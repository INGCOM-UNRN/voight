from voight.core.naming import slugify, get_question_title, set_question_title

def test_slugify():
    assert slugify("Hola Mundo") == "hola_mundo"
    assert slugify("Pregunta: ¿Qué es?") == "pregunta_que_es"
    assert slugify("Acción y Función") == "accion_y_funcion"

def test_get_set_gift_title(tmp_path):
    f = tmp_path / "test.gift"
    f.write_text("::Old Title::\nQuestion{=A}")
    
    assert get_question_title(f) == "Old Title"
    
    set_question_title(f, "New Title")
    assert get_question_title(f) == "New Title"
    assert "::New Title::" in f.read_text()

def test_get_set_xml_title(tmp_path):
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<quiz>
  <question type="multichoice">
    <name>
      <text>Old XML Title</text>
    </name>
  </question>
</quiz>"""
    f = tmp_path / "test.xml"
    f.write_text(xml_content)
    
    assert get_question_title(f) == "Old XML Title"
    
    set_question_title(f, "New XML Title")
    assert get_question_title(f) == "New XML Title"
    assert "<text>New XML Title</text>" in f.read_text()


def test_formato_por_contenido():
    from voight.core.banco import formato_por_contenido

    assert formato_por_contenido('<?xml version="1.0"?>\n<quiz></quiz>') == "xml"
    assert formato_por_contenido("﻿<!-- generado -->\n<quiz>\n</quiz>") == "xml"
    assert formato_por_contenido('<question type="truefalse"></question>') == "xml"
    assert formato_por_contenido("::T:: ¿Sí? {T}") == "gift"
    assert formato_por_contenido("$CATEGORY: $course$/a\n\n::T:: Descripción") == "gift"
    # HTML al principio de un enunciado GIFT no lo vuelve XML.
    assert formato_por_contenido("<p>¿Qué imprime?</p> {=1 ~2}") == "gift"
    assert formato_por_contenido("hola") is None
    assert formato_por_contenido("") is None


def test_fix_extension(tmp_path):
    from click.testing import CliRunner

    from voight.cli import cli
    from voight.core.converter import gift_to_xml

    runner = CliRunner()
    (tmp_path / "gift_disfrazado.xml").write_text("::A:: ¿x? {T}\n", encoding="utf-8")
    (tmp_path / "xml_disfrazado.gift").write_text(gift_to_xml("::B:: ¿y? {F}\n"), encoding="utf-8")
    (tmp_path / "bien.gift").write_text("::C:: ¿z? {T}\n", encoding="utf-8")
    (tmp_path / "raro.xml").write_text("sin preguntas\n", encoding="utf-8")

    res = runner.invoke(cli, ["fix", "extension", str(tmp_path), "-n"])
    assert res.exit_code == 0 and "[SIMULACIÓN]" in res.output
    assert (tmp_path / "gift_disfrazado.xml").exists()

    res = runner.invoke(cli, ["fix", "extension", str(tmp_path)])
    assert res.exit_code == 0, res.output
    nombres = sorted(p.name for p in tmp_path.iterdir())
    assert nombres == ["bien.gift", "gift_disfrazado.gift", "raro.xml", "xml_disfrazado.xml"]


def test_fix_extension_no_pisa(tmp_path):
    import json

    from click.testing import CliRunner

    from voight.cli import cli

    (tmp_path / "p.xml").write_text("::A:: ¿x? {T}\n", encoding="utf-8")
    (tmp_path / "p.gift").write_text("::B:: ¿y? {F}\n", encoding="utf-8")
    res = CliRunner().invoke(cli, ["fix", "extension", str(tmp_path), "--json"])
    assert res.exit_code == 1
    datos = json.loads(res.output)
    assert datos["renombrados"] == [] and len(datos["conflictos"]) == 1
    assert (tmp_path / "p.gift").read_text(encoding="utf-8") == "::B:: ¿y? {F}\n"
