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


# ── Diagramas en el backup: XML los lleva como archivos; GIFT avisa que hay que convertirlo ──

def _dibu_falso(tmp_path: Path, monkeypatch) -> None:
    import stat
    import sys

    script = tmp_path / "dibu"
    script.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        "salida = sys.argv[4]\n"
        "os.makedirs(salida)\n"
        "open(os.path.join(salida, 'diagrama_1.svg'), 'w').write("
        "'<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"4\" height=\"4\"/>')\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("VOIGHT_DIBU", str(script))


XML_CON_DIAGRAMA = """<?xml version="1.0" encoding="UTF-8"?>
<quiz>
  <question type="multichoice">
    <name><text>Arreglo</text></name>
    <questiontext format="markdown"><text><![CDATA[¿Cuánto vale `a[1]`?

```dibu
type: array
values: [1, 2]
```
]]></text></questiontext>
    <answer fraction="100" format="html"><text>2</text>
      <feedback format="html"><text><![CDATA[<pre class="estructura">type: array
values: [2]</pre>]]></text></feedback></answer>
    <answer fraction="0" format="html"><text>1</text></answer>
  </question>
</quiz>
"""


def test_backup_incrusta_los_diagramas_de_las_preguntas_xml(tmp_path: Path, monkeypatch):
    _dibu_falso(tmp_path, monkeypatch)
    d = tmp_path / "banco" / "Arreglos"
    d.mkdir(parents=True)
    (d / "q.xml").write_text(XML_CON_DIAGRAMA, encoding="utf-8")

    info = generar_quiz_mbz(rutas=[tmp_path / "banco"], archivo_salida=tmp_path / "quiz.mbz")
    assert info["archivos"] == 2
    assert info["gift_con_diagramas"] == []

    with tarfile.open(tmp_path / "quiz.mbz", "r:gz") as tar:
        archivos = ET.fromstring(tar.extractfile("files.xml").read())
        preguntas = ET.fromstring(tar.extractfile("questions.xml").read())
        entradas = archivos.findall("file")
        assert {e.findtext("filearea") for e in entradas} == {"questiontext", "answerfeedback"}
        for e in entradas:
            assert e.findtext("component") == "question"
            assert e.findtext("contextid") == "40001"
            assert e.findtext("mimetype") == "image/svg+xml"
            sha = e.findtext("contenthash")
            assert tar.extractfile(f"files/{sha[:2]}/{sha}").read().startswith(b"<svg")

    pregunta = preguntas.find(".//question")
    texto = pregunta.findtext("questiontext")
    enunciado = next(e for e in entradas if e.findtext("filearea") == "questiontext")
    assert enunciado.findtext("itemid") == pregunta.get("id")
    assert f"![diagrama](@@PLUGINFILE@@/{enunciado.findtext('filename')})" in texto
    assert "```dibu" not in texto
    assert pregunta.findtext("questiontextformat") == "4"
    retro = next(e for e in entradas if e.findtext("filearea") == "answerfeedback")
    respuesta = next(a for a in pregunta.iter("answer") if a.get("id") == retro.findtext("itemid"))
    assert "@@PLUGINFILE@@/" in respuesta.findtext("feedback")


def test_backup_no_incrustar_deja_el_texto(tmp_path: Path):
    d = tmp_path / "banco" / "Arreglos"
    d.mkdir(parents=True)
    (d / "q.xml").write_text(XML_CON_DIAGRAMA, encoding="utf-8")

    info = generar_quiz_mbz(rutas=[tmp_path / "banco"], archivo_salida=tmp_path / "quiz.mbz", incrustar=False)
    assert info["archivos"] == 0
    with tarfile.open(tmp_path / "quiz.mbz", "r:gz") as tar:
        assert "```dibu" in tar.extractfile("questions.xml").read().decode("utf-8")
        assert ET.fromstring(tar.extractfile("files.xml").read()).find("file") is None


def test_backup_de_gift_con_diagramas_avisa_que_hay_que_pasarlo_a_xml(tmp_path: Path):
    d = tmp_path / "banco" / "Arreglos"
    d.mkdir(parents=True)
    (d / "q.gift").write_text("::Q:: Mirá\n```dibu\ntype: array\nvalues: [1]\n```\n{=Sí ~No}\n", encoding="utf-8")

    salida = tmp_path / "quiz.mbz"
    r = runner.invoke(cli, ["moodle", "backup-quiz", str(tmp_path / "banco"), "-o", str(salida)])
    assert r.exit_code == 0, r.output
    assert "q.gift" in r.output and "convert gift-to-xml" in r.output
    assert "para que el backup contenga los diagramas" in r.output

    info = generar_quiz_mbz(rutas=[tmp_path / "banco"], archivo_salida=salida)
    assert info["archivos"] == 0
    assert info["gift_con_diagramas"] == [str((d / "q.gift").resolve())]
