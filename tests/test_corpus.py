"""Invariantes sobre el corpus sintético (siempre) y sobre bancos reales (opcional).

Para los bancos reales, sin copiarlos al repositorio (sólo se leen):

    QUESTIONS_BANCOS=/ruta/banco1:/ruta/banco2 uv run pytest tests/test_corpus.py
"""

import os
from pathlib import Path

import pytest

import invariantes as inv

CORPUS = Path(__file__).parent / "data" / "corpus"
BANCOS = [Path(b) for b in os.environ.get("QUESTIONS_BANCOS", "").split(os.pathsep) if b.strip()]


def _sin_problemas(problemas):
    assert not problemas, f"{len(problemas)} problemas:\n" + "\n".join(problemas[:20])


# --- corpus sintético ----------------------------------------------------------

def test_corpus_formato():
    _sin_problemas(inv.formato_conserva_las_preguntas([CORPUS]))


def test_corpus_conversion():
    _sin_problemas(inv.conversion_conserva_las_preguntas([CORPUS]))


def test_corpus_unificar_y_exportar(tmp_path):
    _sin_problemas(inv.unificar_y_exportar_conserva_las_preguntas(CORPUS, tmp_path))


def test_corpus_salud():
    _sin_problemas(inv.salud_coincide_con_sus_elementos([CORPUS]))


def test_el_corpus_ejercita_lo_que_dice():
    """Si el corpus deja de tener sus casos difíciles, los invariantes no prueban nada."""
    from voight.core.hallazgos import archivos_de, hallazgos
    from voight.core.moodle_health import auditar_archivos

    resultado = auditar_archivos(inv.archivos([CORPUS]))
    claves = {h["clave"] for h in hallazgos(resultado)}
    assert "codigo_gift_sin_proteger" in claves  # constructor.gift: código Java crudo
    assert {p.name for p in archivos_de(resultado, "codigo_gift_sin_proteger")} == {"constructor.gift"}
    preguntas = auditar_archivos(inv.archivos([CORPUS]), con_preguntas=True)["_preguntas"]
    tipos = {q["type"] for q in preguntas}
    assert {"MC", "TF", "Matching", "Numerical", "Short", "Description"} <= tipos
    titulos = {q.get("title") for q in preguntas}
    # La pregunta después de una sin cerrar se lee igual.
    assert "Pregunta sana después de la rota" in titulos
    assert any(q.get("metadata", {}).get("bloom") for q in preguntas)  # clasificación en GIFT y XML
    texto = (CORPUS / "punteros" / "aritmetica.gift").read_text(encoding="utf-8")
    assert "↵" in texto and "····" in texto and "＝" in texto  # código protegido con marcas


# --- bancos reales (opcional) --------------------------------------------------

reales = pytest.mark.skipif(not BANCOS, reason="QUESTIONS_BANCOS no está definido (bancos reales, opcional)")


@reales
@pytest.mark.parametrize("banco", BANCOS, ids=str)
def test_banco_real_formato(banco):
    _sin_problemas(inv.formato_conserva_las_preguntas([banco]))


@reales
@pytest.mark.parametrize("banco", BANCOS, ids=str)
def test_banco_real_conversion(banco):
    _sin_problemas(inv.conversion_conserva_las_preguntas([banco]))


@reales
@pytest.mark.parametrize("banco", BANCOS, ids=str)
def test_banco_real_unificar_y_exportar(banco, tmp_path):
    _sin_problemas(inv.unificar_y_exportar_conserva_las_preguntas(banco, tmp_path))


@reales
@pytest.mark.parametrize("banco", BANCOS, ids=str)
def test_banco_real_salud(banco):
    _sin_problemas(inv.salud_coincide_con_sus_elementos([banco]))
