"""Tests unitarios y de integración para el módulo unifier y comando unify."""

from pathlib import Path
from click.testing import CliRunner

from voight.cli import cli
from voight.core.unifier import unificar

runner = CliRunner()


def test_unificar_gift_desde_arbol(tmp_path: Path):
    arbol = tmp_path / "arbol_gift"
    (arbol / "Tema1" / "Subtema").mkdir(parents=True)
    (arbol / "Tema2").mkdir(parents=True)

    (arbol / "Tema1" / "Subtema" / "q1.gift").write_text("::Q1:: ¿2+2? {=4}\n", encoding="utf-8")
    (arbol / "Tema2" / "q2.gift").write_text("::Q2:: El cielo es azul. {T}\n", encoding="utf-8")

    salida = tmp_path / "resultado.gift"
    total = unificar([arbol], salida)

    assert total == 2
    assert salida.exists()
    texto = salida.read_text(encoding="utf-8")
    assert "$course$/Tema1/Subtema" in texto
    assert "$course$/Tema2" in texto
    assert "::Q1:: ¿2+2? {=4}" in texto
    assert "::Q2:: El cielo es azul. {T}" in texto


def test_unificar_gift_archivos_sueltos(tmp_path: Path):
    f1 = tmp_path / "pregunta1.gift"
    f2 = tmp_path / "pregunta2.gift"
    f1.write_text("::P1:: Opción 1 {=A ~B}\n", encoding="utf-8")
    f2.write_text("::P2:: Opción 2 {=C ~D}\n", encoding="utf-8")

    salida = tmp_path / "unificado.gift"
    total = unificar([f1, f2], salida)

    assert total == 2
    texto = salida.read_text(encoding="utf-8")
    assert "::P1::" in texto
    assert "::P2::" in texto


def test_unificar_xml_desde_arbol(tmp_path: Path):
    arbol = tmp_path / "arbol_xml"
    (arbol / "Unidad1").mkdir(parents=True)
    (arbol / "Unidad2").mkdir(parents=True)

    xml_q1 = """<?xml version="1.0" encoding="UTF-8"?>
<quiz>
  <question type="truefalse">
    <name><text>TF1</text></name>
    <questiontext format="html"><text><![CDATA[Enunciado 1]]></text></questiontext>
  </question>
</quiz>"""

    xml_q2 = """<?xml version="1.0" encoding="UTF-8"?>
<quiz>
  <question type="truefalse">
    <name><text>TF2</text></name>
    <questiontext format="html"><text><![CDATA[Enunciado 2]]></text></questiontext>
  </question>
</quiz>"""

    (arbol / "Unidad1" / "q1.xml").write_text(xml_q1, encoding="utf-8")
    (arbol / "Unidad2" / "q2.xml").write_text(xml_q2, encoding="utf-8")

    salida = tmp_path / "unificado.xml"
    total = unificar([arbol], salida)

    assert total == 2
    texto = salida.read_text(encoding="utf-8")
    assert "$course$/Unidad1" in texto
    assert "$course$/Unidad2" in texto
    assert "TF1" in texto
    assert "TF2" in texto


def test_cli_unify_gift(tmp_path: Path):
    d = tmp_path / "preguntas"
    (d / "CatA").mkdir(parents=True)
    (d / "CatA" / "p1.gift").write_text("::P1:: Texto 1 {=A}\n", encoding="utf-8")
    (d / "CatA" / "p2.gift").write_text("::P2:: Texto 2 {=B}\n", encoding="utf-8")

    salida = tmp_path / "banco.gift"
    result = runner.invoke(cli, ["unify", str(d), "-o", str(salida)])

    assert result.exit_code == 0
    assert "2 preguntas escritas" in result.output
    assert salida.exists()
    assert "::P1::" in salida.read_text(encoding="utf-8")
    assert "::P2::" in salida.read_text(encoding="utf-8")


def test_cli_unify_remove_option(tmp_path: Path):
    d = tmp_path / "preguntas_eliminar"
    d.mkdir()
    p1 = d / "p1.gift"
    p1.write_text("::Q:: Test {=OK}\n", encoding="utf-8")

    salida = tmp_path / "banco_removido.gift"
    result = runner.invoke(cli, ["unify", str(d), "-o", str(salida), "--remove"])

    assert result.exit_code == 0
    assert not p1.exists()
    assert salida.exists()
