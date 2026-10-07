"""Tests para el sintetizador de preguntas de C en moodle-toolbox delegando en alucarD."""

import shutil
import pytest
from click.testing import CliRunner

from voight.cli import cli
from voight.core.synth import (
    plantillas_disponibles,
    sintetizar,
    exportar_gift,
    exportar_xml,
)

import importlib.util
if importlib.util.find_spec("generador_examenes") is None:
    pytest.skip("generador_examenes (alucarD) no está disponible en el entorno", allow_module_level=True)

runner = CliRunner()



def test_plantillas_disponibles():
    disponibles = plantillas_disponibles()
    assert "precedencia" in disponibles
    assert "traza-punteros" in disponibles
    assert "recursion" in disponibles
    assert "incrementos" in disponibles


@pytest.mark.skipif(shutil.which("gcc") is None, reason="Requiere gcc en PATH")
def test_sintetizar_y_exportar(tmp_path):
    snippets = sintetizar("precedencia", cantidad=2, semilla=42)
    assert len(snippets) == 2

    gift_out = exportar_gift(snippets)
    assert "::Precedencia de operadores" in gift_out
    assert "{" in gift_out

    xml_out = exportar_xml(snippets)
    assert "<quiz>" in xml_out or "question" in xml_out


def test_cli_synth_listar():
    res = runner.invoke(cli, ["synth", "--listar"])
    assert res.exit_code == 0
    assert "precedencia" in res.output
    assert "traza-punteros" in res.output
