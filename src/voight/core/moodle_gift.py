"""Lo que impide importar un GIFT en Moodle tal cual, y su corrección.

Son las reglas de `alucard lint-gift` (`generador_examenes.gift_linter`), sin depender de él: los
metadatos van en un comentario y sin `:` (`// [tag, a, b] [category, C]`), el desarrollo es `{}` y en
la pregunta no quedan `:` sueltos. Lo que igual hay que preprocesar (diagramas y fórmulas) está exento.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple

from voight.core.formulas import fuera_de_plantuml, tramos_a_preprocesar

_VIEJA = re.compile(
    r"^[ \t]*//.*$"
    r"|[ \t]*\[(?P<clave>tags?|category):\s*(?P<valor>[^\]\n]+?)\s*\][ \t]*"
    r"|(?P<desarrollo>\{\s*desarrollo(?::(?P<tamano>\w+))?\s*\})",
    re.I | re.M)
_TAMANOS = ("pequeno", "mediano", "grande")
# Lo que puede llevar `:` en un banco: comentarios, `$CATEGORY:`, los delimitadores del título, las
# respuestas numéricas ({#3:2}) y el escape de GIFT.
_DOS_PUNTOS = re.compile(r"^[ \t]*//.*$|^[ \t]*\$CATEGORY:.*$|\{\s*#[^{}]*\}|\\:"
                         r"|^[ \t]*::(?P<titulo>.+?)::|(?P<dos_puntos>:)", re.M)
_COMENTARIO = re.compile(r"^[ \t]*//.*$", re.M)
_TAG_O_CATEGORIA = re.compile(r"\[(tag|category):\s*((?:\\\]|[^\]])*?)\s*\]", re.I)
_INICIO_PREGUNTA = re.compile(r"^[ \t]*::|(?:(?<=\n\n)|\A)[ \t]*\[(?:markdown|html)\]", re.M)


# Las marcas de corte y de números de línea: sirven para el PDF de alucarD, y un banco fusionado es para Moodle.
_CORTE_GIFT = re.compile(r"^[ \t]*//[ \t]*\[(?:corte|numerar|sin-numerar)\][ \t]*(?:\n|$)", re.I | re.M)
_CORTE_HTML = re.compile(r"(\n*)[ \t]*<!--\s*(?:corte|numerar|sin-numerar)\s*-->[ \t]*(\n*)", re.I)


def sin_cortes(texto: str) -> str:
    """El texto sin `// [corte]` ni `<!--corte-->`, ni sus pares de `numerar`; los renglones en blanco
    que separaban quedan."""
    def quitar(trozo: str) -> str:
        return _CORTE_HTML.sub(lambda m: max(m.group(1), m.group(2), key=len), _CORTE_GIFT.sub("", trozo))

    return fuera_de_plantuml(texto, quitar)


def quitar_cortes(pregunta: ET.Element) -> None:
    """Saca las marcas de todos los textos de un <question>."""
    for texto in pregunta.iter("text"):
        if texto.text:
            texto.text = sin_cortes(texto.text)


def _vieja(contenido: str) -> List[re.Match]:
    return [m for m in _VIEJA.finditer(contenido) if m.group("clave") or m.group("desarrollo")]


def _dos_puntos_sueltos(contenido: str) -> List[int]:
    exentos: List[Tuple[int, int]] = [m.span() for m in _vieja(contenido)] + tramos_a_preprocesar(contenido)
    posiciones: List[int] = []
    for m in _DOS_PUNTOS.finditer(contenido):
        if m.group("titulo"):
            posiciones += [m.start("titulo") + i for i, c in enumerate(m.group("titulo")) if c == ":"]
        elif m.group("dos_puntos"):
            posiciones.append(m.start())
    return [pos for pos in posiciones if not any(desde <= pos < hasta for desde, hasta in exentos)]


def revisar(contenido: str) -> List[str]:
    """Un renglón por cada problema: `corregir` los arregla todos."""
    def donde(pos: int) -> str:
        return f"línea {contenido[:pos].count(chr(10)) + 1}"

    problemas = []
    for m in _vieja(contenido):
        if m.group("desarrollo"):
            problemas.append(f"{donde(m.start())}: Moodle toma {m.group().strip()} como respuesta corta")
        else:
            problemas.append(f"{donde(m.start())}: Moodle toma {m.group().strip()} como texto de la pregunta")
    for comentario in _COMENTARIO.finditer(contenido):
        for m in _TAG_O_CATEGORIA.finditer(comentario.group()):
            problemas.append(f"{donde(comentario.start())}: {m.group()} lleva `:`")
    problemas += [f"{donde(pos)}: `:` suelto en la pregunta" for pos in _dos_puntos_sueltos(contenido)]
    return problemas


def _inicio_de_pregunta(contenido: str, pos: int) -> int:
    inicios = [m.start() for m in _INICIO_PREGUNTA.finditer(contenido, 0, pos)]
    if inicios:
        return inicios[-1]
    corte = contenido.rfind("\n\n", 0, pos)
    return corte + 2 if corte >= 0 else 0


def corregir(contenido: str) -> str:
    """Pasa los metadatos a un comentario arriba de la pregunta, sin `:`, `{desarrollo:grande}` a `{}`
    con su etiqueta y los `:` sueltos a `\\:`, el escape de GIFT: no se pierde al volver a convertirlo."""
    ediciones: List[Tuple[int, int, str]] = []
    etiquetas: Dict[int, List[str]] = {}
    categorias: Dict[int, str] = {}
    for m in _vieja(contenido):
        inicio = _inicio_de_pregunta(contenido, m.start())
        nuevas = etiquetas.setdefault(inicio, [])
        if m.group("desarrollo"):
            ediciones.append((m.start(), m.end(), "{}"))
            if (m.group("tamano") or "").lower() in _TAMANOS:
                nuevas.append(f"desarrollo-{m.group('tamano').lower()}")
            continue
        if m.group("clave").lower() == "category":
            categorias[inicio] = m.group("valor")
        else:
            nuevas += [tag.strip() for tag in m.group("valor").split(",") if tag.strip()]
        sola = contenido[m.start() - 1:m.start()] in ("", "\n") and contenido[m.end():m.end() + 1] == "\n"
        ediciones.append((m.start(), m.end() + sola, ""))
    for pos in {*etiquetas, *categorias}:
        marcas = ([f"[tag, {', '.join(etiquetas[pos])}]"] if etiquetas.get(pos) else [])
        marcas += [f"[category, {categorias[pos]}]"] if pos in categorias else []
        if marcas:
            ediciones.append((pos, pos, f"// {' '.join(marcas)}\n"))
    for desde, hasta, texto in sorted(ediciones, reverse=True):
        contenido = contenido[:desde] + texto + contenido[hasta:]
    contenido = _COMENTARIO.sub(
        lambda c: _TAG_O_CATEGORIA.sub(lambda m: f"[{m.group(1)}, {m.group(2)}]", c.group()), contenido)
    for pos in reversed(_dos_puntos_sueltos(contenido)):
        contenido = contenido[:pos] + "\\:" + contenido[pos + 1:]
    return contenido
