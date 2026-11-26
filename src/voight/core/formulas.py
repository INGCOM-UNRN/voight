"""Lo que Moodle no importa de un GIFT: diagramas, tablas y fórmulas `$...$`.

Un bloque de diagrama (```plantuml, ```puml, y los de dibu: ```estructura, ```statics, ```dibu) va
crudo: lleva `{ } : = #`, renglones en blanco y `//`, y ni el ancho completo ni las marcas · y ↵ del
código se le aplican. `proteger_bloques` lo esconde mientras se parte y se parsea el GIFT, y también
las opciones `// [...]` de un ```tabla.

Reconoce las fórmulas con las reglas de alucarD (`generador_examenes.matematica`), sin depender de
él: los espacios de adentro son parejos, el `$` que cierra no va seguido de un dígito y lo que está en
código no se toca, así que `$100 y $200` es texto. En HTML también valen `\\(...\\)` y `\\[...\\]`.

GIFT usa `{ } = ~ # \\` y una fórmula está llena de ellos: `proteger_gift` los esconde mientras se
parsea la pregunta y `restaurar` los repone.
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Tuple

_CODIGO = r"(?P<codigo>```.*?```|~~~.*?~~~|``[^\n]*?``|`[^`\n]*`|<pre\b.*?</pre>|<code\b.*?</code>)"
_DOLAR = r"(?P<dolar>\\\$)"
_BLOQUE = r"\$\$(?P<bloque>.+?)\$\$"
_LINEA = r"(?<![\\$\w])\$(?P<linea>[^\s$](?:(?:\\.|[^$\\\n])*(?:\\.|[^\s$\\]))?)\$(?![\d$])"
_ESPACIADA = r"(?<![\\$\w])\$[ \t]+(?P<linea3>[^\s$\d][^$\n]*?)[ \t]+\$(?![ \t]*[\d$])"
_LATEX = r"\\\[(?P<bloque2>.+?)\\\]|\\\((?P<linea2>.+?)\\\)"
# Lo que no es texto de una pregunta: `$CATEGORY: $course$/top` no es una fórmula.
_NO_ES_TEXTO = r"(?P<metadato>^[ \t]*(?:\$CATEGORY:|//)[^\n]*$)"
_ETIQUETA = r"(?P<etiqueta><[a-zA-Z/][^>]*>)"

_GIFT = re.compile("|".join((_NO_ES_TEXTO, _CODIGO, _DOLAR, _BLOQUE, _LINEA, _ESPACIADA)), re.S | re.M)
_MARKDOWN = re.compile("|".join((_CODIGO, _DOLAR, _BLOQUE, _LINEA, _ESPACIADA)), re.S)
_HTML = re.compile("|".join((_CODIGO, _ETIQUETA, _DOLAR, _BLOQUE, _LINEA, _ESPACIADA, _LATEX)), re.S)

# Los bloques de diagramas: los dibujan dibu (estructura, statics, dibu) y PlantUML (plantuml, puml).
# No son código: van crudos, sin escapes de GIFT, ancho completo ni marcas.
LENGUAJES_DIAGRAMA = ("estructura", "statics", "dibu", "plantuml", "puml")
_DIAGRAMAS = "|".join(LENGUAJES_DIAGRAMA)

_DIAGRAMA = re.compile(r"^[ \t]*(?P<valla>`{3,}|~{3,})[ \t]*(?:" + _DIAGRAMAS + r"|mermaid)[ \t]*\n.*?"
                       r"^[ \t]*(?P=valla)[ \t]*$", re.S | re.M | re.I)

_TABLA = re.compile(r"^[ \t]*(?P<valla>`{3,}|~{3,})[ \t]*tabla[ \t]*\n.*?^[ \t]*(?P=valla)[ \t]*$", re.S | re.M | re.I)

# Del área de uso privado de Unicode: no aparecen en un banco.
_ESCONDIDOS = {c: chr(0xF0000 + i) for i, c in enumerate("\\{}=~#:/")}
_RENGLON_EN_BLANCO = chr(0xF0100)
_ESCONDER = str.maketrans(_ESCONDIDOS)
_REPONER = str.maketrans({**{v: k for k, v in _ESCONDIDOS.items()}, _RENGLON_EN_BLANCO: None})

_CRUDO = re.compile(r"^(?P<abre>[ \t]*(?P<valla>`{3,}|~{3,})[ \t]*(?P<lenguaje>tabla|" + _DIAGRAMAS + r")[ \t]*\n)(?P<cuerpo>.*?)"
                    r"(?P<cierra>^[ \t]*(?P=valla)[ \t]*$)", re.S | re.M | re.I)


def fuente_de(m: re.Match) -> Tuple[str, bool] | None:
    """(LaTeX, va aparte) de una coincidencia, o None si no es una fórmula."""
    grupos = m.groupdict()
    for nombre, bloque in (("bloque", True), ("bloque2", True), ("linea", False), ("linea2", False), ("linea3", False)):
        if grupos.get(nombre) is not None:
            return html.unescape(grupos[nombre]), bloque
    return None


def reemplazar(texto: str, es_html: bool, funcion) -> str:
    """Cambia cada fórmula de un campo por `funcion(latex, va_aparte)`; `\\$` queda como un signo pesos."""
    def cambiar(m: re.Match) -> str:
        if m.group("dolar"):
            return "&#36;"
        formula = fuente_de(m)
        return m.group(0) if formula is None else funcion(*formula)

    return (_HTML if es_html else _MARKDOWN).sub(cambiar, texto)


def _sin_diagramas(contenido: str) -> str:
    return _DIAGRAMA.sub("", contenido)


def _formulas_gift(contenido: str) -> Iterator[re.Match]:
    return (m for m in _GIFT.finditer(contenido) if fuente_de(m) is not None)


def proteger_bloques(contenido: str) -> str:
    """Esconde lo que un diagrama o un ```tabla tienen que conservar; `restaurar` lo repone."""
    def esconder(m: re.Match) -> str:
        cuerpo = m.group("cuerpo")
        if m.group("lenguaje").lower() == "tabla":
            cuerpo = re.sub(r"^[ \t]*//", lambda c: c.group().translate(_ESCONDER), cuerpo, flags=re.M)
        else:
            cuerpo = re.sub(r"^[ \t]*$", _RENGLON_EN_BLANCO, cuerpo.replace("\\:", ":").translate(_ESCONDER), flags=re.M)
            cuerpo = cuerpo.removesuffix(_RENGLON_EN_BLANCO)
        return m.group("abre") + cuerpo + m.group("cierra")

    return _CRUDO.sub(esconder, contenido)


def fuera_de_plantuml(texto: str, funcion) -> str:
    """Aplica `funcion` a lo que no está en un bloque de diagrama (PlantUML o dibu), que no lleva
    escapes de GIFT."""
    salida, inicio = [], 0
    for m in _CRUDO.finditer(texto):
        if m.group("lenguaje").lower() != "tabla":
            salida += [funcion(texto[inicio:m.start()]), m.group(0)]
            inicio = m.end()
    return "".join(salida) + funcion(texto[inicio:])


def tramos_a_preprocesar(contenido: str) -> List[Tuple[int, int]]:
    """Dónde hay diagramas y fórmulas: Moodle no los importa sin preprocesar, así que su `:` no molesta."""
    return [m.span() for m in _DIAGRAMA.finditer(contenido)] + [m.span() for m in _formulas_gift(contenido)]


def proteger_gift(contenido: str) -> str:
    """Esconde las marcas de GIFT de las fórmulas. `\\=` y `\\~` son el escape que pide alucarD."""
    def esconder(m: re.Match) -> str:
        if fuente_de(m) is None:
            return m.group(0)
        return m.group(0).replace("\\=", "=").replace("\\~", "~").translate(_ESCONDER)

    return _GIFT.sub(esconder, proteger_bloques(contenido))


def restaurar(texto: str) -> str:
    return texto.translate(_REPONER)


def a_preprocesar(contenido: str) -> Dict[str, int]:
    """Cuántos diagramas, tablas y fórmulas tiene un GIFT."""
    return {"diagramas": len(_DIAGRAMA.findall(contenido)),
            "tablas": len(_TABLA.findall(contenido)),
            "formulas": sum(1 for _ in _formulas_gift(_sin_diagramas(contenido)))}


SUGERENCIA_UNIFY = ("pasalo a XML con `voight convert gift-to-xml` y fusionalo con `voight unify … -o banco.xml`, "
                    "que los convierte.")
SUGERENCIA_BACKUP = ("el backup no puede llevarlos desde GIFT: pasalo a XML con `voight convert gift-to-xml` "
                     "para que el backup contenga los diagramas.")


def avisos_gift(archivos: Iterable[Path], sugerencia: str = SUGERENCIA_UNIFY) -> List[str]:
    """Una advertencia por cada GIFT que Moodle no puede mostrar tal cual."""
    avisos = []
    for archivo in archivos:
        if Path(archivo).suffix.lower() != ".gift":
            continue
        cuenta = a_preprocesar(Path(archivo).read_text(encoding="utf-8"))
        if any(cuenta.values()):
            avisos.append(f"Advertencia: {archivo} tiene {cuenta['diagramas']} diagramas, {cuenta['tablas']} tablas y "
                          f"{cuenta['formulas']} fórmulas, que Moodle no dibuja: {sugerencia}")
    return avisos
