"""Tests para el verificador de LanguageTool en voight."""

import json
from pathlib import Path
import pytest
from click.testing import CliRunner

# myst-tools llega con el extra `languagetool` (uv sync --extra languagetool).
pytest.importorskip("myst_tools", reason="requiere el extra languagetool (myst-tools)")

from voight.cli import cli  # noqa: E402
from voight.core.languagetool_checker import (
    enmascarar_gift_xml,
    consultar_languagetool,
    analizar_archivo_banco,
    aplicar_autofix_archivo_banco,
)

runner = CliRunner()


def test_enmascarar_gift_xml():
    texto = (
        "::Pregunta 1:: ¿Cuál es la opción corecta? {\n"
        "  =Opción verdadera\n"
        "  ~Opción falsa #Retroalimentación con `int x = 5;`\n"
        "}\n"
        "<p>Texto con HTML y fórmula \\(x^2 + y^2 = z^2\\)</p>"
    )
    enmascarado, _ = enmascarar_gift_xml(texto)
    assert "¿Cuál es la opción corecta?" in enmascarado
    assert "::Pregunta 1::" not in enmascarado
    assert "=Opción verdadera" not in enmascarado
    assert "<p>" not in enmascarado
    assert "x^2 + y^2" not in enmascarado
    assert len(enmascarado) == len(texto)


def test_consultar_languagetool_moodle_premium(monkeypatch):
    captured = []

    class MockResponse:
        status = 200
        def read(self):
            return json.dumps({"matches": []}).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=10.0: (captured.append(req), MockResponse())[1])

    # 1. Local
    consultar_languagetool("Texto de prueba")
    assert len(captured) == 1

    # 2. Premium
    consultar_languagetool("Texto", username="docente@uba.ar", api_key="lt-moodle-key", premium=True)
    assert len(captured) == 2
    assert "api.languagetoolplus.com" in captured[1].full_url
    body = captured[1].data.decode("utf-8")
    assert "username=docente%40uba.ar" in body
    assert "apiKey=lt-moodle-key" in body


def test_analizar_y_autofix_archivo_gift(tmp_path: Path, monkeypatch):
    banco = tmp_path / "preguntas.gift"
    banco.write_text("::P1:: Texto con prueva de pregunta { =Correcta ~Incorrecta }\n", encoding="utf-8")

    sample_response = {
        "matches": [
            {
                "message": "Falta de ortografía",
                "shortMessage": "Error",
                "offset": 17,
                "length": 6,
                "rule": {"id": "MORFOLOGIK_RULE_ES", "category": {"name": "Ortografía"}},
                "context": {"text": "Texto con prueva de pregunta", "offset": 17, "length": 6},
                "replacements": [{"value": "prueba"}],
            }
        ]
    }

    class MockResponse:
        status = 200
        def read(self):
            return json.dumps(sample_response).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=10.0: MockResponse())

    issues = analizar_archivo_banco(banco)
    assert len(issues) >= 1
    assert issues[0].original_word == "prueva"

    cambios = aplicar_autofix_archivo_banco(banco, issues)
    assert cambios >= 1
    assert "prueba" in banco.read_text(encoding="utf-8")


def test_cli_spellcheck_moodle(tmp_path: Path, monkeypatch):
    banco = tmp_path / "test.gift"
    banco.write_text("::P1:: Texto con errror { =A ~B }\n", encoding="utf-8")

    sample_response = {
        "matches": [
            {
                "message": "Error",
                "shortMessage": "Error",
                "offset": 17,
                "length": 6,
                "rule": {"id": "TEST", "category": {"name": "Ortografía"}},
                "context": {"text": "Texto con errror", "offset": 17, "length": 6},
                "replacements": [{"value": "error"}],
            }
        ]
    }

    class MockResponse:
        status = 200
        def read(self):
            return json.dumps(sample_response).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=10.0: MockResponse())

    res = runner.invoke(cli, ["grammar", str(banco)])
    assert res.exit_code == 1
    assert "Observaciones de LanguageTool" in res.output

    # JSON
    res_json = runner.invoke(cli, ["grammar", str(banco), "--json"])
    assert res_json.exit_code == 1
    assert "total_issues" in res_json.output

    # MD
    md_out = tmp_path / "rep.md"
    res_md = runner.invoke(cli, ["grammar", str(banco), "--md", str(md_out)])
    assert res_md.exit_code == 1
    assert md_out.is_file()
