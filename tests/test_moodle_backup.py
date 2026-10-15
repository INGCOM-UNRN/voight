"""Tests unitarios y funcionales para la generación de backups MBZ de cuestionarios."""

import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path
from click.testing import CliRunner

from voight.cli import cli
from voight.core.moodle_backup import generar_quiz_mbz, recolectar_banco_unificado

runner = CliRunner()


def test_recolectar_banco_unificado(tmp_path: Path):
    d = tmp_path / "preguntas"
    (d / "TemaA").mkdir(parents=True)
    (d / "TemaB").mkdir(parents=True)

    (d / "TemaA" / "q1.gift").write_text("::Q1:: ¿Pregunta A? {=Si ~No}\n", encoding="utf-8")
    (d / "TemaB" / "q2.gift").write_text("::Q2:: ¿Pregunta B? {=Verdadero ~Falso}\n", encoding="utf-8")

    categorias = recolectar_banco_unificado([d])
    nombres_cat = {c["name"] for c in categorias}

    assert "TemaA" in nombres_cat
    assert "TemaB" in nombres_cat
    total_preguntas = sum(len(c["questions"]) for c in categorias)
    assert total_preguntas == 2


def test_generar_quiz_mbz_estructura(tmp_path: Path):
    d = tmp_path / "banco"
    (d / "Variables").mkdir(parents=True)
    (d / "Variables" / "p1.gift").write_text("::P1:: Texto {=A ~B}\n", encoding="utf-8")
    (d / "Variables" / "p2.gift").write_text("::P2:: Texto 2 {=C ~D}\n", encoding="utf-8")

    salida_mbz = tmp_path / "quiz.mbz"
    info = generar_quiz_mbz(
        rutas=[d],
        archivo_salida=salida_mbz,
        titulo="Examen Parcial",
        preguntas_por_categoria=1,
    )

    assert info["categorias"] == 1
    assert info["preguntas"] == 2
    assert info["slots"] == 1
    assert salida_mbz.exists()

    with tarfile.open(salida_mbz, "r:gz") as tar:
        nombres = tar.getnames()
        nombres_set = set(nombres)
        assert "moodle_backup.xml" in nombres_set
        assert "questions.xml" in nombres_set
        assert "activities/quiz_10001/quiz.xml" in nombres_set
        assert "activities/quiz_10001/module.xml" in nombres_set
        assert "activities/quiz_10001/grades.xml" in nombres_set
        assert "activities/quiz_10001/inforef.xml" in nombres_set

        quiz_xml = tar.extractfile("activities/quiz_10001/quiz.xml").read().decode("utf-8")
        quiz_tree = ET.fromstring(quiz_xml)
        assert quiz_tree.find(".//quiz/name").text == "Examen Parcial"
        slots = quiz_tree.findall(".//question_instance")
        assert len(slots) == 1
        qsr = slots[0].find("question_set_reference")
        assert qsr is not None
        assert "filtercondition" in [c.tag for c in qsr]

        inforef_xml = tar.extractfile("activities/quiz_10001/inforef.xml").read().decode("utf-8")
        inforef_tree = ET.fromstring(inforef_xml)
        gi_ids = [e.text for e in inforef_tree.findall(".//grade_itemref/grade_item/id")]
        assert "1" in gi_ids
        qc_ids = [e.text for e in inforef_tree.findall(".//question_categoryref/question_category/id")]
        assert len(qc_ids) >= 2  # top + categoría de preguntas

        q_xml = tar.extractfile("questions.xml").read().decode("utf-8")
        q_tree = ET.fromstring(q_xml)
        cats = q_tree.findall(".//question_category")
        cat_names = [c.findtext("name") for c in cats]
        assert "Variables" in cat_names


def test_cli_moodle_backup_quiz(tmp_path: Path):
    d = tmp_path / "repo_preguntas"
    (d / "Modulo1").mkdir(parents=True)
    (d / "Modulo1" / "test.gift").write_text("::M1:: Enunciado {=Correcto ~Falso}\n", encoding="utf-8")

    salida_mbz = tmp_path / "respaldo.mbz"
    result = runner.invoke(
        cli,
        [
            "moodle",
            "backup-quiz",
            str(d),
            "-o",
            str(salida_mbz),
            "-t",
            "Quiz Autogenerado",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert salida_mbz.exists()
    assert '"comando": "moodle backup-quiz"' in result.output
    assert '"slots": 1' in result.output
