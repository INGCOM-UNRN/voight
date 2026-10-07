"""Moodle XML -> modelo unificado de preguntas (el mismo que produce el parser GIFT).

Con este parser el análisis (validate, analyze, health, duplicados) trabaja igual
sobre bancos GIFT y XML: ambos llegan como listas de `Question` / diccionarios con la
forma de `Question.to_dict()`.

Correspondencia de fracciones: una respuesta con 100 % es `is_correct` sin peso (el
`=` de GIFT); 0 % es incorrecta sin peso (`~`); cualquier otro valor queda en
`weight` (`~%50%`). En `shortanswer` y `numerical` toda fracción positiva es correcta
(`=%50%` en GIFT).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from voight.core.gift_model import Choice, FormattedText, MatchPair, Question
from voight.core.metadatos import leer_clasificacion

_FORMATOS = {
    "html": "html",
    "markdown": "markdown",
    "plain_text": "plain",
    "moodle_auto_format": "moodle",
}

_TIPOS = {
    "multichoice": "MC",
    "shortanswer": "Short",
    "truefalse": "TF",
    "matching": "Matching",
    "numerical": "Numerical",
    "essay": "Essay",
    "description": "Description",
    "cloze": "Cloze",
    "multianswer": "Cloze",
}


CAMPOS_MOODLE = ("penalty", "defaultgrade", "shuffleanswers", "answernumbering", "single")


def _texto(el: ET.Element | None, ruta: str = "text") -> str:
    if el is None:
        return ""
    t = el.find(ruta) if ruta else el
    return (t.text or "").strip() if t is not None else ""


def _formateado(el: ET.Element | None, formato_por_defecto: str = "html") -> FormattedText | None:
    """Texto con formato de un elemento con hijo <text> y atributo format; None si está vacío."""
    texto = _texto(el)
    if not texto:
        return None
    formato = (el.get("format") if el is not None else None) or formato_por_defecto
    return FormattedText(format=_FORMATOS.get(formato, formato), text=texto)


def _fraccion(ans: ET.Element) -> float:
    try:
        return float(ans.get("fraction", "0"))
    except ValueError:
        return 0.0


def _opcion(ans: ET.Element, positiva_es_correcta: bool, formato_pregunta: str) -> Choice:
    frac = _fraccion(ans)
    es_100 = abs(frac - 100.0) < 0.01
    es_0 = abs(frac) < 0.01
    correcta = es_100 or (positiva_es_correcta and frac > 0)
    return Choice(
        is_correct=correcta,
        weight=None if (es_100 or es_0) else frac,
        text=FormattedText(
            format=_FORMATOS.get(ans.get("format") or formato_pregunta, "html"),
            text=_texto(ans),
        ),
        feedback=_formateado(ans.find("feedback")),
    )


def _pregunta(q: ET.Element) -> Question:
    qtype = (q.get("type") or "").lower()

    if qtype == "category":
        return Question(type="Category", title=_texto(q.find("category")))

    qt = q.find("questiontext")
    formato = (qt.get("format") if qt is not None else None) or "html"
    tags = [t.text.strip() for t in q.findall("tags/tag/text") if t.text and t.text.strip()]
    pregunta = Question(
        type=_TIPOS.get(qtype, qtype or "Unknown"),
        title=_texto(q.find("name")) or None,
        stem=FormattedText(format=_FORMATOS.get(formato, formato), text=_texto(qt)),
        id=_texto(q, "idnumber") or None,
        tags=tags,
        global_feedback=_formateado(q.find("generalfeedback")),
    )

    pregunta.moodle = {campo: _texto(q, campo) for campo in CAMPOS_MOODLE if _texto(q, campo)}

    respuestas = q.findall("answer")
    if qtype == "multichoice":
        pregunta.choices = [_opcion(a, False, formato) for a in respuestas]
    elif qtype in ("shortanswer", "numerical"):
        pregunta.choices = [_opcion(a, True, formato) for a in respuestas]
        if qtype == "numerical":
            for opcion, ans in zip(pregunta.choices, respuestas):
                tolerancia = _texto(ans, "tolerance")
                if tolerancia and opcion.text is not None:
                    opcion.text.text = f"{opcion.text.text}:{tolerancia}"
    elif qtype == "truefalse":
        for ans in respuestas:
            valor = _texto(ans).lower()
            if valor not in ("true", "false"):
                continue
            if abs(_fraccion(ans) - 100.0) < 0.01:
                pregunta.is_true = valor == "true"
            retro = _formateado(ans.find("feedback"))
            if valor == "true":
                pregunta.true_feedback = retro
            else:
                pregunta.false_feedback = retro
    elif qtype == "matching":
        for sq in q.findall("subquestion"):
            pregunta.match_pairs.append(MatchPair(
                subquestion=FormattedText(
                    format=_FORMATOS.get(sq.get("format") or "html", "html"), text=_texto(sq)
                ),
                subanswer=_texto(sq.find("answer")),
            ))
    elif qtype in ("cloze", "multianswer"):
        pregunta.has_embedded_answers = True

    return pregunta


def parse_moodle_xml(contenido: str) -> list[Question]:
    """Parsea un documento Moodle XML (<quiz> o una <question> suelta).

    El comentario que precede a cada <question> (p. ej. el que escribe classify) aporta su
    clasificación en `metadata`, igual que los tags bloom:… / dificultad-….
    """
    raiz = ET.fromstring(contenido, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
    if raiz.tag == "question":
        return [_con_metadatos(_pregunta(raiz), "")]
    preguntas, comentario = [], ""
    for nodo in raiz:
        if nodo.tag is ET.Comment:
            comentario += " " + (nodo.text or "")
        elif nodo.tag == "question":
            preguntas.append(_con_metadatos(_pregunta(nodo), comentario))
            comentario = ""
    return preguntas


def _con_metadatos(q: Question, comentario: str) -> Question:
    q.metadata = leer_clasificacion(comentario, q.tags)
    return q


def parse_xml(contenido: str) -> dict:
    """Mismo contrato que `parse_gift`: {success, questions, questionCount} o {success, error}."""
    try:
        preguntas = parse_moodle_xml(contenido)
    except ET.ParseError as e:
        linea, columna = getattr(e, "position", (None, None))
        return {
            "success": False,
            "error": {"message": f"XML inválido: {e}", "location": {"line": linea, "column": columna}},
        }
    except Exception as e:  # noqa: BLE001 - se informa como error del archivo
        return {"success": False, "error": {"message": str(e)}}
    return {
        "success": True,
        "questions": [p.to_dict() for p in preguntas],
        "questionCount": len(preguntas),
    }


def parse_xml_file(filepath: str | Path) -> dict:
    ruta = Path(filepath)
    if not ruta.exists():
        return {"success": False, "filepath": str(ruta), "error": {"message": f"Archivo no encontrado: {ruta}"}}
    try:
        contenido = ruta.read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        return {"success": False, "filepath": str(ruta), "error": {"message": f"Error leyendo archivo: {e}"}}
    resultado = parse_xml(contenido)
    resultado["filepath"] = str(ruta)
    return resultado
