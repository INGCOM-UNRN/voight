"""Invariantes que debe cumplir cualquier banco: los usan el corpus sintético y, con
QUESTIONS_BANCOS, los bancos reales (que sólo se leen). Cada función devuelve la lista
de problemas encontrados (vacía si se cumple)."""

from __future__ import annotations

import contextlib
import io
from collections import Counter
from pathlib import Path
from typing import List

from voight.core.banco import expandir_rutas, formato_de
from voight.core.converter import gift_to_xml, xml_to_gift
from voight.core.formatter import format_content
from voight.core.moodle_xml import parse_xml
from voight.core.parser import parse_gift


# Tipos que existen en GIFT y en Moodle XML (cloze y los de plugins sólo en XML).
REPRESENTABLES = {"MC", "TF", "Short", "Matching", "Numerical", "Essay", "Description"}


def _parsear(texto: str, formato: str) -> list:
    resultado = parse_xml(texto) if formato == "xml" else parse_gift(texto)
    return resultado.get("questions", []) if resultado.get("success") else []


def _texto(t: str) -> str:
    """Texto comparable entre formatos: en GIFT una línea en blanco del código se escribe ↵
    (si no, cortaría la pregunta), una que empieza con // se escribe ／／ (si no, sería un
    comentario) y -> se escribe -＞ (si no, sería un emparejamiento), así que esas marcas y
    los espacios finales no cuentan."""
    t = (t or "").replace("↵", "").replace("／／", "//").replace("-＞", "->")
    return "\n".join(linea.rstrip() for linea in t.split("\n")).strip()


def _esencia(q: dict, titulo: bool = True) -> tuple:
    """Lo que no puede cambiar al convertir o formatear: tipo, título, enunciado y opciones."""
    # Una opción en blanco (p. ej. un espacio que representa «el carácter espacio») no
    # existe en GIFT: no cuenta.
    opciones = tuple((_texto(c.get("text", {}).get("text", "")), bool(c.get("is_correct")))
                     for c in q.get("choices", []) if _texto(c.get("text", {}).get("text", "")))
    return (q.get("type"), (q.get("title") or "").strip() if titulo else "",
            _texto((q.get("stem") or {}).get("text", "")), opciones)


def archivos(rutas) -> List[Path]:
    return expandir_rutas([Path(r) for r in rutas], True)


def formato_conserva_las_preguntas(rutas) -> List[str]:
    """format no cambia lo que el parser lee y aplicarlo dos veces no cambia nada."""
    problemas = []
    for ruta in archivos(rutas):
        formato = formato_de(ruta) or "gift"
        try:
            texto = ruta.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        formateado = format_content(texto, formato)
        if _parsear(formateado, formato) != _parsear(texto, formato):
            problemas.append(f"{ruta}: format cambia las preguntas")
        elif format_content(formateado, formato) != formateado:
            problemas.append(f"{ruta}: format no es idempotente")
    return problemas


def conversion_conserva_las_preguntas(rutas) -> List[str]:
    """GIFT → XML y XML → GIFT no parten ni pierden preguntas, y las que tienen equivalente
    en el otro formato conservan tipo, título, enunciado y opciones (un cloze pasa a GIFT
    como texto)."""
    problemas = []
    for ruta in archivos(rutas):
        formato = formato_de(ruta) or "gift"
        try:
            texto = ruta.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        originales = [q for q in _parsear(texto, formato) if q["type"] != "Category"]
        if formato == "xml":
            convertidas = _parsear(xml_to_gift(texto), "gift")
        else:
            convertidas = _parsear(gift_to_xml(texto), "xml")
        convertidas = [q for q in convertidas if q["type"] != "Category"]
        sentido = "XML → GIFT" if formato == "xml" else "GIFT → XML"
        if len(convertidas) != len(originales):
            problemas.append(f"{ruta}: la conversión {sentido} da {len(convertidas)} preguntas en lugar de {len(originales)}")
            continue
        # Moodle XML exige un nombre: una pregunta GIFT sin título se llama "Pregunta" al convertirla.
        sin_titulo = any(not (q.get("title") or "").strip() for q in originales)
        esencia = (lambda q, sin_titulo=sin_titulo: _esencia(q, titulo=not sin_titulo))
        representables = [q for q in originales if q["type"] in REPRESENTABLES]
        if Counter(map(esencia, representables)) - Counter(map(esencia, convertidas)):
            problemas.append(f"{ruta}: la conversión {sentido} cambia preguntas")
    return problemas


def unificar_y_exportar_conserva_las_preguntas(raiz: Path, tmp: Path) -> List[str]:
    """unify de un árbol GIFT y tree export del resultado no pierden ni parten preguntas."""
    from voight.core.tree import gift_export
    from voight.core.unifier import unificar

    gifts = [r for r in archivos([raiz]) if formato_de(r) == "gift"]
    if not gifts:
        return []

    def preguntas(rutas):
        return Counter(_esencia(q) for r in rutas for q in _parsear(r.read_text(encoding="utf-8"), "gift")
                       if q["type"] != "Category")

    with contextlib.redirect_stdout(io.StringIO()):
        unificar([raiz], tmp / "todo.gift", formato="gift", recursivo=True)
        gift_export(tmp / "todo.gift", tmp / "arbol")
    originales, unificado = preguntas(gifts), preguntas([tmp / "todo.gift"])
    exportado = preguntas(sorted((tmp / "arbol").rglob("*.gift")))
    problemas = []
    if sum(unificado.values()) != sum(originales.values()):
        problemas.append(f"unify: {sum(originales.values())} preguntas en el árbol, {sum(unificado.values())} unificadas")
    if exportado != unificado:
        perdidas, sobrantes = unificado - exportado, exportado - unificado
        problemas.append(f"tree export: {sum(perdidas.values())} preguntas cambian o faltan, {sum(sobrantes.values())} sobran")
    return problemas


def salud_coincide_con_sus_elementos(rutas) -> List[str]:
    """Cada hallazgo del resumen de health tiene tantos elementos navegables como dice."""
    from voight.core.hallazgos import elementos, hallazgos
    from voight.core.moodle_health import auditar_archivos

    resultado = auditar_archivos(archivos(rutas))
    return [f"health: {h['clave']} dice {h['cantidad']} y tiene {len(elementos(resultado, h['clave']))} elementos"
            for h in hallazgos(resultado) if len(elementos(resultado, h["clave"])) != h["cantidad"]]
