"""Contrato de línea de comandos (LINEAMIENTOS §3.2, N-ECO-04): el test reutilizable de yutani (N-ECO-14)."""

from __future__ import annotations

from importlib.metadata import version

from typer.testing import CliRunner
from yutani.testing import pruebas_de_contrato

from voight.cli import app

test_ayuda, test_version, test_doctor_json = pruebas_de_contrato(app)


def test_la_version_nombra_la_herramienta():
    assert CliRunner().invoke(app, ["--version"]).output.strip() == f"voight {version('voight')}"


def test_la_ayuda_esta_en_espanol():
    salida = CliRunner().invoke(app, ["--help"], env={"COLUMNS": "150"}).output
    assert "Comandos" in salida and "Muestra esta ayuda y sale." in salida


def test_los_nombres_anteriores_avisan_que_ahora_es_voight(monkeypatch, capsys):
    from voight import cli

    for anterior in ("questions", "moodle-toolbox"):
        monkeypatch.setattr(cli.sys, "argv", [f"/usr/bin/{anterior}"])
        cli._avisar_alias_deprecado()
        assert f"`{anterior}` ahora se llama `voight`" in capsys.readouterr().err
    monkeypatch.setattr(cli.sys, "argv", ["/usr/bin/voight"])
    cli._avisar_alias_deprecado()
    assert capsys.readouterr().err == ""


def test_lee_el_toml_con_el_nombre_anterior(tmp_path):
    from voight.core import configuracion

    (tmp_path / ".git").mkdir()
    (tmp_path / ".questions.toml").write_text("[dedup]\numbral = 0.9\n", encoding="utf-8")
    configuracion._buscar.cache_clear()
    assert configuracion.buscar([tmp_path]) == tmp_path / ".questions.toml"
    (tmp_path / ".voight.toml").write_text("[dedup]\numbral = 0.8\n", encoding="utf-8")
    configuracion._buscar.cache_clear()
    assert configuracion.buscar([tmp_path]) == tmp_path / ".voight.toml"
