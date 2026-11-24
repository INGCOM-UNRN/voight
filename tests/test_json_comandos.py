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


def test_split_y_unify_json(tmp_path):
    f = tmp_path / "cat.gift"
    f.write_text(GIFT, encoding="utf-8")
    out = tmp_path / "arbol"
    datos = _json(runner.invoke(cli, ["split", str(f), "-o", str(out), "--json"]))
    assert datos["preguntas"] == 1 and datos["comando"] == "split" and datos["simulacion"] is False
    assert (out / "Mate" / "Algebra").is_dir()
    salida = tmp_path / "rebuilt.gift"
    datos = _json(runner.invoke(cli, ["unify", str(out), "-o", str(salida), "--json"]))
    assert datos["comando"] == "unify" and datos["preguntas"] == 1


def test_split_en_lugar_json_y_dry_run(tmp_path):
    f = tmp_path / "varias.gift"
    f.write_text("::Q1:: ¿2+2? {=4 ~3}\n\n::Q2:: ¿3+3? {=6 ~5}\n", encoding="utf-8")

    res_dry = runner.invoke(cli, ["split", str(f), "--dry-run", "--json"])
    assert res_dry.exit_code == 0, res_dry.output
    assert res_dry.stderr == ""
    datos_dry = json.loads(res_dry.stdout)
    assert datos_dry["schema_version"] == "1.0.0"
    assert datos_dry["herramienta"] == "voight"
    assert datos_dry["comando"] == "split"
    assert datos_dry["archivos"] == 1
    assert datos_dry["preguntas"] == 2
    assert datos_dry["simulacion"] is True
    assert list(tmp_path.glob("*.gift")) == [f]

    res = runner.invoke(cli, ["split", str(f), "--json"])
    assert res.exit_code == 0, res.output
    assert res.stderr == ""
    datos = json.loads(res.stdout)
    assert datos["comando"] == "split"
    assert datos["archivos"] == 1
    assert datos["preguntas"] == 2
    assert datos["simulacion"] is False
    assert (tmp_path / "q1.gift").exists() and (tmp_path / "q2.gift").exists()


def test_split_exportar_dry_run_json_y_normal(tmp_path):
    f = tmp_path / "banco.gift"
    f.write_text(GIFT + "\n::P2:: ¿3+3? {=6 ~5}\n", encoding="utf-8")
    out = tmp_path / "arbol_dry"

    res_dry_json = runner.invoke(cli, ["split", str(f), "-o", str(out), "--dry-run", "--json"])
    assert res_dry_json.exit_code == 0, res_dry_json.output
    assert res_dry_json.stderr == ""
    datos = json.loads(res_dry_json.stdout)
    assert datos["schema_version"] == "1.0.0"
    assert datos["herramienta"] == "voight"
    assert datos["comando"] == "split"
    assert datos["simulacion"] is True
    assert datos["bancos"] == 1
    assert datos["directorio"] == str(out)
    assert not out.exists()

    res_dry_txt = runner.invoke(cli, ["split", str(f), "-o", str(out), "--dry-run"])
    assert res_dry_txt.exit_code == 0, res_dry_txt.output
    assert f"[SIMULACIÓN] 1 bancos se exportarían a {out}" in res_dry_txt.stdout
    assert not out.exists()


def test_split_modo_normal_y_directorio_vacio(tmp_path):
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    res_vacio = runner.invoke(cli, ["split", str(vacio), "--json"])
    assert res_vacio.exit_code == 0, res_vacio.output
    datos_vacio = json.loads(res_vacio.stdout)
    assert datos_vacio["archivos"] == 0 and datos_vacio["preguntas"] == 0 and datos_vacio["simulacion"] is False

    f = tmp_path / "normal.gift"
    f.write_text("::A1:: ¿1+1? {=2 ~3}\n\n::A2:: ¿4+4? {=8 ~7}\n", encoding="utf-8")
    res_dry = runner.invoke(cli, ["split", str(f), "--dry-run"])
    assert res_dry.exit_code == 0, res_dry.output
    assert "[SIMULACIÓN] " in res_dry.stdout
    assert "Resumen: 1 archivos divididos, 2 nuevos archivos creados." in res_dry.stdout

    res_normal = runner.invoke(cli, ["split", str(f)])
    assert res_normal.exit_code == 0, res_normal.output
    assert "✓ " in res_normal.stdout and "dividido en 2 archivos" in res_normal.stdout
    assert "Resumen: 1 archivos divididos, 2 nuevos archivos creados." in res_normal.stdout


def test_tree_export_y_collect_json_nombres_anteriores(tmp_path):
    f = tmp_path / "cat.gift"
    f.write_text(GIFT, encoding="utf-8")
    out = tmp_path / "arbol"
    res = runner.invoke(cli, ["tree", "export", str(f), "-o", str(out), "--json"])
    assert "ahora es `voight split -o DIR`" in res.stderr
    assert json.loads(res.stdout)["preguntas"] == 1
    res = runner.invoke(cli, ["tree", "collect", str(out), "-o", str(tmp_path / "rebuilt.gift"), "--json"])
    assert "ahora es `voight unify`" in res.stderr
    assert json.loads(res.stdout)["comando"] == "tree collect"


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

