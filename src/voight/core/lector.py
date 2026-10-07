"""Lector único de bancos GIFT y Moodle XML como unidades procesables.

Cada archivo se lee como una secuencia de segmentos: las preguntas que se pueden
procesar son `Unidad` (con la pregunta en el modelo unificado, su clasificación, el
texto original y lo necesario para volver a escribirla) y el resto queda tal cual
(categorías, comentarios sueltos, preguntas sin equivalente en GIFT). Lo usan `ai`,
`dedup`, `verify`, `classify` y las interfaces de terminal.
"""
from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from voight.core.codigo import transformar_codigo, usa_convencion
from voight.core.converter import question_to_gift
from voight.core.formatter import _bloques_gift
from voight.core.gift_model import Question
from voight.core.moodle_xml import _pregunta as _pregunta_xml
from voight.core.parser import GiftParser

TIPOS_PROCESABLES = ("MC", "Short", "TF", "Matching", "Numerical", "Essay", "Description")


def split_gift_questions(content: str) -> List[str]:
    """Divide GIFT en preguntas como el parser (el código con líneas en blanco queda junto)."""
    return [p.strip() for p in _bloques_gift(content) if p.strip()]


def _forma(q: Question) -> tuple:
    """Cantidad de opciones y de correctas: lo que `improve` no debería cambiar."""
    return (len(q.choices) + len(q.match_pairs), sum(1 for c in q.choices if c.is_correct))



# ---------------------------------------------------------------------------
# Unidades: una pregunta a procesar y lo necesario para escribirla de vuelta
# ---------------------------------------------------------------------------

@dataclass
class Unidad:
    archivo: Path
    formato: str               # 'gift' o 'xml'
    texto: str                 # GIFT compacto que recibe el modelo
    tipo: str                  # tipo del modelo unificado
    pregunta: Question         # modelo unificado del original
    original: str = ""         # texto original (para medir el ahorro)
    prefijo: List[str] = field(default_factory=list)  # comentarios GIFT
    elemento: Optional[ET.Element] = None             # <question> original (XML)
    fullwidth: bool = True     # el código original usaba símbolos fullwidth
    marcas: bool = False       # el código original usaba marcas · / ↵
    forma: tuple = ()          # ver _forma
    parcial: str = ""          # "feedback" | "distractores": sólo se agrega eso al original
    procesado: List[Question] = field(default_factory=list)
    procesado_gift: List[str] = field(default_factory=list)

    @property
    def nodo(self) -> ET.Element:
        """El <question> original de una unidad XML."""
        if self.elemento is None:
            raise ValueError(f"{self.archivo}: la unidad no viene de un Moodle XML")
        return self.elemento


@dataclass
class Archivo:
    ruta: Path
    formato: str
    segmentos: list            # GIFT: str (texto que no se procesa) o Unidad
    raiz: Optional[ET.Element] = None  # XML


def _compactar(texto: str, contexto: str) -> str:
    """Código en ASCII sin marcas ni escapes de GIFT: la forma más corta y natural.

    Primero se protege en su contexto (así se interpretan los escapes de GIFT) y
    después se restaura sin escapar.
    """
    texto, _ = transformar_codigo(texto, contexto=contexto, fullwidth=True, espacios=False, saltos=False)
    texto, _ = transformar_codigo(texto, contexto="xml", fullwidth=False)
    return texto


def _agregar_metadatos(q: Question, comentario: str) -> None:
    """La clasificación del comentario que precede a la pregunta (y de sus tags) en `metadata`."""
    from voight.core.metadatos import leer_clasificacion

    datos = leer_clasificacion(comentario, getattr(q, "tags", None) or [])
    if datos:
        q.metadata = {**(q.metadata or {}), **datos}


def _leer_gift(ruta: Path) -> Archivo:
    segmentos: list = []
    for bloque in split_gift_questions(ruta.read_text(encoding="utf-8")):
        lineas = bloque.splitlines()
        prefijo = []
        while lineas and (lineas[0].strip().startswith("//") or lineas[0].strip().startswith("$CATEGORY")):
            prefijo.append(lineas.pop(0))
        cuerpo = "\n".join(lineas).strip()
        preguntas = [q for q in GiftParser()._manual_parse(cuerpo) if q.type != "Category"] if cuerpo else []
        if len(preguntas) != 1 or preguntas[0].type not in TIPOS_PROCESABLES:
            segmentos.append(bloque)
            continue
        _, marcas = usa_convencion(cuerpo, "gift")
        _agregar_metadatos(preguntas[0], " ".join(prefijo))
        segmentos.append(Unidad(
            archivo=ruta, formato="gift", texto=_compactar(cuerpo, "gift"), tipo=preguntas[0].type,
            original=bloque, prefijo=prefijo, fullwidth=True, marcas=marcas, forma=_forma(preguntas[0]),
            pregunta=preguntas[0],
        ))
    return Archivo(ruta, "gift", segmentos)


def _compactar_pregunta(q: Question) -> Question:
    q = copy.deepcopy(q)
    textos = [q.stem, q.global_feedback, q.true_feedback, q.false_feedback]
    textos += [c.text for c in q.choices] + [c.feedback for c in q.choices]
    textos += [p.subquestion for p in q.match_pairs]
    for ft in textos:
        if ft is not None and ft.text:
            ft.text = _compactar(ft.text, "xml")
    for p in q.match_pairs:
        p.subanswer = _compactar(p.subanswer or "", "xml")
    return q


def _leer_xml(ruta: Path) -> Archivo:
    contenido = ruta.read_text(encoding="utf-8")
    # Con los comentarios: se conservan al escribir (p. ej. `<!-- question: 1854266 -->`).
    raiz = ET.fromstring(contenido, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
    segmentos: list = []
    for elemento in list(raiz):
        if elemento.tag != "question":
            segmentos.append(elemento)
            continue
        q = _pregunta_xml(elemento)
        if q.type not in TIPOS_PROCESABLES:
            segmentos.append(elemento)
            continue
        anterior = segmentos[-1] if segmentos and getattr(segmentos[-1], "tag", None) is ET.Comment else None
        _agregar_metadatos(q, anterior.text or "" if anterior is not None else "")
        crudo = ET.tostring(elemento, encoding="unicode")
        fullwidth, marcas = usa_convencion("\n".join(t.text or "" for t in elemento.iter("text")), "xml")
        segmentos.append(Unidad(
            archivo=ruta, formato="xml", texto=question_to_gift(_compactar_pregunta(q), escapar_codigo=False), tipo=q.type,
            original=crudo, elemento=elemento, fullwidth=fullwidth, marcas=marcas, forma=_forma(q),
            pregunta=q,
        ))
    return Archivo(ruta, "xml", segmentos, raiz=raiz)


def leer_archivos(rutas: List[Path]) -> List[Archivo]:
    archivos = []
    for ruta in rutas:
        try:
            archivos.append(_leer_xml(ruta) if ruta.suffix.lower() == ".xml" else _leer_gift(ruta))
        except Exception as e:  # noqa: BLE001 - se informa y se sigue con el resto
            print(f"❌ Error leyendo {ruta}: {e}")
    return archivos


def unidades_de(archivos: List[Archivo]) -> List[Unidad]:
    return [s for a in archivos for s in a.segmentos if isinstance(s, Unidad)]
