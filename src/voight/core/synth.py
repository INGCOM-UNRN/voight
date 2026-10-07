"""Motor de síntesis de preguntas C — Delegado al engine canónico de alucarD."""

from __future__ import annotations

try:
    from generador_examenes.synthesizer.engine import (
        SnippetGenerado,
        compilar_y_ejecutar,
        PLANTILLAS,
        plantillas_disponibles,
        sintetizar,
        exportar_gift,
        exportar_xml as _exportar_xml_base,
    )
except ImportError:  # sin alucarD (generador-examenes): la síntesis no está disponible
    SnippetGenerado = None  # type: ignore
    compilar_y_ejecutar = None  # type: ignore
    PLANTILLAS = {}  # type: ignore
    def plantillas_disponibles() -> dict[str, str]:  # type: ignore
        return {
            "precedencia": "Precedencia de operadores",
            "traza-punteros": "Traza de punteros",
            "recursion": "Recursión",
            "incrementos": "Incrementos",
        }
    def sintetizar(*args, **kwargs):  # type: ignore
        raise RuntimeError(
            "la síntesis de preguntas usa alucarD (generador-examenes), que no está instalado. "
            "Sumalo al entorno de voight: uv tool install --with "
            "\"generador-examenes @ git+https://github.com/INGCOM-UNRN/alucarD\" "
            "\"voight @ git+https://github.com/INGCOM-UNRN/voight\""
        )
    def exportar_gift(*args, **kwargs) -> str:  # type: ignore
        return ""
    def _exportar_xml_base(*args, **kwargs) -> str:  # type: ignore
        return ""


def exportar_xml(snippets: list[SnippetGenerado]) -> str:
    """Serializa los snippets como Moodle XML reutilizando gift_to_xml si está disponible, o el exportador base."""
    try:
        from voight.core.converter import gift_to_xml
        return gift_to_xml(exportar_gift(snippets))
    except Exception:
        return _exportar_xml_base(snippets)


__all__ = [
    "SnippetGenerado",
    "compilar_y_ejecutar",
    "PLANTILLAS",
    "plantillas_disponibles",
    "sintetizar",
    "exportar_gift",
    "exportar_xml",
]
