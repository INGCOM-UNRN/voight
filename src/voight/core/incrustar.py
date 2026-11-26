"""Incrustación de diagramas, fórmulas e imágenes relativas al fusionar Moodle XML.

Las preguntas se escriben como texto:

- un diagrama mermaid es un bloque ```mermaid (o ``<pre class="mermaid">``,
  ``<div class="mermaid">`` o ``<pre><code class="language-mermaid">``);
- un diagrama de dibu (estructuras de datos, sistemas de computación, control, química,
  señales…) es un bloque ```dibu (o ```estructura, ```statics) con uno o varios bloques en
  YAML/JSON (o sus equivalentes HTML con la clase ``dibu``, ``estructura`` o ``statics``);
- un diagrama PlantUML es un bloque ```plantuml o ```puml (o sus equivalentes HTML con la clase
  ``plantuml``/``puml``), con sus opciones en comentarios ``// [centrado] [ancho, 60%] [alt, texto]``,
  el mismo formato de alucarD;
- una fórmula se escribe ``$...$`` o ``$$...$$`` (en HTML, también ``\\(...\\)`` y ``\\[...\\]``);
- una tabla va en un bloque ```tabla, con sintaxis Markdown, y pasa a una tabla HTML (no es una imagen);
- una imagen se referencia con una ruta relativa al archivo de la pregunta
  (``![alt](img/a.png)`` o ``<img src="img/a.png">``).

Los archivos fuente no se tocan: sólo al fusionarlos (`unify`) cada mermaid se
renderiza con mermaid-cli (`mmdc`), cada diagrama de dibu con el binario `dibu`, cada PlantUML con el
programa `plantuml` a través de alucarD y cada fórmula con el renderizador SVG de alucarD, y la imagen resultante (o la referenciada) se adjunta al campo que la usa
como ``<file encoding="base64">``, con el bloque o la referencia cambiados por una
imagen ``@@PLUGINFILE@@/<nombre>``, que es como Moodle importa los archivos de un
campo de texto. `moodle backup-quiz` usa lo mismo para guardar las imágenes en el MBZ.

Los renders de mermaid, dibu y fórmulas se guardan en la caché de voight por contenido (ver `cache.py`).
"""
from __future__ import annotations

import base64
import hashlib
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import quote, unquote

from voight.core.cache import Cache
from voight.core.codigo import transformar_fragmento
from voight.core.formulas import reemplazar

FORMATOS_DIAGRAMA = ("png", "svg")


def _fence(lenguajes: str) -> re.Pattern:
    """Bloque de código Markdown (``` o ~~~, de 3 o más) de alguno de `lenguajes`."""
    return re.compile(r"^[ \t]*(?P<valla>`{3,}|~{3,})[ \t]*(?:" + lenguajes + r")[ \t]*\n"
                      r"(?P<codigo>.*?\n)[ \t]*(?P=valla)[ \t]*$", re.S | re.M | re.I)


def _html(clases: str) -> re.Pattern:
    """`<pre>`/`<div>` con alguna de `clases`, o `<pre><code class="language-…">`."""
    clase = r"\bclass\s*=\s*[\"'][^\"']*\b(?:language-)?(?:" + clases + r")\b[^\"']*[\"']"
    return re.compile(
        r"<pre\b[^>]*>\s*<code\b[^>]*" + clase + r"[^>]*>(?P<codigo>.*?)</code>\s*</pre>"
        r"|<(?P<tag>pre|div)\b[^>]*" + clase + r"[^>]*>(?P<codigo2>.*?)</(?P=tag)>", re.S | re.I)


_FENCE_MERMAID = _fence("mermaid")
_HTML_MERMAID = _html("mermaid")
# Los bloques que dibuja dibu: ```dibu y los nombres heredados de statics y alucarD.
_FENCE_DIBU = _fence("dibu|estructura|statics")
_HTML_DIBU = _html("dibu|estructura|statics")
_FENCE_PLANTUML = _fence("plantuml|puml")
_HTML_PLANTUML = _html("plantuml|puml")
_FENCE_TABLA = _fence("tabla")
_HTML_TABLA = _html("tabla")
_IMG_MD = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src><[^>]+>|[^)\s]+)(?P<titulo>\s+\"[^\"]*\")?\)")
_IMG_HTML = re.compile(r"(?P<antes><img\b[^>]*?\bsrc\s*=\s*)(?P<q>[\"'])(?P<src>.*?)(?P=q)", re.S | re.I)
# Absolutas, de Moodle o embebidas: quedan como están.
_NO_RELATIVA = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|/|#|@@PLUGINFILE@@)", re.I)

# Campos cuyo <text> nunca lleva imágenes.
_SIN_RECURSOS = {"name", "tag", "category", "info"}
# Las respuestas de los demás tipos se comparan como texto: una imagen no se puede calificar.
_RESPUESTA_CON_FORMULAS = "multichoice"

_INSTALAR_ALUCARD = ("uv tool install --with \"generador-examenes @ git+https://github.com/INGCOM-UNRN/alucarD\" "
                     "\"voight @ git+https://github.com/INGCOM-UNRN/voight\"")


class ErrorIncrustacion(Exception):
    """Un diagrama que no se pudo renderizar o una imagen que no existe."""


def comando_mermaid() -> Optional[str]:
    """El ejecutable de mermaid-cli: `VOIGHT_MMDC` o `mmdc` en el PATH."""
    return os.environ.get("VOIGHT_MMDC") or shutil.which("mmdc")


def comando_dibu() -> Optional[str]:
    """El binario `dibu`: `VOIGHT_DIBU`, `DIBU_BIN`, el del entorno de voight o `dibu` en el PATH."""
    for variable in ("VOIGHT_DIBU", "DIBU_BIN"):
        if os.environ.get(variable):
            return os.environ[variable]
    junto_python = Path(sys.executable).parent / ("dibu.exe" if os.name == "nt" else "dibu")
    if junto_python.is_file() and os.access(junto_python, os.X_OK):
        return str(junto_python)
    return shutil.which("dibu")


def _huella(ruta: str) -> str:
    """Identifica un ejecutable (ruta, tamaño y fecha): si se actualiza, la caché no lo confunde."""
    try:
        st = Path(ruta).stat()
    except OSError:
        return ruta
    return f"{ruta}|{st.st_size}|{st.st_mtime_ns}"


def _limpiar_codigo(codigo: str, es_html: bool) -> str:
    """Código de un diagrama (mermaid, dibu o PlantUML) en ASCII: sin entidades, símbolos fullwidth ni marcas `·`/`↵`."""
    if es_html:
        codigo = html.unescape(re.sub(r"<br\s*/?>", "\n", codigo, flags=re.I))
    return transformar_fragmento(codigo, contexto="xml", fullwidth=False).strip() + "\n"


def _codigo_html(m: re.Match) -> str:
    return m.group("codigo") if m.group("codigo") is not None else m.group("codigo2")


_INSTALAR_DIBU = ("instalá dibu (la rueda de sus releases con `uv tool install --with ./dibu-*.whl "
                  "\"voight @ git+https://github.com/INGCOM-UNRN/voight\"`, o `cargo install --path crates/dibu-cli` "
                  "desde https://github.com/INGCOM-UNRN/dibu) o indicá su ruta en VOIGHT_DIBU")


def renderizar_dibu(codigo: str, cache: Optional[Cache] = None) -> bytes:
    """Dibuja los bloques de dibu de `codigo` (YAML/JSON: un bloque, una lista o `blocks:`) como un SVG.

    Usa `dibu render`; varios bloques quedan apilados en una sola imagen. El theme sale de
    `DIBU_THEME` o del `theme:` de cada bloque, como en el resto del ecosistema.
    """
    dibu = comando_dibu()
    if not dibu:
        raise ErrorIncrustacion(f"los diagramas de dibu los dibuja el binario `dibu`, que no se encontró: {_INSTALAR_DIBU}")
    cache = cache or Cache("dibu")
    clave = Cache.clave("dibu", _huella(dibu), os.environ.get("DIBU_THEME", ""), codigo)
    guardado = cache.obtener(clave)
    if guardado:
        return base64.b64decode(guardado)

    with tempfile.TemporaryDirectory(prefix="voight-dibu-") as tmp:
        entrada, salida = Path(tmp) / "diagrama.yaml", Path(tmp) / "svg"
        entrada.write_text(codigo, encoding="utf-8")
        try:
            r = subprocess.run([dibu, "render", str(entrada), "-o", str(salida)],
                               capture_output=True, text=True, encoding="utf-8", timeout=120)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ErrorIncrustacion(f"dibu no pudo ejecutarse: {e}") from e
        # dibu nombra cada bloque diagrama_<n>.svg, desde 1.
        svgs = sorted(salida.glob("diagrama_*.svg"), key=lambda p: int(p.stem.rsplit("_", 1)[1]))
        if r.returncode != 0 or not svgs:
            detalle = [linea.strip().replace(f"{entrada}: ", "")
                       for linea in (r.stderr or r.stdout).splitlines() if linea.strip()]
            raise ErrorIncrustacion("diagrama de dibu inválido: "
                                    + (" ".join(detalle[:3]) if detalle else f"dibu terminó con código {r.returncode}"))
        textos = [p.read_text(encoding="utf-8") for p in svgs]
    datos = (textos[0] if len(textos) == 1 else _apilar_svgs(textos)).encode("utf-8")
    cache.guardar(clave, base64.b64encode(datos).decode("ascii"))
    return datos


def motor_formulas():
    """El módulo de fórmulas de alucarD (`generador_examenes.matematica`), o None."""
    try:
        from generador_examenes import matematica
    except ImportError:
        return None
    return matematica if hasattr(matematica, "a_svg") else None


def motor_tablas():
    """El armado de tablas para Moodle de alucarD, como una función del bloque, o None."""
    try:
        from generador_examenes.core.markdown_utils import markdown_to_html
        from generador_examenes.tablas import tabla_a_moodle
    except ImportError:
        return None
    return lambda cuerpo: tabla_a_moodle(cuerpo, markdown_to_html)


def motor_plantuml():
    """El módulo de PlantUML de alucarD (`generador_examenes.plantuml`), o None."""
    try:
        from generador_examenes import plantuml
    except ImportError:
        return None
    return plantuml


def renderizar_plantuml(cuerpo: str, formato: str = "png") -> tuple:
    """(imagen, opciones) de un bloque ```plantuml; alucarD guarda los dibujos en su caché."""
    motor = motor_plantuml()
    if motor is None:
        raise ErrorIncrustacion("los diagramas ```plantuml los arma alucarD (generador-examenes), que no está "
                                f"instalado o es anterior a ellos. Sumalo al entorno de voight: {_INSTALAR_ALUCARD}")
    try:
        return motor.a_imagen(cuerpo, formato), motor.leer(cuerpo)[0]
    except ValueError as e:  # ErrorPlantuml
        raise ErrorIncrustacion(f"diagrama PlantUML inválido: {e}") from e


def renderizar_tabla(cuerpo: str) -> str:
    """Un bloque ```tabla como una tabla HTML."""
    motor = motor_tablas()
    if motor is None:
        raise ErrorIncrustacion("las tablas las arma alucarD (generador-examenes), que no está instalado o es "
                                f"anterior a los bloques ```tabla. Sumalo al entorno de voight: {_INSTALAR_ALUCARD}")
    try:
        return motor(cuerpo)
    except ValueError as e:  # ErrorTabla
        raise ErrorIncrustacion(f"tabla inválida: {e}") from e


def renderizar_formula(fuente: str, bloque: bool, cache: Optional[Cache] = None) -> bytes:
    """Dibuja una fórmula en LaTeX como SVG."""
    cache = cache or Cache("formulas")
    clave = Cache.clave("formula", bloque, fuente)
    guardado = cache.obtener(clave)
    if guardado:
        return base64.b64decode(guardado)

    motor = motor_formulas()
    if motor is None:
        raise ErrorIncrustacion("las fórmulas las dibuja alucarD (generador-examenes), que no está instalado "
                                f"o es anterior a `a_svg`. Sumalo al entorno de voight: {_INSTALAR_ALUCARD}")
    try:
        datos = motor.a_svg(fuente, bloque).encode("utf-8")
    except (ValueError, RuntimeError) as e:  # ErrorFormula, o Typst que no compila
        raise ErrorIncrustacion(f"fórmula inválida «{fuente}»: {e}") from e
    cache.guardar(clave, base64.b64encode(datos).decode("ascii"))
    return datos


def _apilar_svgs(svgs: list) -> str:
    """Varios `<svg>` uno debajo del otro en un único SVG (una sola imagen por bloque)."""
    def medida(svg: str, atributo: str) -> int:
        m = re.search(r'\b' + atributo + r'="(\d+(?:\.\d+)?)"', svg)
        return int(float(m.group(1))) if m else 0

    ancho, y, partes = 0, 0, []
    for svg in svgs:
        w, h = medida(svg, "width"), medida(svg, "height")
        partes.append(re.sub(r"^<svg\b", f'<svg x="0" y="{y}"', svg, count=1))
        ancho, y = max(ancho, w), y + h + 8
    alto = max(y - 8, 0)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" height="{alto}" '
            f'viewBox="0 0 {ancho} {alto}">' + "".join(partes) + "</svg>")


def renderizar_mermaid(codigo: str, formato: str = "png", cache: Optional[Cache] = None) -> bytes:
    """Renderiza un diagrama mermaid con `mmdc` y devuelve la imagen."""
    cache = cache or Cache("mermaid")
    clave = Cache.clave("mermaid", formato, codigo)
    guardado = cache.obtener(clave)
    if guardado:
        return base64.b64decode(guardado)

    mmdc = comando_mermaid()
    if not mmdc:
        raise ErrorIncrustacion(
            "no se encontró mermaid-cli (`mmdc`): instalalo con "
            "`npm install -g @mermaid-js/mermaid-cli` o indicá su ruta en VOIGHT_MMDC")
    with tempfile.TemporaryDirectory(prefix="voight-mermaid-") as tmp:
        entrada, salida = Path(tmp) / "diagrama.mmd", Path(tmp) / f"diagrama.{formato}"
        entrada.write_text(codigo, encoding="utf-8")
        try:
            r = subprocess.run([mmdc, "-q", "-i", str(entrada), "-o", str(salida), "-b", "white"],
                               capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ErrorIncrustacion(f"mmdc no pudo ejecutarse: {e}") from e
        if r.returncode != 0 or not salida.exists():
            detalle = (r.stderr or r.stdout).strip().splitlines()
            raise ErrorIncrustacion("mmdc no pudo renderizar el diagrama: "
                                    + (" ".join(detalle[:3]) if detalle else f"código {r.returncode}"))
        datos = salida.read_bytes()
    cache.guardar(clave, base64.b64encode(datos).decode("ascii"))
    return datos


class _Adjuntos:
    """Los archivos de UN campo de texto: nombres únicos dentro del campo."""

    def __init__(self, existentes: Optional[Dict[str, bytes]] = None) -> None:
        self.archivos: Dict[str, bytes] = dict(existentes or {})

    def agregar(self, nombre: str, datos: bytes) -> str:
        """Agrega el archivo y devuelve la URL con la que se lo referencia."""
        if self.archivos.get(nombre, datos) != datos:
            raiz, ext = os.path.splitext(nombre)
            nombre = f"{raiz}-{hashlib.sha1(datos).hexdigest()[:8]}{ext}"
        self.archivos[nombre] = datos
        return "@@PLUGINFILE@@/" + quote(nombre)


def _imagen(url: str, alt: str, markdown: bool) -> str:
    if markdown:
        return f"![{alt}]({url})"
    return f'<img src="{url}" alt="{html.escape(alt)}">'


def _imagen_plantuml(url: str, opciones: dict) -> str:
    """En HTML también en Markdown: hacen falta la posición y las medidas."""
    margen = {"izquierda": "0.5em auto 0.5em 0", "derecha": "0.5em 0 0.5em auto"}.get(opciones.get("posicion", ""), "0.5em auto")
    estilo = motor_plantuml().estilo(opciones)
    alt = html.escape(opciones.get("alt", "diagrama"), quote=True)
    return f'<img src="{url}" alt="{alt}" style="display:block;margin:{margen};{estilo}">'


def _imagen_formula(url: str, fuente: str, bloque: bool) -> str:
    """En HTML también en Markdown: hace falta el estilo para que quede en el renglón."""
    estilo = "display:block;margin:0.5em auto" if bloque else "vertical-align:middle"
    return f'<img src="{url}" alt="{html.escape(fuente, quote=True)}" style="{estilo}">'


def incrustar_texto(texto: str, formato_texto: str, base: Path, adjuntos: _Adjuntos,
                    formato_diagrama: str = "png", cache: Optional[Cache] = None,
                    con_formulas: bool = True) -> str:
    """Reemplaza diagramas, fórmulas e imágenes relativas de un texto por referencias a `adjuntos`."""
    markdown = formato_texto == "markdown"

    def diagrama(codigo: str, es_html: bool) -> str:
        codigo = _limpiar_codigo(codigo, es_html)
        datos = renderizar_mermaid(codigo, formato_diagrama, cache)
        nombre = f"mermaid-{hashlib.sha1(codigo.encode()).hexdigest()[:12]}.{formato_diagrama}"
        return _imagen(adjuntos.agregar(nombre, datos), "diagrama", markdown)

    def dibu(codigo: str, es_html: bool) -> str:
        codigo = _limpiar_codigo(codigo, es_html)
        datos = renderizar_dibu(codigo, cache)
        nombre = f"dibu-{hashlib.sha1(codigo.encode()).hexdigest()[:12]}.svg"
        return _imagen(adjuntos.agregar(nombre, datos), "diagrama", markdown)

    def plantuml(codigo: str, es_html: bool) -> str:
        codigo = _limpiar_codigo(codigo, es_html)
        datos, opciones = renderizar_plantuml(codigo, formato_diagrama)
        nombre = f"plantuml-{hashlib.sha1(codigo.encode()).hexdigest()[:12]}.{formato_diagrama}"
        return _imagen_plantuml(adjuntos.agregar(nombre, datos), opciones)

    texto = _FENCE_PLANTUML.sub(lambda m: plantuml(m.group("codigo"), False), texto)
    texto = _HTML_PLANTUML.sub(lambda m: plantuml(_codigo_html(m), True), texto)
    texto = _FENCE_MERMAID.sub(lambda m: diagrama(m.group("codigo"), False), texto)
    texto = _HTML_MERMAID.sub(lambda m: diagrama(_codigo_html(m), True), texto)
    texto = _FENCE_DIBU.sub(lambda m: dibu(m.group("codigo"), False), texto)
    texto = _HTML_DIBU.sub(lambda m: dibu(_codigo_html(m), True), texto)

    def formula(fuente: str, bloque: bool) -> str:
        fuente = _limpiar_codigo(fuente, False).strip()
        datos = renderizar_formula(fuente, bloque, cache)
        nombre = f"formula-{hashlib.sha1(f'{bloque}{fuente}'.encode()).hexdigest()[:12]}.svg"
        return _imagen_formula(adjuntos.agregar(nombre, datos), fuente, bloque)

    def tabla(cuerpo: str) -> str:
        # Las fórmulas de las celdas pasan por marcadores: un `|` en su texto alternativo cortaría la celda.
        imagenes: Dict[str, str] = {}

        def apartar(fuente: str, bloque: bool) -> str:
            marcador = f"VOIGHTFORMULA{len(imagenes)}X"
            imagenes[marcador] = formula(fuente, bloque)
            return marcador

        resultado = renderizar_tabla(reemplazar(cuerpo, False, apartar))
        for marcador, imagen in imagenes.items():
            resultado = resultado.replace(marcador, imagen)
        return f"\n\n{resultado}\n\n" if markdown else resultado

    texto = _FENCE_TABLA.sub(lambda m: tabla(m.group("codigo")), texto)
    texto = _HTML_TABLA.sub(lambda m: tabla(html.unescape(_codigo_html(m))), texto)

    if con_formulas:
        texto = reemplazar(texto, not markdown, formula)

    def leer(src: str) -> Optional[str]:
        """La URL @@PLUGINFILE@@ de una imagen relativa, o None si no es relativa."""
        src = src.strip().strip("<>")
        if not src or _NO_RELATIVA.match(src):
            return None
        ruta = (base / unquote(src.split("?")[0].split("#")[0])).resolve()
        if not ruta.is_file():
            raise ErrorIncrustacion(f"no existe la imagen «{src}» (buscada en {ruta})")
        return adjuntos.agregar(ruta.name, ruta.read_bytes())

    def img_md(m: re.Match) -> str:
        url = leer(m.group("src"))
        return m.group(0) if url is None else f"![{m.group('alt')}]({url}{m.group('titulo') or ''})"

    def img_html(m: re.Match) -> str:
        url = leer(html.unescape(m.group("src")))
        return m.group(0) if url is None else f"{m.group('antes')}{m.group('q')}{url}{m.group('q')}"

    texto = _IMG_MD.sub(img_md, texto)
    return _IMG_HTML.sub(img_html, texto)


def incrustar_pregunta(pregunta: ET.Element, base: Path, formato_diagrama: str = "png",
                       cache: Optional[Cache] = None) -> int:
    """Incrusta los recursos de cada campo de un <question>; devuelve cuántos adjuntó.

    `base` es el directorio contra el que se resuelven las rutas relativas (el del
    archivo de la pregunta).
    """
    if formato_diagrama not in FORMATOS_DIAGRAMA:
        raise ValueError(f"Formato de diagrama no soportado: {formato_diagrama}")
    total = 0
    for campo in list(pregunta.iter()):
        if campo.tag in _SIN_RECURSOS:
            continue
        texto = campo.find("text")
        if texto is None or not texto.text or campo.get("format") == "plain_text":
            continue
        # Los <file> que el campo ya trae (p. ej. exportado de Moodle) reservan su nombre.
        existentes = {f.get("name", ""): base64.b64decode(f.text or "") for f in campo.findall("file")}
        adjuntos = _Adjuntos(existentes)
        try:
            con_formulas = campo.tag != "answer" or pregunta.get("type") == _RESPUESTA_CON_FORMULAS
            texto.text = incrustar_texto(texto.text, campo.get("format", "html"), base,
                                         adjuntos, formato_diagrama, cache, con_formulas)
        except ErrorIncrustacion as e:
            nombre = pregunta.findtext("name/text") or "(sin nombre)"
            raise ErrorIncrustacion(f"{nombre.strip()} <{campo.tag}>: {e}") from e
        nuevos = [(n, d) for n, d in adjuntos.archivos.items() if n not in existentes]
        posicion = list(campo).index(texto) + 1
        for i, (nombre, datos) in enumerate(nuevos):
            archivo = ET.Element("file", {"name": nombre, "path": "/", "encoding": "base64"})
            archivo.text = base64.b64encode(datos).decode("ascii")
            campo.insert(posicion + i, archivo)
        total += len(nuevos)
    return total

