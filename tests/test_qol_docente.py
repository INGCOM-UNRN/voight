"""Utilidades docentes expuestas en CLI, con bancos mixtos y sin modificar las fuentes."""

import json
import random

import pytest
from click.testing import CliRunner

from voight.cli import cli
from voight.core.accessibility import validar_accesibilidad_imagenes
from voight.core.lectura import leer_preguntas
from voight.core.simulator import simular_examen_aleatorio

runner = CliRunner()


@pytest.fixture
def banco(tmp_path):
    root = tmp_path / "banco"
    root.mkdir()
    for n in range(5):
        (root / f"{n}.gift").write_text(
            f"$CATEGORY: Tema\n::P{n}:: Número {n} {{=Bien ~Mal}}\n", encoding="utf-8"
        )
    (root / "extra.xml").write_text(
        """<quiz><question type="truefalse"><name><text>Desde XML</text></name>
      <questiontext><text>Un booleano</text></questiontext>
      <answer fraction="100"><text>false</text></answer><answer fraction="0"><text>true</text></answer></question></quiz>""",
        encoding="utf-8",
    )
    return root


def test_catalog_and_overlapping_inputs(banco, tmp_path):
    original = {p: p.read_bytes() for p in banco.iterdir()}
    report = runner.invoke(
        cli, ["catalogo", str(banco), str(banco / "0.gift"), "--json"]
    )
    assert report.exit_code == 0, report.output
    data = json.loads(report.stdout)
    assert data["cantidad"] == 6 and data["comando"] == "catalogo"
    assert data["schema_version"] == "1.0.0"
    md = tmp_path / "catalogo.md"
    report = runner.invoke(cli, ["catalogo", str(banco), "-o", str(md)])
    assert report.exit_code == 0
    text = md.read_text(encoding="utf-8")
    assert "Desde XML" in text and "**Categoría:** Tema" in text and "[✓] Falso" in text
    assert "**Origen:**" in text
    assert all(p.read_bytes() == data for p, data in original.items())


def test_seeded_sample_and_no_source_overwrite(banco):
    args = ["muestra", str(banco), "-n", "3", "--semilla", "123", "--json"]
    first, second = runner.invoke(cli, args), runner.invoke(cli, args)
    assert first.exit_code == second.exit_code == 0, first.output
    assert first.stdout == second.stdout
    data = json.loads(first.stdout)
    assert data["cantidad"] == 3 and data["semilla"] == 123 and data["disponibles"] == 6
    assert len({q["archivo"] for q in data["preguntas"]}) == 3
    target = banco / "0.gift"
    original = target.read_bytes()
    report = runner.invoke(cli, ["muestra", str(banco), "-n", "1", "-o", str(target)])
    assert report.exit_code == 1 and target.read_bytes() == original
    report = runner.invoke(cli, ["catalogo", str(banco), "-o", str(target)])
    assert report.exit_code == 1 and target.read_bytes() == original


def test_sample_exact_count_and_rng_isolation(banco):
    report = runner.invoke(cli, ["muestra", str(banco), "-n", "7"])
    assert report.exit_code == 1 and "banco tiene 6" in report.output
    questions = leer_preguntas([banco])
    before = random.getstate()
    selected = simular_examen_aleatorio(questions, 6, 123)
    assert random.getstate() == before and len(selected) == 6
    assert selected == simular_examen_aleatorio(questions, 6, 123)
    with pytest.raises(ValueError):
        simular_examen_aleatorio(questions, 0)


def test_accessibility_enunciado_options_feedback(tmp_path):
    bank = tmp_path / "imagenes.xml"
    bank.write_text(
        """<quiz><question type="multichoice"><name><text>Imágenes</text></name>
      <questiontext format="html"><text><![CDATA[<img src="a" ALT = "Diagrama de pila">]]></text></questiontext>
      <generalfeedback format="html"><text><![CDATA[<img src="b">]]></text></generalfeedback>
      <answer fraction="100"><text><![CDATA[<img src="c" alt="">]]></text></answer>
      <answer fraction="0"><text>Otra</text><feedback><text><![CDATA[<img src="d" alt=Correcto>]]></text></feedback></answer>
      </question></quiz>""",
        encoding="utf-8",
    )
    original = bank.read_bytes()
    report = runner.invoke(cli, ["health", "accesibilidad", str(bank), "--json"])
    assert report.exit_code == 1, report.output
    data = json.loads(report.stdout)
    assert data["total_imagenes"] == 4 and data["imagenes_sin_alt"] == 2
    assert {r["campo"] for r in data["hallazgos"]} == {
        "globalFeedback",
        "choices.0.text",
    }
    assert bank.read_bytes() == original


def test_html_markdown_alt_and_code():
    text = '<img src="a" ALT = "a > b"><img src="b" alt=Diagrama>'
    assert validar_accesibilidad_imagenes(text)["accesible"]
    md = '![Diagrama](a.png) ![](b.png)\n```c\nchar *s = "<img src=x>";\n```\n`<img src=y>`'
    report = validar_accesibilidad_imagenes(md, "markdown")
    assert report["total_imagenes"] == 2 and report["imagenes_sin_alt"] == 1
    assert validar_accesibilidad_imagenes("![Diagrama][ref]", "markdown")["accesible"]


def test_bad_input_is_not_silently_ignored(banco):
    (banco / "rota.xml").write_text("<quiz>", encoding="utf-8")
    for command in (["catalogo"], ["muestra"], ["health", "accesibilidad"]):
        report = runner.invoke(cli, [*command, str(banco)])
        assert report.exit_code == 1 and "rota.xml" in report.output
