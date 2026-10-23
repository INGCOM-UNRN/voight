"""`voight config`: un solo juego de comandos sobre ~/.voight/.env (aislado por el conftest)."""

import os

from click.testing import CliRunner

from voight.cli import cli
from voight.core import config

runner = CliRunner()


def test_set_get_unset_y_show(monkeypatch):
    for c in config.CLAVES.values():
        monkeypatch.delenv(c.variable, raising=False)
    assert runner.invoke(cli, ["config", "set", "anthropic-key", "sk-ant-1234567890"]).exit_code == 0
    assert runner.invoke(cli, ["config", "set", "moodle-url", "https://moodle.ejemplo"]).exit_code == 0
    assert runner.invoke(cli, ["config", "set", "typesafe-key", "ts-abcdefghij"]).exit_code == 0

    res = runner.invoke(cli, ["config", "get", "anthropic-key"])
    assert res.stdout.strip() == "sk-a*********7890"
    assert runner.invoke(cli, ["config", "get", "anthropic-key", "--mostrar"]).stdout.strip() == "sk-ant-1234567890"
    show = runner.invoke(cli, ["config", "show"]).stdout
    assert "https://moodle.ejemplo" in show and "sk-ant-1234567890" not in show

    # unset quita sólo esa clave (antes unset-key borraba todo el archivo).
    assert runner.invoke(cli, ["config", "unset", "anthropic-key"]).exit_code == 0
    guardado = config.archivo_env().read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY" not in guardado and "MOODLE_URL" in guardado and "TYPESAFE_API_KEY" in guardado
    assert runner.invoke(cli, ["config", "get", "anthropic-key"]).exit_code == 1
    assert oct(config.archivo_env().stat().st_mode & 0o777) == "0o600"


def test_el_entorno_gana_y_se_informa(monkeypatch):
    monkeypatch.delenv("MOODLE_TOKEN", raising=False)
    runner.invoke(cli, ["config", "set", "moodle-token", "guardado-123456"])
    monkeypatch.setenv("MOODLE_TOKEN", "del-entorno-123456")
    res = runner.invoke(cli, ["config", "get", "moodle-token", "--mostrar"])
    assert res.stdout.strip() == "del-entorno-123456"
    assert "variable de entorno" in res.stderr


def test_proveedor_y_modelo_guardados_llegan_a_ai(monkeypatch):
    for variable in ("P1_IA_PROVEEDOR", "P1_IA_MODELO", "VOIGHT_PROVEEDOR", "VOIGHT_MODELO", "GEMINI_MODEL"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("P1_IA_CONFIG", os.devnull)
    assert runner.invoke(cli, ["config", "set", "proveedor", "nada"]).exit_code == 1
    assert runner.invoke(cli, ["config", "set", "proveedor", "local"]).exit_code == 0
    assert runner.invoke(cli, ["config", "set", "modelo", "qwen2.5-coder:7b"]).exit_code == 0

    from voight.core.ai import configuracion_ia

    efectiva = configuracion_ia()
    assert (efectiva.proveedor, efectiva.modelo) == ("local", "qwen2.5-coder:7b")
    assert efectiva.origen["proveedor"] == "VOIGHT_PROVEEDOR"
    # Con --proveedor explícito, el modelo guardado (de otro proveedor) no aplica.
    assert configuracion_ia("claude").modelo != "qwen2.5-coder:7b"


def test_moodle_url_guardada_llega_a_moodle_subir(monkeypatch, tmp_path):
    monkeypatch.delenv("MOODLE_URL", raising=False)
    monkeypatch.delenv("MOODLE_TOKEN", raising=False)
    runner.invoke(cli, ["config", "set", "moodle-url", "https://moodle.ejemplo"])
    banco = tmp_path / "a.gift"
    banco.write_text("::P:: ¿2+2? {=4 ~3}\n", encoding="utf-8")
    res = runner.invoke(cli, ["moodle", "subir", str(banco), "--curso", "2", "--dry-run"])
    assert "Missing option '--url'" not in res.output and "--url" not in res.stderr


def test_nombres_anteriores(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    res = runner.invoke(cli, ["config", "set-key", "AIzaEJEMPLO12345"])
    assert res.exit_code == 0 and "ahora es `voight config set gemini-key`" in res.stderr
    runner.invoke(cli, ["config", "set", "moodle-url", "https://moodle.ejemplo"])
    res = runner.invoke(cli, ["config", "unset-key"])
    assert "ahora es `voight config unset gemini-key`" in res.stderr
    guardado = config.archivo_env().read_text(encoding="utf-8")
    assert "GEMINI_API_KEY" not in guardado and "MOODLE_URL" in guardado
    ayuda = runner.invoke(cli, ["config", "--help"], terminal_width=200).output
    for oculto in ("set-key", "show-key", "unset-key", "list-models", "set-provider"):
        assert f"│ {oculto} " not in ayuda
