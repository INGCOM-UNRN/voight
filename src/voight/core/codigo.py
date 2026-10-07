"""Secciones de código en bancos de preguntas: símbolos fullwidth y marcas de espacio.

GIFT usa ``{ } = ~ # :`` y la barra invertida como sintaxis, y una línea en blanco
termina la pregunta; el código C y Java usa esos mismos caracteres. Dentro de las
secciones de código (bloques `````, código en línea ```...``` y ``<pre>``/``<code>``
en HTML) los caracteres que chocan se reemplazan por sus equivalentes fullwidth,
la indentación se marca con ``·`` (un punto por espacio) y cada salto de línea con
``↵`` al final de la línea. La transformación es la misma para GIFT y Moodle XML;
lo único que cambia es el contexto en el que se escribe el resultado:

- ``gift``: el texto crudo del archivo GIFT. Al restaurar los caracteres normales se
  escapan con ``\\`` los que GIFT interpreta y las líneas en blanco del código
  conservan su ``↵`` (sin él, la línea en blanco cortaría la pregunta).
- ``xml``: el contenido de un ``<text>`` (CDATA o texto escapado) de Moodle XML.

La referencia de caracteres está en ``docs/caracteres_especiales.md``.
"""

from __future__ import annotations

import re
from typing import Callable, Optional

MARCA_ESPACIO = "·"
MARCA_SALTO = "↵"

# Caracteres que se reemplazan por su forma fullwidth (U+FF01..U+FF5E = ASCII + 0xFEE0).
SIMBOLOS_FULLWIDTH = '=#{}~:;<>[]()*"&\\'
_A_FULLWIDTH = {c: chr(ord(c) + 0xFEE0) for c in SIMBOLOS_FULLWIDTH}
# Secuencias de dos caracteres con una forma propia: `==` y el comentario `//`
# (una línea que empieza con `//` es un comentario de GIFT y se descarta).
_SECUENCIAS_A_FULLWIDTH = {"==": "⩵", "//": "／／"}

# Variantes históricas de los bancos que se llevan a la forma canónica.
_VARIANTES_ESPACIO = "\u2007\u2000\u00a0\u3000"  # figure space, en quad, NBSP, ideographic
_VARIANTES_A_CANONICA = {**{c: MARCA_ESPACIO for c in _VARIANTES_ESPACIO}, "\u037e": "；"}

# Toda la tabla fullwidth (no sólo SIMBOLOS_FULLWIDTH) vuelve a ASCII: los bancos
# también traen ＋ － ． ／ ， ％ ！ ？ …
_A_NORMAL = {chr(c): chr(c - 0xFEE0) for c in range(0xFF01, 0xFF5F)}
_A_NORMAL.update({"⩵": "==", "\u037e": ";", MARCA_ESPACIO: " "})
_A_NORMAL.update({c: " " for c in _VARIANTES_ESPACIO})

# Entidades que aparecen en el código de preguntas exportadas como HTML. Lista
# cerrada a propósito: html.unescape también reconoce `&not`, `&copy`… sin `;`, que
# en C son el operador & seguido de un identificador.
_ENTIDADES = {
    "&lt;": "<", "&#60;": "<", "&gt;": ">", "&#62;": ">",
    "&quot;": '"', "&#34;": '"', "&apos;": "'", "&#39;": "'",
    "&nbsp;": " ", "&amp;": "&", "&#38;": "&",
}

# Escapes de GIFT que pueden aparecer dentro de código ya escrito en forma normal.
_ESCAPE_GIFT = re.compile(r"\\([\\{}=#~:])")

_FENCE = r"(?P<fence>```)(?P<lang>[^\n`]*)\n(?P<bloque>.*?)```"
_HTML = r"(?P<abre><(?P<tag>pre|code)\b[^>]*>)(?P<html>.*?)(?P<cierra></(?P=tag)>)"
# El código en línea puede ocupar varias líneas (como en markdown) pero no cruzar un
# párrafo; en GIFT tampoco cruza el comienzo de otra opción de respuesta.
_EN_LINEA = r"(?<!`)`(?!`)(?P<linea>(?:[^`\n]|\n(?![ \t]*\n{corte}))+?)`(?!`)"
_SECCIONES = {
    "xml": re.compile("|".join([_FENCE, _HTML, _EN_LINEA.format(corte="")]), re.S | re.I),
    "gift": re.compile(
        "|".join([_FENCE, _HTML, _EN_LINEA.format(corte=r"|[ \t]*[=~#}]")]), re.S | re.I
    ),
}


def _sin_entidades(texto: str) -> str:
    for entidad, caracter in _ENTIDADES.items():
        if entidad != "&amp;":
            texto = texto.replace(entidad, caracter)
    return texto.replace("&amp;", "&")


def _a_fullwidth(texto: str) -> str:
    for secuencia, forma in _SECUENCIAS_A_FULLWIDTH.items():
        texto = texto.replace(secuencia, forma)
    return "".join(_A_FULLWIDTH.get(c) or _VARIANTES_A_CANONICA.get(c) or c for c in texto)


def _canonizar_marcas(texto: str) -> str:
    return "".join(_VARIANTES_A_CANONICA.get(c, c) for c in texto)


def _marcar(texto: str, espacios: bool, saltos: bool, primera_es_linea: bool, bloque: bool = False) -> str:
    """Marca la indentación con `·` y los saltos con `↵` (idempotente).

    En un bloque ``` (`bloque`) todas las líneas de código llevan `↵`, también la última
    (la que precede a la guarda de cierre). En `<pre>` y en el código en línea la última
    línea no lo lleva: es la que cierra la sección. Con `primera_es_linea`
    en falso (código en línea) la primera línea empieza a mitad de un párrafo y su
    indentación no se toca.
    """
    lineas = texto.split("\n")
    # Un bloque ``` termina en "\n```": el último elemento vacío es la línea del cierre.
    ultima = len(lineas) - 2 if len(lineas) > 1 and lineas[-1] == "" else len(lineas) - 1
    # En un bloque ```, el último elemento vacío es la línea de la guarda de cierre: la
    # última línea de código queda antes y también lleva `↵`.
    cierre = len(lineas) - 1 if bloque and len(lineas) > 1 and lineas[-1] == "" else None
    if cierre is not None:
        ultima = cierre
    salida = []
    for i, linea in enumerate(lineas):
        if espacios and (i > 0 or primera_es_linea):
            cuerpo = linea.lstrip(" \t" + MARCA_ESPACIO)
            sangria = linea[: len(linea) - len(cuerpo)]
            linea = sangria.replace("\t", "    ").replace(" ", MARCA_ESPACIO) + cuerpo
        # Una última línea en blanco también lleva `↵` (en GIFT cortaría la pregunta).
        lleva_salto = i < ultima or (cierre is None and primera_es_linea and i == ultima > 0
                                     and not linea.strip(" \t" + MARCA_ESPACIO))
        if saltos and lleva_salto and not linea.endswith(MARCA_SALTO):
            linea += MARCA_SALTO
        salida.append(linea)
    return "\n".join(salida)


def _escapar_gift(texto: str) -> str:
    """Escapa con `\\` lo que GIFT interpretaría (forma normal de GIFT; `↵` queda tal cual)."""
    return re.sub(r"([\\{}=#~:])", r"\\\1", texto)


def _proteger_lineas_vacias(texto: str) -> str:
    """En GIFT una línea en blanco corta la pregunta: dentro del código lleva `↵`."""
    lineas = texto.split("\n")
    ultima = len(lineas) - 1
    return "\n".join(
        MARCA_SALTO if (0 < i < ultima and not linea.strip()) else linea
        for i, linea in enumerate(lineas)
    )


def _restaurar(texto: str, conservar_lineas_vacias: bool) -> str:
    """Vuelve a ASCII. Sólo se quita el `↵` que precede a un salto real: uno a mitad de
    línea (p. ej. la salida `hola↵mundo` en código en línea) es contenido del autor."""
    lineas = texto.split("\n")
    ultima = len(lineas) - 1
    salida = []
    for i, linea in enumerate(lineas):
        if i < ultima and linea.endswith(MARCA_SALTO):
            linea = linea[:-1]
        linea = "".join(_A_NORMAL.get(c, c) for c in linea)
        if conservar_lineas_vacias and 0 < i < ultima and not linea.strip():
            linea = MARCA_SALTO
        salida.append(linea)
    return "\n".join(salida)


def transformar_fragmento(
    codigo: str,
    *,
    contexto: str = "xml",
    fullwidth: bool | None = True,
    espacios: bool = True,
    saltos: bool = True,
    html: bool = False,
    multilinea: bool = True,
    escapes: bool = True,
    bloque: bool = False,
) -> str:
    """Transforma el contenido de UNA sección de código.

    `fullwidth`: True lleva los símbolos a fullwidth, False los restaura a ASCII
    (quitando también las marcas `·` y `↵`) y None no los toca. `espacios` y `saltos`
    agregan las marcas `·` y `↵` (sólo si no se está restaurando). `html` indica que
    el código está dentro de `<pre>`/`<code>`: las entidades se interpretan al
    proteger y `< > &` se vuelven a escapar al restaurar. `multilinea` en falso
    indica código en línea (su primera línea no es una línea propia). `escapes` en
    falso indica que el código de un GIFT viene crudo (sin `\\{`, `\\\\`…), como el
    que devuelve un LLM: entonces no se desescapa. `bloque` indica un bloque ```: su
    última línea de código también lleva `↵`.
    """
    gift = contexto == "gift"
    desescapar = gift and escapes

    if fullwidth is False:
        if desescapar:
            codigo = _ESCAPE_GIFT.sub(r"\1", codigo)
        codigo = _restaurar(_sin_entidades(codigo) if html else codigo, conservar_lineas_vacias=gift)
        if html:
            codigo = codigo.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if gift:
            codigo = _escapar_gift(codigo)
        return codigo

    if fullwidth:
        if desescapar:
            codigo = _ESCAPE_GIFT.sub(r"\1", codigo)
        codigo = _a_fullwidth(_sin_entidades(codigo))
    else:
        codigo = _canonizar_marcas(codigo)
    if espacios or saltos:
        codigo = _marcar(codigo, espacios, saltos, primera_es_linea=multilinea, bloque=bloque)
    if gift:
        codigo = _proteger_lineas_vacias(codigo)
    return codigo


def transformar_secciones(
    texto: str,
    funcion: Callable[..., str],
    contexto: str = "xml",
) -> tuple[str, int]:
    """Aplica `funcion(codigo, html=..., multilinea=..., bloque=...)` a cada sección de código
    del texto (`bloque` es verdadero en los bloques ```).

    Devuelve el texto nuevo y la cantidad de secciones que cambiaron.
    """
    cambios = 0

    def reemplazar(m: re.Match) -> str:
        nonlocal cambios
        if m.group("fence"):
            original = m.group("bloque")
            nuevo = funcion(original, html=False, multilinea=True, bloque=True)
            salida = f"```{m.group('lang')}\n{nuevo}```"
        elif m.group("abre"):
            original = m.group("html")
            interno = re.fullmatch(r"(<code\b[^>]*>)(.*)(</code>)", original, re.S | re.I)
            if interno:
                nuevo = interno.group(1) + funcion(interno.group(2), html=True, multilinea=True, bloque=False) + interno.group(3)
            elif "<" in original:
                return m.group(0)  # otras etiquetas adentro (resaltado de sintaxis): no se toca
            else:
                es_pre = m.group("tag").lower() == "pre"
                nuevo = funcion(original, html=True, multilinea=es_pre, bloque=False)
            salida = m.group("abre") + nuevo + m.group("cierra")
        else:
            original = m.group("linea")
            nuevo = funcion(original, html=False, multilinea=False, bloque=False)
            salida = f"`{nuevo}`"
        if salida != m.group(0):
            cambios += 1
        return salida

    return _SECCIONES[contexto].sub(reemplazar, texto), cambios


def fuera_de_codigo(texto: str, funcion: Callable[[str], str], contexto: str = "xml") -> str:
    """Aplica `funcion` sólo al texto que NO es código (p. ej. escapar GIFT)."""
    piezas, ultimo = [], 0
    for m in _SECCIONES[contexto].finditer(texto):
        piezas += [funcion(texto[ultimo:m.start()]), m.group(0)]
        ultimo = m.end()
    piezas.append(funcion(texto[ultimo:]))
    return "".join(piezas)


def transformar_codigo(
    texto: str,
    *,
    contexto: str = "xml",
    fullwidth: bool | None = True,
    espacios: bool = True,
    saltos: bool = True,
    escapes: bool = True,
) -> tuple[str, int]:
    """Transforma todas las secciones de código de un texto (ver `transformar_fragmento`)."""

    def funcion(codigo: str, html: bool, multilinea: bool, bloque: bool = False) -> str:
        return transformar_fragmento(
            codigo, contexto=contexto, fullwidth=fullwidth, espacios=espacios,
            saltos=saltos, html=html, multilinea=multilinea, escapes=escapes, bloque=bloque,
        )

    return transformar_secciones(texto, funcion, contexto)


def usa_convencion(texto: str, contexto: str = "xml") -> tuple[bool, bool]:
    """(símbolos fullwidth, marcas) que usa el código del texto, para restaurar la misma
    convención después de transformarlo."""
    hallado = {"fullwidth": False, "marcas": False}

    def revisar(codigo: str, html: bool, multilinea: bool, bloque: bool = False) -> str:
        if any(c in _A_NORMAL and c not in _VARIANTES_ESPACIO and c != MARCA_ESPACIO for c in codigo):
            hallado["fullwidth"] = True
        if any(c in codigo for c in (MARCA_ESPACIO, MARCA_SALTO) + tuple(_VARIANTES_ESPACIO)):
            hallado["marcas"] = True
        return codigo

    transformar_secciones(texto, revisar, contexto)
    return hallado["fullwidth"], hallado["marcas"]


# ---------------------------------------------------------------------------
# Moodle XML: el código vive dentro de los <text>, en CDATA o como texto escapado
# ---------------------------------------------------------------------------

# `(?<!/)>` excluye `<text/>`: sin eso el contenido se extendería hasta el próximo </text>.
_TEXTO_XML = re.compile(r"(<text\b[^>]*(?<!/)>)(.*?)(</text>)", re.S)
_CDATA = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)


def _desescapar_xml(texto: str) -> str:
    texto = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), texto)
    texto = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), texto)
    for entidad, caracter in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'")):
        texto = texto.replace(entidad, caracter)
    return texto.replace("&amp;", "&")


def a_cdata(texto: str) -> str:
    return "<![CDATA[" + texto.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def transformar_textos_xml(xml: str, funcion: Callable[[str], tuple[str, int]]) -> tuple[str, int]:
    """Aplica `funcion(texto) -> (texto, cambios)` al contenido de cada `<text>` del XML.

    El contenido en CDATA se reescribe en CDATA; el texto escapado sólo se toca si
    cambia, y entonces pasa a CDATA (la convención de los bancos).
    """
    total = 0

    def reemplazar(m: re.Match) -> str:
        nonlocal total
        abre, contenido, cierra = m.groups()
        if not contenido.strip():
            return m.group(0)
        partes = _CDATA.findall(contenido)
        resto = _CDATA.sub("", contenido)
        if partes and not resto.strip():
            interno = "".join(partes)
            nuevo, cambios = funcion(interno)
            if not cambios:
                return m.group(0)
            total += cambios
            return abre + a_cdata(nuevo) + cierra
        if partes:
            return m.group(0)  # mezcla de CDATA y texto escapado: no se arriesga
        nuevo, cambios = funcion(_desescapar_xml(contenido))
        if not cambios:
            return m.group(0)
        total += cambios
        return abre + a_cdata(nuevo) + cierra

    return _TEXTO_XML.sub(reemplazar, xml), total


def transformar_archivo(
    contenido: str,
    formato: str,
    *,
    fullwidth: bool | None = True,
    espacios: bool = True,
    saltos: bool = True,
) -> tuple[str, int]:
    """Transforma el código de un archivo completo según su formato (`gift`, `xml` o `md`)."""
    if formato == "xml":
        return transformar_textos_xml(
            contenido,
            lambda t: transformar_codigo(t, contexto="xml", fullwidth=fullwidth, espacios=espacios, saltos=saltos),
        )
    contexto = "gift" if formato == "gift" else "xml"
    return transformar_codigo(contenido, contexto=contexto, fullwidth=fullwidth, espacios=espacios, saltos=saltos)


# ---------------------------------------------------------------------------
# Guardas ``` solas en su línea
# ---------------------------------------------------------------------------

_GUARDA = re.compile(r"`{3,}")
# La marca de lenguaje va pegada a la guarda que abre («```c», «```python»): la palabra
# pegada a la apertura siempre es la marca, aunque le siga código en la misma línea.
_ETIQUETA = re.compile(r"[A-Za-z][\w+#.-]*")


def aislar_guardas(texto: str) -> tuple:
    """Deja cada guarda ``` sola en su línea. (texto, líneas cambiadas).

    El texto pegado antes de una guarda sube a su propia línea y el que la sigue baja a
    la siguiente: «Dado el código ```c» queda «Dado el código» y «```c»; «return 0;```
    y luego» queda «return 0;», «```» y «y luego». La guarda que abre conserva su
    etiqueta de lenguaje; la que cierra no lleva nada. Apertura y cierre se alternan de
    izquierda a derecha, como en el resto del módulo; si el texto tiene una cantidad
    impar de guardas no se toca (no se sabe cuál abre y cuál cierra, y la marca de
    lenguaje podría quedar tomada como texto pegado a un cierre).
    """
    if "```" not in texto or len(_GUARDA.findall(texto)) % 2:
        return texto, 0
    salida: list = []
    abierto = False
    cambios = 0
    for linea in texto.split("\n"):
        if "```" not in linea:
            salida.append(linea)
            continue
        piezas: list = []
        resto = linea
        while True:
            m = _GUARDA.search(resto)
            if not m:
                if resto.strip() or not piezas:
                    piezas.append(resto)
                break
            antes, guarda, despues = resto[:m.start()], m.group(), resto[m.end():]
            if antes.strip():
                piezas.append(antes.rstrip())
            if abierto:
                piezas.append(guarda)
            else:
                etiqueta = ""
                m_et = _ETIQUETA.match(despues)
                if m_et:
                    etiqueta, despues = m_et.group(), despues[m_et.end():]
                piezas.append(guarda + etiqueta)
            abierto = not abierto
            resto = despues.lstrip()
            if not resto:
                break
        if piezas != [linea]:
            cambios += 1
        salida.extend(piezas)
    return "\n".join(salida), cambios


def aislar_guardas_archivo(contenido: str) -> tuple:
    """`aislar_guardas` en cada `<text>` de un Moodle XML. (contenido, cambios)."""
    return transformar_textos_xml(contenido, aislar_guardas)


# ---------------------------------------------------------------------------
# Lenguaje de los bloques ```
# ---------------------------------------------------------------------------

_SEÑALES_LENGUAJE = (
    ("java", re.compile(r"System\.out|public\s+(?:static\s+)?(?:class|void)|String\[\]|\bimport\s+java\.|"
                        r"\bnew\s+[A-Z]\w*\s*\(|@Override|\bextends\b|\bimplements\b")),
    ("c", re.compile(r"#include|#define|\bprintf\s*\(|\bscanf\s*\(|\bmalloc\s*\(|\bfree\s*\(|\bsizeof\b|"
                     r"\bint\s+main\s*\(|->|\bstruct\s+\w+|\btypedef\b|\bNULL\b|\bchar\s*\*")),
    ("python", re.compile(r"^\s*def\s+\w+\(.*\):\s*$|^\s*import\s+\w+\s*$|\bprint\(|^\s*elif\b|:\s*$", re.M)),
)


def detectar_lenguaje(codigo: str) -> Optional[str]:
    """c, java o python según el contenido (restaurado a ASCII); None si no se puede decidir."""
    plano = transformar_fragmento(codigo, contexto="xml", fullwidth=False)
    for lenguaje, patron in _SEÑALES_LENGUAJE:
        if patron.search(plano):
            return lenguaje
    return None


def etiquetar_lenguaje(texto: str, por_defecto: Optional[str] = None, contexto: str = "xml") -> tuple:
    """Agrega la etiqueta de lenguaje a los bloques ``` que no la tienen. (texto, cambios).

    Los bloques se emparejan como en el resto del módulo (apertura y cierre, de izquierda
    a derecha): el ``` que cierra un bloque nunca se toma por la apertura de otro.
    """
    cambios = 0

    def etiquetar(m: re.Match) -> str:
        nonlocal cambios
        if not m.group("fence") or m.group("lang").strip():
            return m.group(0)
        lenguaje = detectar_lenguaje(m.group("bloque")) or por_defecto
        if not lenguaje:
            return m.group(0)
        cambios += 1
        return f"```{lenguaje}\n{m.group('bloque')}```"

    return _SECCIONES[contexto].sub(etiquetar, texto), cambios


def etiquetar_lenguaje_archivo(contenido: str, formato: str, por_defecto: Optional[str] = None) -> tuple:
    if formato == "xml":
        return transformar_textos_xml(contenido, lambda t: etiquetar_lenguaje(t, por_defecto))
    return etiquetar_lenguaje(contenido, por_defecto, "gift")


def backticks_sin_cerrar(texto: str, contexto: str = "xml") -> bool:
    """Un ``` o un ` que no forma parte de ninguna sección de código: queda sin pareja y
    el código se come el resto del texto. Los backticks dentro de un bloque o de código
    en línea (`char c = '`';`) son contenido, no marcas."""
    return "`" in _SECCIONES[contexto].sub(" ", texto)


# ---------------------------------------------------------------------------
# Diagnóstico (para `health`)
# ---------------------------------------------------------------------------

# Lo que rompe (o cambia) una pregunta GIFT si aparece crudo en el código: llaves y
# marcadores de respuesta, la barra invertida (`\n` se importa como salto de línea) y
# el comentario `//` al comienzo de una línea.
_CONFLICTO_GIFT = re.compile(r"[{}=~#\\]|^\s*//", re.M)


def diagnosticar_codigo(texto: str, contexto: str = "xml") -> dict:
    """Cuenta secciones de código sin proteger o con marcas no canónicas.

    El criterio es el mismo en ambos formatos, para que un banco XML pueda pasar a
    GIFT sin romperse:

    - `sin_proteger`: código con caracteres que GIFT interpretaría (sin escapar).
    - `variantes`: marcas históricas (U+2007, NBSP, U+037E…) en lugar de `·` y `；`.
    - `lineas_vacias`: líneas en blanco dentro del código (en GIFT cortan la pregunta).
    - `comentarios`: secciones con líneas que empiezan con `//` sin proteger (GIFT y
      Moodle las descartan como comentarios: el código se muestra sin ellas).
    - `sin_lenguaje`: bloques ``` sin etiqueta de lenguaje (sin resaltado en Moodle).
    """
    resultado = {"secciones": 0, "sin_proteger": 0, "variantes": 0, "lineas_vacias": 0,
                 "comentarios": 0, "sin_lenguaje": 0}
    for m in _SECCIONES[contexto].finditer(texto):
        if m.group("fence"):
            codigo, html, multilinea = m.group("bloque"), False, True
            if not m.group("lang").strip():
                resultado["sin_lenguaje"] += 1
        elif m.group("abre"):
            codigo, html, multilinea = m.group("html"), True, m.group("tag").lower() == "pre"
        else:
            codigo, html, multilinea = m.group("linea"), False, False
        resultado["secciones"] += 1
        plano = _sin_entidades(codigo) if html else codigo
        if contexto == "gift":
            plano = _ESCAPE_GIFT.sub("", plano)
        if _CONFLICTO_GIFT.search(plano):
            resultado["sin_proteger"] += 1
        if any(c in _VARIANTES_A_CANONICA for c in codigo):
            resultado["variantes"] += 1
        if multilinea and re.search(r"\n[ \t]*\n", codigo):
            resultado["lineas_vacias"] += 1
        if re.search(r"(?m)^[ \t]*//", plano):
            resultado["comentarios"] += 1
    return resultado
