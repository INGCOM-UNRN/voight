"""Resaltado de sintaxis de C en HTML con CSS en línea, para Moodle (`voight fix highlight`, QoL #628).

La vista de cuestionarios de Moodle muestra los bloques ``` sin colores, y un resaltador del
navegador (highlight.js, Prism) no corre ahí: no se pueden cargar scripts en una pregunta. Acá cada
bloque C se convierte en un `<pre>` con un `<span style="color:…">` por token: no depende de nada
en el navegador ni del tema de Moodle (los colores van en el atributo `style`, que el filtro HTML
de Moodle conserva).

En un texto con `format="markdown"` el bloque queda como HTML crudo entre líneas en blanco, que el
Markdown de Moodle (PHP Markdown Extra) deja pasar tal cual; el resto del texto no cambia. Sólo
para Moodle XML: en GIFT el `#` y los `:` de los estilos son sintaxis.
"""
from __future__ import annotations

import html
import re
from typing import List, Tuple

from voight.core.codigo import detectar_lenguaje, transformar_fragmento

# Paleta del tema claro de GitHub: legible sobre el fondo blanco de la vista de cuestionario.
COLORES = {
    "comentario": "color:#6a737d;font-style:italic",
    "cadena": "color:#032f62",
    "preprocesador": "color:#d73a49",
    "palabra_clave": "color:#d73a49;font-weight:bold",
    "tipo": "color:#005cc5",
    "numero": "color:#005cc5",
    "funcion": "color:#6f42c1",
}
ESTILO_PRE = ("background:#f6f8fa;color:#24292e;padding:0.75em 1em;border-radius:6px;overflow-x:auto;"
              "font-family:Consolas,Menlo,'DejaVu Sans Mono',monospace;font-size:0.9em;line-height:1.45;"
              "white-space:pre")

PALABRAS_CLAVE = {
    "if", "else", "for", "while", "do", "switch", "case", "default", "break", "continue", "return", "goto",
    "sizeof", "typedef", "static", "extern", "const", "volatile", "register", "inline", "restrict",
    "_Static_assert", "_Alignof", "_Noreturn", "NULL", "true", "false",
}
TIPOS = {
    "void", "char", "short", "int", "long", "float", "double", "signed", "unsigned", "struct", "union",
    "enum", "bool", "_Bool", "size_t", "ssize_t", "ptrdiff_t", "FILE", "int8_t", "int16_t", "int32_t",
    "int64_t", "uint8_t", "uint16_t", "uint32_t", "uint64_t", "intptr_t", "uintptr_t",
}

_TOKENS = re.compile(
    r"(?P<comentario>/\*.*?(?:\*/|$)|//[^\n]*)"
    r"|(?P<preprocesador>^[ \t]*#[^\n]*)"
    r"|(?P<cadena>\"(?:\\.|[^\"\\\n])*\"?|'(?:\\.|[^'\\\n])*'?)"
    r"|(?P<numero>\b(?:0[xX][0-9a-fA-F]+|\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+)[uUlLfF]*\b)"
    r"|(?P<identificador>\b[A-Za-z_]\w*\b)",
    re.S | re.M,
)


def resaltar_c(codigo: str) -> str:
    """El código C como HTML: `<pre style=…><code>` con un `<span style=…>` por token."""
    partes: List[str] = []
    ultimo = 0
    for m in _TOKENS.finditer(codigo):
        partes.append(html.escape(codigo[ultimo:m.start()], quote=False))
        clase = m.lastgroup or ""
        texto = m.group(0)
        if clase == "identificador":
            if texto in PALABRAS_CLAVE:
                clase = "palabra_clave"
            elif texto in TIPOS:
                clase = "tipo"
            elif re.match(r"\s*\(", codigo[m.end():]):
                clase = "funcion"
            else:
                clase = ""
        escapado = html.escape(texto, quote=False)
        partes.append(f'<span style="{COLORES[clase]}">{escapado}</span>' if clase else escapado)
        ultimo = m.end()
    partes.append(html.escape(codigo[ultimo:], quote=False))
    # La clase identifica el bloque: `voight health` y `fix clean-html` no tratan sus estilos como HTML obsoleto.
    return f'<pre class="voight-resaltado" style="{ESTILO_PRE}"><code>{"".join(partes).rstrip()}</code></pre>'


_FENCE = re.compile(r"(?m)^(?P<sangria>[ \t]*)```(?P<lang>[^\n`]*)\n(?P<bloque>.*?)```[ \t]*$", re.S)
_LENGUAJES_C = {"c", "h"}


def resaltar_texto(texto: str) -> Tuple[str, int]:
    """Cambia cada bloque ``` de C del texto por su HTML resaltado (rodeado de líneas en blanco)."""
    cambios = 0

    def reemplazar(m: re.Match) -> str:
        nonlocal cambios
        etiqueta = m.group("lang").strip().lower()
        if etiqueta not in _LENGUAJES_C and not (etiqueta == "" and detectar_lenguaje(m.group("bloque")) == "c"):
            return m.group(0)
        codigo = transformar_fragmento(m.group("bloque"), contexto="xml", fullwidth=False).replace("↵", "")
        cambios += 1
        return f"\n\n{resaltar_c(codigo)}\n\n"

    nuevo = _FENCE.sub(reemplazar, texto)
    return (re.sub(r"\n{3,}", "\n\n", nuevo).strip("\n") + ("\n" if texto.endswith("\n") else "")
            if cambios else texto), cambios


def resaltar_xml(xml: str) -> Tuple[str, int]:
    """Resalta los bloques C de cada `<text>` de un Moodle XML. Devuelve el XML y cuántos bloques cambió."""
    from voight.core.codigo import transformar_textos_xml

    return transformar_textos_xml(xml, resaltar_texto)
