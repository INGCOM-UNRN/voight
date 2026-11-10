"""Formato estándar de bancos GIFT y Moodle XML, y transformación del código.

GIFT: comentarios, `::Título::`, enunciado, `{` y `}` en líneas propias y una opción
por línea con 4 espacios de sangría. Moodle XML: sangría de 2 espacios y todo `<text>`
con contenido en CDATA. En ambos, los `|` de los bloques ```tabla quedan alineados. En ambos, `correct_first` ordena las opciones de opción
múltiple por porcentaje (la correcta primero). La transformación del código
(fullwidth y marcas `·`/`↵`) vive en `voight.core.codigo`.
"""

import re
import unicodedata
import xml.etree.ElementTree as ET

from voight.core.codigo import aislar_guardas, transformar_archivo, transformar_codigo
from voight.core.formulas import proteger_bloques, restaurar
from voight.core.gift_semantics import _extraer_ultimo_grupo_llaves, corta_en_blanco

_BLOQUE_TABLA = re.compile(r"(?P<valla>`{3,}|~{3,})[ \t]*tabla[ \t]*\n(?P<cuerpo>.*?\n)(?P<cierre>[ \t]*(?P=valla))", re.S | re.I)
_SEPARADOR = re.compile(r":?-+:?")


# ---------------------------------------------------------------------------
# GIFT
# ---------------------------------------------------------------------------

def _bloques_gift(content: str) -> list[str]:
    """Separa las preguntas como el parser (ver `corta_en_blanco`): el código con líneas
    en blanco queda en su pregunta y una pregunta sin cerrar no se traga las siguientes."""
    lineas = proteger_bloques(content).split("\n")
    bloques: list[str] = []
    actual: list[str] = []
    for i, linea in enumerate(lineas):
        if not linea.strip():
            if not actual:
                continue
            if corta_en_blanco("\n".join(actual), lineas, i):
                bloques.append("\n".join(actual))
                actual = []
            else:
                actual.append("")
            continue
        actual.append(linea)
    if actual:
        bloques.append("\n".join(actual))
    return [restaurar(b) for b in bloques]


def _codigo_abierto(texto: str) -> bool:
    """True si el texto deja abierto un bloque ``` o un código en línea `...`."""
    if texto.count("```") % 2:
        return True
    return texto.replace("```", "").count("`") % 2 == 1


def _peso_opcion(opcion: str) -> float:
    """Porcentaje de una línea de opción GIFT: `=` 100, `~` 0, `~%n%` / `=%n%` n."""
    m = re.match(r"^([=~])\s*%(-?\d+(?:\.\d+)?)%", opcion)
    if m:
        return float(m.group(2))
    return 100.0 if opcion.startswith("=") else 0.0


def _partir_opciones(opcion: str) -> list[str]:
    """Separa opciones escritas en la misma línea (`=a ~b ####fb`) donde el parser las
    separa: en cada `=` o `~` y en el `####` de la retroalimentación general, sin
    escapar y fuera del código."""
    partes, inicio, en_codigo, i = [], 0, False, 0
    while i < len(opcion):
        c = opcion[i]
        if c == "\\":
            i += 2
            continue
        if opcion.startswith("```", i):
            en_codigo = not en_codigo
            i += 3
            continue
        if c == "`":
            en_codigo = not en_codigo
        elif opcion.startswith("####", i) and i > 0 and not en_codigo:
            partes.append(opcion[inicio:i].rstrip())
            inicio = i
            i += 4
            continue
        elif c in "=~" and i > 0 and not en_codigo and not opcion.startswith("####", inicio):
            partes.append(opcion[inicio:i].rstrip())
            inicio = i
        i += 1
    partes.append(opcion[inicio:])
    return [p for p in partes if p.strip()]


def _opciones_gift(answers_block: str) -> list[str]:
    """Una entrada por opción; las líneas de continuación se unen a su opción.

    El código dentro de una opción conserva sus saltos de línea y su sangría.
    """
    opciones: list[str] = []
    actual = ""
    for cruda in answers_block.splitlines():
        if actual and _codigo_abierto(actual):
            actual += "\n" + cruda.rstrip()
            continue
        linea = cruda.strip()
        if not linea:
            continue
        if linea[0] in ('=', '~', '#', '{'):
            if actual:
                opciones.append(actual)
            actual = linea
        elif actual:
            actual += " " + linea
        else:
            actual = linea
    if actual:
        opciones.append(actual)
    if answers_block.startswith("#") or "->" in answers_block:
        return opciones  # numérica y emparejamiento conservan su disposición
    return [parte for opcion in opciones for parte in _partir_opciones(opcion)]


def format_gift_content(content: str, correct_first: bool = False) -> str:
    """
    Formatea el contenido de un archivo GIFT según las reglas estandarizadas.
    """
    formatted_questions = []

    for q in _bloques_gift(content.strip()):
        # Extraer comentarios iniciales
        comments = []
        q_lines = q.splitlines()
        content_start_idx = 0
        for line in q_lines:
            if line.strip().startswith('//') or line.strip().startswith('$'):
                comments.append(line.strip())
                content_start_idx += 1
            elif not line.strip():
                content_start_idx += 1
            else:
                break

        remaining_content = "\n".join(q_lines[content_start_idx:]).strip()

        # Extraer título
        title = ""
        title_match = re.match(r'^::(.*?)::(.*)', remaining_content, re.DOTALL)
        if title_match:
            title = f"::{title_match.group(1).strip()}::"
            remaining_content = title_match.group(2).strip()

        # El bloque de respuestas es el ÚLTIMO grupo de llaves balanceado: el código
        # del enunciado puede tener llaves propias.
        grupo = _extraer_ultimo_grupo_llaves(remaining_content)
        if grupo is None:
            stem, answers_block = remaining_content, None
        else:
            stem, answers_block = grupo[0].strip(), grupo[1].strip()
            fuera_de_codigo = re.sub(r"```.*?```|`[^`]*`", "", stem, flags=re.DOTALL)
            if re.search(r"(?<!\\)\{", fuera_de_codigo):
                # Cloze (respuestas embebidas en el enunciado): se deja como está.
                stem, answers_block = remaining_content, None

        parts = list(comments)
        if title:
            parts.append(title)
        if stem:
            parts.append(stem)

        if answers_block is not None:
            ans_lines = _opciones_gift(answers_block)

            # Reordenar si correct_first es True (solo para MC): por porcentaje, de
            # mayor a menor; la retroalimentación general (####) queda al final.
            if correct_first:
                # La retroalimentación escrita en su propia línea (`#...`) viaja con su opción.
                unidades: list[list[str]] = []
                for a in ans_lines:
                    if a.startswith("#") and not a.startswith("####") and unidades and unidades[-1][0][0] in "=~":
                        unidades[-1].append(a)
                    else:
                        unidades.append([a])
                opciones = [u for u in unidades if u[0][0] in "=~"]
                otras = [u for u in unidades if u[0][0] not in "=~"]
                pesos = [_peso_opcion(u[0]) for u in opciones]
                if any(p > 0 for p in pesos) and any(p <= 0 for p in pesos):
                    ordenadas = sorted(opciones, key=lambda u: _peso_opcion(u[0]), reverse=True)
                    ans_lines = [linea for u in ordenadas + otras for linea in u]

            parts.append("{")
            parts.extend("    " + a for a in ans_lines)
            parts.append("}")

        formatted_questions.append("\n".join(parts))

    return "\n\n".join(formatted_questions) + "\n"


# ---------------------------------------------------------------------------
# Moodle XML
# ---------------------------------------------------------------------------

_CD_ABRE = "\ue000"
_CD_CIERRA = "\ue001"


def _desescapar_marcado(m: re.Match) -> str:
    texto = m.group(1).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return "<![CDATA[" + texto.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def format_xml_content(content: str, correct_first: bool = False) -> str:
    """Formatea un archivo Moodle XML: sangría de 2 espacios, `<text>` en CDATA y cada
    guarda ``` sola en su línea (el texto pegado antes sube y el de después baja).

    Conserva los comentarios. Con `correct_first`, en las preguntas de opción múltiple
    las respuestas quedan ordenadas por fracción (la correcta primero).
    """
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    raiz = ET.fromstring(content, parser=parser)

    if correct_first:
        for pregunta in raiz.iter("question"):
            if pregunta.get("type") != "multichoice":
                continue
            respuestas = pregunta.findall("answer")
            if len(respuestas) < 2:
                continue
            posicion = list(pregunta).index(respuestas[0])
            for r in respuestas:
                pregunta.remove(r)

            def fraccion(r):
                try:
                    return float(r.get("fraction", "0"))
                except ValueError:
                    return 0.0

            for i, r in enumerate(sorted(respuestas, key=fraccion, reverse=True)):
                pregunta.insert(posicion + i, r)

    for texto in raiz.iter("text"):
        if texto.text and texto.text.strip():
            texto.text = _CD_ABRE + aislar_guardas(texto.text)[0] + _CD_CIERRA

    ET.indent(raiz, space="  ")
    # `<text></text>` como en las exportaciones de Moodle 4 (no `<text />`).
    xml = ET.tostring(raiz, encoding="unicode", short_empty_elements=False)
    xml = re.sub(f"{_CD_ABRE}(.*?){_CD_CIERRA}", _desescapar_marcado, xml, flags=re.DOTALL)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml + "\n"


def _ancho(texto: str) -> int:
    """Columnas que ocupa un texto en una fuente monoespaciada: fullwidth ocupa dos."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in texto
               if not unicodedata.combining(c))


def _celdas(fila: str) -> list[str]:
    """Las celdas de una fila `| a | b |`: un `|` escapado o en código no separa."""
    fila = fila.strip()
    fila = fila[1:] if fila.startswith("|") else fila
    celdas, actual, en_codigo, i = [], "", False, 0
    while i < len(fila):
        c = fila[i]
        if c == "\\" and i + 1 < len(fila):
            actual += fila[i:i + 2]
            i += 2
            continue
        if c == "`":
            en_codigo = not en_codigo
        if c == "|" and not en_codigo:
            celdas.append(actual.strip())
            actual = ""
        else:
            actual += c
        i += 1
    if actual.strip():
        celdas.append(actual.strip())
    return celdas


def _separador(celda: str, ancho: int) -> str:
    """`---`, `:---`, `---:` o `:---:` del ancho de la columna."""
    izquierda, derecha = ":" * celda.startswith(":"), ":" * celda.endswith(":")
    return izquierda + "-" * (ancho - len(izquierda) - len(derecha)) + derecha


def _alinear_filas(filas: list[str]) -> list[str]:
    tabla = [_celdas(fila) for fila in filas]
    columnas = max(len(fila) for fila in tabla)
    tabla = [fila + [""] * (columnas - len(fila)) for fila in tabla]
    separadores = [i for i, fila in enumerate(tabla) if all(_SEPARADOR.fullmatch(c) or not c for c in fila)]
    anchos = [max(3, *(_ancho(fila[j]) for i, fila in enumerate(tabla) if i not in separadores))
              for j in range(columnas)]
    return ["| " + " | ".join(_separador(c or "-", a) if i in separadores else c + " " * (a - _ancho(c))
                              for c, a in zip(fila, anchos)) + " |"
            for i, fila in enumerate(tabla)]


def alinear_tablas(contenido: str) -> str:
    """Alinea los `|` de cada bloque ```tabla; sus comentarios de opciones quedan como están."""
    def alinear(m: re.Match) -> str:
        lineas = m.group("cuerpo").rstrip("\n").split("\n")
        filas = [i for i, linea in enumerate(lineas) if "|" in linea and not linea.lstrip().startswith("//")]
        if not filas:
            return m.group(0)
        for i, fila in zip(filas, _alinear_filas([lineas[i] for i in filas])):
            lineas[i] = fila
        return m.group(0)[:m.start("cuerpo") - m.start()] + "\n".join(lineas) + "\n" + m.group("cierre")

    return _BLOQUE_TABLA.sub(alinear, contenido)


def format_content(content: str, formato: str, correct_first: bool = False) -> str:
    """Formatea un archivo según su formato ('gift' o 'xml')."""
    if formato == "xml":
        return alinear_tablas(format_xml_content(content, correct_first=correct_first))
    return alinear_tablas(format_gift_content(content, correct_first=correct_first))


# ---------------------------------------------------------------------------
# Código (compatibilidad: la lógica está en voight.core.codigo)
# ---------------------------------------------------------------------------

def fix_code_indentation(content: str, formato: str = "md") -> tuple[str, int]:
    """
    Marca la indentación del código con '·' (un punto por espacio) dentro de las
    secciones de código. Devuelve el contenido y la cantidad de secciones modificadas.
    """
    return transformar_archivo(content, formato, fullwidth=None, espacios=True, saltos=False)


def convert_code_block_content(content: str, to_normal: bool = True) -> str:
    """
    Convierte el contenido de un bloque de código entre normal y fullwidth.
    """
    texto, _ = transformar_codigo(f"```\n{content}```", fullwidth=not to_normal, espacios=False, saltos=False)
    return texto[4:-3]


def convert_markdown_code_blocks(text: str, to_normal: bool = True) -> tuple[str, int]:
    """
    Convierte caracteres especiales en bloques de código markdown.
    """
    return transformar_codigo(text, fullwidth=not to_normal, espacios=False, saltos=False)


def process_xml_cdata(text: str, to_normal: bool = True) -> tuple[str, int]:
    """
    Convierte caracteres especiales en el código de los <text> de un archivo XML.
    """
    return transformar_archivo(text, "xml", fullwidth=not to_normal, espacios=False, saltos=False)
