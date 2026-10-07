"""Regresión de MOODLE-D0601: --json versionado en analyze, health, tree y synth."""

import json
import shutil
import importlib.util

import pytest

from click.testing import CliRunner

from voight.cli import cli

runner = CliRunner()
GIFT = "$CATEGORY: Mate/Algebra\n::P1:: ¿2+2? {=4 ~3 ~5}\n"


def _json(res):
    assert res.exit_code == 0, res.output
    datos = json.loads(res.output)
    assert datos["schema_version"] == "1.0.0"
    assert datos["herramienta"] == "voight"
    return datos


def test_analyze_stats_json(tmp_path):
    (tmp_path / "a.gift").write_text(GIFT, encoding="utf-8")
    datos = _json(runner.invoke(cli, ["health", "stats", str(tmp_path), "--json"]))
    assert datos["comando"] == "analyze stats"
    assert datos["stats"]["totalQuestions"] == 1


def test_analyze_similar_json(tmp_path):
    (tmp_path / "a.gift").write_text(GIFT, encoding="utf-8")
    datos = _json(runner.invoke(cli, ["health", "similar", str(tmp_path), "--json"]))
    assert datos["pares"] == []


def test_health_json(tmp_path):
    f = tmp_path / "a.gift"
    f.write_text(GIFT, encoding="utf-8")
    datos = _json(runner.invoke(cli, ["health", str(f), "--json"]))
    assert datos["formato"] == "gift"
    assert "porcentajes" in datos and "enlaces" in datos


def test_tree_export_y_collect_json(tmp_path):
    f = tmp_path / "cat.gift"
    f.write_text(GIFT, encoding="utf-8")
    out = tmp_path / "arbol"
    datos = _json(runner.invoke(cli, ["tree", "export", str(f), "-o", str(out), "--json"]))
    assert datos["preguntas"] == 1
    salida = tmp_path / "rebuilt.gift"
    datos = _json(runner.invoke(cli, ["tree", "collect", str(out), "-o", str(salida), "--json"]))
    assert datos["comando"] == "tree collect"


def test_synth_listar_json():
    datos = _json(runner.invoke(cli, ["synth", "--listar", "--json"]))
    assert "precedencia" in datos["plantillas"]


@pytest.mark.skipif(
    shutil.which("gcc") is None or importlib.util.find_spec("generador_examenes") is None,
    reason="Requiere gcc y generador_examenes (alucarD)"
)
def test_synth_generar_json(tmp_path):
    salida = tmp_path / "b.gift"
    datos = _json(runner.invoke(cli, ["synth", "precedencia", "-n", "1", "-o", str(salida), "--json"]))
    assert datos["cantidad"] == 1 and salida.exists()

