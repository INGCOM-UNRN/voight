"""Vistas parciales de una pregunta: al modelo se le envía sólo lo que necesita y devuelve sólo lo que cambia.

`voight ai` envía GIFT compacto (ver core/ai.py), pero mejorar únicamente el enunciado, las
opciones, la retroalimentación que falta o los distractores no necesita la pregunta entera, ni
de ida ni de vuelta:

| Clase | Se envía | Vuelve |
|:--|:--|:--|
| ``enunciado`` (improve --parte enunciado) | el enunciado | el enunciado |
| ``respuestas`` (improve --parte respuestas) | el enunciado y las opciones, sin retroalimentación | las opciones |
| ``feedback`` | el enunciado, las opciones y qué retroalimentación falta | sólo la que falta |
| ``distractors`` | el enunciado y las opciones, sin retroalimentación | sólo los distractores nuevos |

Lo que devuelve el modelo se aplica sobre una copia de la pregunta original y se serializa a
GIFT, así que sigue el mismo camino (validación, convenciones del código, escritura en GIFT o
XML) que una respuesta completa. El código se envía en ASCII y se vuelve a proteger al aplicarlo.
"""
from __future__ import annotations

import copy
import re
from typing import List, Optional, Tuple

from voight.core.codigo import transformar_codigo
from voight.core.converter import question_to_gift
from voight.core.gift_model import Choice, FormattedText, Question

PARTES = ("todo", "enunciado", "respuestas")


def clase_de(mode: str, parte: str = "todo") -> Optional[str]:
    """La vista que corresponde al modo (None: se envía la pregunta GIFT completa)."""
    if mode == "improve" and parte in ("enunciado", "respuestas"):
        return parte
    if mode in ("feedback", "distractors"):
        return mode
    return None


def aplica(clase: Optional[str], q: Question) -> bool:
    """Las vistas de opciones sólo tienen sentido con opciones (o verdadero/falso para feedback)."""
    if clase in ("respuestas", "distractors"):
        return bool(q.choices)
    if clase == "enunciado":
        return q.stem is not None and bool((q.stem.text or "").strip())
    return True  # feedback: opciones, verdadero/falso o sólo la general


def _ascii(texto: str) -> str:
    return transformar_codigo(texto or "", contexto="xml", fullwidth=False)[0]


def _proteger(texto: str) -> str:
    return transformar_codigo(texto, contexto="gift", fullwidth=True, espacios=False, saltos=False, escapes=False)[0]


def _hay(ft: Optional[FormattedText]) -> bool:
    return ft is not None and bool((ft.text or "").strip())


def _marca(c: Choice) -> str:
    if c.weight is not None and c.weight not in (0, 100):
        peso = int(c.weight) if float(c.weight).is_integer() else c.weight
        return f"{'=' if c.is_correct else '~'}%{peso}%"
    return "=" if c.is_correct or (c.weight or 0) > 0 else "~"


def _opciones(q: Question, numeradas: bool = False) -> List[str]:
    return [f"{i}. " * numeradas + f"{_marca(c)}{_ascii(c.text.text if c.text else '')}" for i, c in
            enumerate(q.choices, 1)]


def vista(q: Question, clase: str) -> str:
    """El texto que se envía para la pregunta `q` (en su representación protegida, de `_interpretar`)."""
    enunciado = _ascii(q.stem.text if q.stem else "")
    if clase == "enunciado":
        return enunciado
    if clase == "respuestas":
        return "\n".join(["ENUNCIADO (no lo cambies): " + enunciado, *_opciones(q)])
    if clase == "distractors":
        return "\n".join(["ENUNCIADO: " + enunciado, *_opciones(q)])
    # feedback
    if q.type == "TF":
        lineas = ["ENUNCIADO: " + enunciado, f"RESPUESTA CORRECTA: {'Verdadero' if q.is_true else 'Falso'}"]
        faltan = [x for x, ft in (("V", q.true_feedback), ("F", q.false_feedback)) if not _hay(ft)]
    else:
        lineas = ["ENUNCIADO: " + enunciado, *_opciones(q, numeradas=True)]
        faltan = [str(i) for i, c in enumerate(q.choices, 1) if not _hay(c.feedback)]
    if not _hay(q.global_feedback):
        faltan.append("G")
    return "\n".join([*lineas, "FALTA: " + ", ".join(faltan)])


def instruccion(clase: str, objetivo: int) -> Tuple[str, str]:
    """(qué hacer, qué devolver) para la clase."""
    if clase == "enunciado":
        return ("Sos experto en pedagogía. Mejorá la claridad, la gramática y la calidad pedagógica de cada "
                "ENUNCIADO de pregunta de opción múltiple sin cambiar lo que pregunta ni su respuesta.",
                "sólo el enunciado mejorado de cada una")
    if clase == "respuestas":
        return ("Sos experto en pedagogía y en el formato GIFT de Moodle. Mejorá la redacción de las opciones de "
                "cada pregunta (= correcta, ~ incorrecta, ~%n% parcial) sin cambiar cuál es correcta ni su "
                "significado; el enunciado es sólo contexto.",
                "sólo las opciones, una por línea, en el mismo orden, con la misma cantidad y la misma marca "
                "(=, ~ o ~%n%) al comienzo")
    if clase == "feedback":
        return ("Sos experto en pedagogía. Escribí sólo la retroalimentación que indica FALTA: para cada opción "
                "numerada, una explicación breve de por qué es correcta o incorrecta (el error conceptual que "
                "revela); V y F, la que ve quien responde Verdadero o Falso; G, la retroalimentación general.",
                "una línea por cada retroalimentación que falta, con la forma 'n# texto' (o 'V# …', 'F# …', "
                "'G# …')")
    return (f"Sos experto en pedagogía y en el formato GIFT de Moodle. Proponé distractores plausibles, basados "
            f"en errores conceptuales comunes del tema, para que cada pregunta llegue a {objetivo} opciones en "
            "total. Si la correcta es mucho más larga que los distractores, los nuevos deben tener un largo "
            "parecido al de la correcta.",
            "sólo los distractores nuevos, uno por línea, con la forma '~texto' o '~texto # retroalimentación'")


_ITEM_OPCION = re.compile(r"^(=|~)(%-?\d+(?:\.\d+)?%)?", re.MULTILINE)
_ITEM_FEEDBACK = re.compile(r"^\s*(\d+|[VFG])\s*[#:.)-]\s*", re.MULTILINE | re.IGNORECASE)


def _items(bloque: str, patron: re.Pattern) -> List[Tuple[re.Match, str]]:
    """Cada ítem empieza en una línea que coincide con `patron` y sigue hasta el próximo (puede tener
    varias líneas, como un bloque de código)."""
    marcas = list(patron.finditer(bloque))
    return [(m, bloque[m.end():(marcas[i + 1].start() if i + 1 < len(marcas) else len(bloque))].strip())
            for i, m in enumerate(marcas)]


def reconstruir(q: Question, clase: str, bloque: str) -> Optional[str]:
    """La pregunta completa en GIFT (protegido) con lo que devolvió el modelo; None si no se entiende."""
    bloque = bloque.strip()
    # Restos de los marcadores de lote (un modelo chico que inventa o deforma «--- PREGUNTA n ---»).
    if not bloque or re.search(r"^-{3,}\s*PREGU", bloque, re.MULTILINE | re.IGNORECASE):
        return None
    nueva = copy.deepcopy(q)
    if clase == "enunciado":
        bloque = re.sub(r"^ENUNCIADO[^:]*:\s*", "", bloque)
        nueva.stem = FormattedText(format=q.stem.format if q.stem else "moodle", text=_proteger(bloque))
    elif clase == "respuestas":
        items = _items(bloque, _ITEM_OPCION)
        if [m.group(0) for m, _ in items] != [_marca(c) for c in q.choices] or any(not t for _, t in items):
            return None
        for c, (_, texto) in zip(nueva.choices, items, strict=True):
            c.text = FormattedText(format=c.text.format if c.text else "moodle", text=_proteger(texto))
    elif clase == "distractors":
        for m, texto in _items(bloque, _ITEM_OPCION):
            if m.group(0) != "~" or not texto:
                continue  # sólo distractores nuevos
            # «~texto #retroalimentación» (como en GIFT); un # dentro de `código` no separa.
            partes = re.split(r"\s#\s*", texto, maxsplit=1)
            texto, feedback = partes[0], (partes[1] if len(partes) > 1 else "")
            nueva.choices.append(Choice(is_correct=False, text=FormattedText(text=_proteger(texto.strip())),
                                        feedback=FormattedText(text=_proteger(feedback.strip()))
                                        if feedback.strip() else None))
    else:  # feedback
        for m, texto in _items(bloque, _ITEM_FEEDBACK):
            if not texto:
                continue
            clave = m.group(1).upper()
            ft = FormattedText(text=_proteger(texto))
            if clave == "G":
                nueva.global_feedback = ft
            elif clave == "V" and q.type == "TF":
                nueva.true_feedback = ft
            elif clave == "F" and q.type == "TF":
                nueva.false_feedback = ft
            elif clave.isdigit() and 1 <= int(clave) <= len(nueva.choices):
                nueva.choices[int(clave) - 1].feedback = ft
    return question_to_gift(nueva)


def salida_esperada(q: Question, clase: str) -> int:
    """Caracteres aproximados de lo que vuelve (para estimar tokens de salida)."""
    if clase == "enunciado":
        return len(vista(q, clase))
    if clase == "respuestas":
        return sum(len(o) for o in _opciones(q))
    if clase == "distractors":
        return 2 * max((len(o) for o in _opciones(q)), default=20)
    faltan = len(vista(q, clase).rsplit("FALTA: ", 1)[-1].split(","))
    return 60 * faltan  # «n# explicación breve» por cada retroalimentación que falta
