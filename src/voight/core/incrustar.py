"""Incrustación de diagramas e imágenes relativas al fusionar Moodle XML.

Las preguntas se escriben como texto:

- un diagrama mermaid es un bloque ```mermaid (o ``<pre class="mermaid">``,
  ``<div class="mermaid">`` o ``<pre><code class="language-mermaid">``);
- un diagrama de estructura de datos es un bloque ```estructura (o ```statics) con
  el bloque de statics en YAML/JSON (o sus equivalentes HTML con la clase
  ``estructura``), el mismo formato que dibuja alucarD;
- una imagen se referencia con una ruta relativa al archivo de la pregunta
  (``![alt](img/a.png)`` o ``<img src="img/a.png">``).

Los archivos fuente no se tocan: sólo al fusionarlos (`unify`) cada mermaid se
renderiza con mermaid-cli (`mmdc`), cada estructura con el renderizador SVG de
alucarD, y la imagen resultante (o la referenciada) se adjunta al campo que la usa
como ``<file encoding="base64">``, con el bloque o la referencia cambiados por una
imagen ``@@PLUGINFILE@@/<nombre>``, que es como Moodle importa los archivos de un
campo de texto.

Los renders de mermaid se guardan en la caché de voight por contenido (ver `cache.py`).
"""
from __future__ import annotations

import base64
import hashlib
import html
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import quote, unquote

from voight.core.cache import Cache
from voight.core.codigo import transformar_fragmento

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
_FENCE_ESTRUCTURA = _fence("estructura|statics")
_HTML_ESTRUCTURA = _html("estructura|statics")
_IMG_MD = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src><[^>]+>|[^)\s]+)(?P<titulo>\s+\"[^\"]*\")?\)")
_IMG_HTML = re.compile(r"(?P<antes><img\b[^>]*?\bsrc\s*=\s*)(?P<q>[\"'])(?P<src>.*?)(?P=q)", re.S | re.I)
# Absolutas, de Moodle o embebidas: quedan como están.
_NO_RELATIVA = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|/|#|@@PLUGINFILE@@)", re.I)

# Campos cuyo <text> nunca lleva imágenes.
_SIN_RECURSOS = {"name", "tag", "category", "info"}


class ErrorIncrustacion(Exception):
    """Un diagrama que no se pudo renderizar o una imagen que no existe."""


def comando_mermaid() -> Optional[str]:
    """El ejecutable de mermaid-cli: `VOIGHT_MMDC` o `mmdc` en el PATH."""
    return os.environ.get("VOIGHT_MMDC") or shutil.which("mmdc")


def _limpiar_codigo(codigo: str, es_html: bool) -> str:
    """Código de un diagrama (mermaid o estructura) en ASCII: sin entidades, símbolos fullwidth ni marcas `·`/`↵`."""
    if es_html:
        codigo = html.unescape(re.sub(r"<br\s*/?>", "\n", codigo, flags=re.I))
    return transformar_fragmento(codigo, contexto="xml", fullwidth=False).strip() + "\n"


def _codigo_html(m: re.Match) -> str:
    return m.group("codigo") if m.group("codigo") is not None else m.group("codigo2")


def motor_estructuras():
    """El módulo de diagramas de alucarD (`generador_examenes.diagramas`), o None."""
    try:
        from generador_examenes import diagramas
    except ImportError:
        return None
    return diagramas


def renderizar_estructura(codigo: str) -> bytes:
    """Dibuja los bloques de statics de `codigo` (YAML/JSON) como un único SVG."""
    motor = motor_estructuras()
    if motor is None:
        raise ErrorIncrustacion(
            "los diagramas ```estructura los dibuja alucarD (generador-examenes), que no está "
            "instalado. Sumalo al entorno de voight: uv tool install --with "
            "\"generador-examenes @ git+https://github.com/INGCOM-UNRN/alucarD\" "
            "\"voight @ git+https://github.com/INGCOM-UNRN/voight\"")
    try:
        svgs = [motor.renderizar(b) for b in motor.leer_bloques(codigo)]
    except ValueError as e:  # ErrorDiagrama
        raise ErrorIncrustacion(f"diagrama de estructura inválido: {e}") from e
    if len(svgs) == 1:
        return svgs[0].encode("utf-8")
    return _apilar_svgs(svgs).encode("utf-8")


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


def incrustar_texto(texto: str, formato_texto: str, base: Path, adjuntos: _Adjuntos,
                    formato_diagrama: str = "png", cache: Optional[Cache] = None) -> str:
    """Reemplaza diagramas e imágenes relativas de un texto por referencias a `adjuntos`."""
    markdown = formato_texto == "markdown"

    def diagrama(codigo: str, es_html: bool) -> str:
        codigo = _limpiar_codigo(codigo, es_html)
        datos = renderizar_mermaid(codigo, formato_diagrama, cache)
        nombre = f"mermaid-{hashlib.sha1(codigo.encode()).hexdigest()[:12]}.{formato_diagrama}"
        return _imagen(adjuntos.agregar(nombre, datos), "diagrama", markdown)

    def estructura(codigo: str, es_html: bool) -> str:
        codigo = _limpiar_codigo(codigo, es_html)
        datos = renderizar_estructura(codigo)
        nombre = f"estructura-{hashlib.sha1(codigo.encode()).hexdigest()[:12]}.svg"
        return _imagen(adjuntos.agregar(nombre, datos), "diagrama de estructura", markdown)

    texto = _FENCE_MERMAID.sub(lambda m: diagrama(m.group("codigo"), False), texto)
    texto = _HTML_MERMAID.sub(lambda m: diagrama(_codigo_html(m), True), texto)
    texto = _FENCE_ESTRUCTURA.sub(lambda m: estructura(m.group("codigo"), False), texto)
    texto = _HTML_ESTRUCTURA.sub(lambda m: estructura(_codigo_html(m), True), texto)

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
            texto.text = incrustar_texto(texto.text, campo.get("format", "html"), base,
                                         adjuntos, formato_diagrama, cache)
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

