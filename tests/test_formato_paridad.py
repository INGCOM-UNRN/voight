"""Formato y comandos de mantenimiento con la misma capacidad en GIFT y Moodle XML."""

import xml.etree.ElementTree as ET

from click.testing import CliRunner

from voight.cli import cli
from voight.core.formatter import format_gift_content, format_xml_content
from voight.core.moodle_xml import parse_xml
from voight.core.parser import parse_gift
from voight.core.splitter import split_file
from voight.core.xml_tools import ensure_cdata_in_text_blocks

runner = CliRunner()

XML = """<?xml version="1.0" encoding="UTF-8"?>
<quiz><!-- question: 1 -->
<question type="multichoice"><name><text>Uno</text></name>
<questiontext format="markdown"><text><![CDATA[```c
#include <stdio.h>
int a = 1 && 2;
```]]></text></questiontext>
<generalfeedback format="markdown"><text/></generalfeedback>
<answer fraction="0"><text>x &lt; y</text></answer>
<answer fraction="50"><text>media</text></answer>
<answer fraction="100"><text>buena</text></answer>
</question>
<question type="truefalse"><name><text>Dos</text></name><questiontext><text>¿Sí?</text></questiontext>
<answer fraction="100"><text>true</text></answer><answer fraction="0"><text>false</text></answer></question>
</quiz>
"""


def test_formato_gift_no_corta_el_codigo_con_lineas_en_blanco():
    gift = "::T::[markdown]Código:\n```c\nint a;\n\nint b;\n```\n{\n=x\n~y\n}\n"
    salida = format_gift_content(gift)
    assert "int a;\n\nint b;" in salida
    assert parse_gift(salida)["questions"] == parse_gift(gift)["questions"]


def test_formato_gift_conserva_el_codigo_de_las_opciones():
    gift = "::T::¿Cuál?\n{\n=`if (x)\n{····y;\n}`\n~otra\n}\n"
    salida = format_gift_content(gift)
    assert "    =`if (x)\n{····y;\n}`\n    ~otra" in salida
    assert format_gift_content(salida) == salida


def test_formato_gift_llaves_en_el_enunciado_y_opciones_en_una_linea():
    gift = "::T::¿Qué hace `if (a) { b; }`? {=nada ~algo}\n"
    salida = format_gift_content(gift)
    assert salida == "::T::\n¿Qué hace `if (a) { b; }`?\n{\n    =nada\n    ~algo\n}\n"
    assert parse_gift(salida)["questions"] == parse_gift(gift)["questions"]


def test_formato_gift_cloze_queda_igual():
    gift = "::C:: El {=uno ~dos} y el {=tres ~cuatro} final"
    assert format_gift_content(gift) == "::C::\nEl {=uno ~dos} y el {=tres ~cuatro} final\n"


def test_correct_first_ordena_por_porcentaje_en_ambos_formatos():
    gift = format_gift_content("::T:: Q {~mala ~%50%media =buena ####fb}", correct_first=True)
    assert gift.splitlines()[3:7] == ["    =buena", "    ~%50%media", "    ~mala", "    ####fb"]
    xml = format_xml_content(XML, correct_first=True)
    respuestas = ET.fromstring(xml).find("question").findall("answer")
    assert [a.get("fraction") for a in respuestas] == ["100", "50", "0"]


def test_correct_first_mueve_la_retroalimentacion_con_su_opcion():
    gift = "::T:: Q {\n~mala\n#por qué no\n=buena\n#por qué sí\n####general\n}"
    salida = format_gift_content(gift, correct_first=True)
    assert "    =buena\n    #por qué sí\n    ~mala\n    #por qué no\n    ####general" in salida
    antes = {c["text"]["text"]: c["feedback"]["text"] for c in parse_gift(gift)["questions"][0]["choices"]}
    despues = {c["text"]["text"]: c["feedback"]["text"] for c in parse_gift(salida)["questions"][0]["choices"]}
    assert antes == despues


def test_formato_xml_cdata_sangria_y_comentarios():
    salida = format_xml_content(XML)
    ET.fromstring(salida)
    assert "<!-- question: 1 -->" in salida
    assert "<text><![CDATA[x < y]]></text>" in salida
    assert "#include <stdio.h>\nint a = 1 && 2;" in salida
    assert "\n  <question type=\"multichoice\">\n    <name>" in salida
    assert "<text></text>" in salida
    assert format_xml_content(salida) == salida
    assert parse_xml(salida)["questions"] == parse_xml(XML)["questions"]


def test_comando_format_procesa_gift_y_xml(tmp_path):
    (tmp_path / "a.gift").write_text("::A::Q {=a ~b}\n", encoding="utf-8")
    (tmp_path / "b.xml").write_text(XML, encoding="utf-8")
    res = runner.invoke(cli, ["fix", "format", str(tmp_path), "--fullwidth"])
    assert res.exit_code == 0, res.output
    assert "2 modificados" in res.output
    xml = (tmp_path / "b.xml").read_text(encoding="utf-8")
    assert "＃include ＜stdio.h＞↵\nint a ＝ 1 ＆＆ 2；↵\n```" in xml
    res = runner.invoke(cli, ["fix", "format", str(tmp_path), "--fullwidth"])
    assert "0 modificados" in res.output
    res = runner.invoke(cli, ["fix", "format", str(tmp_path), "--normal"])
    assert "#include <stdio.h>\nint a = 1 && 2;\n```" in (tmp_path / "b.xml").read_text(encoding="utf-8")


def test_fix_code_indent_y_code_chars_en_xml(tmp_path):
    xml = tmp_path / "c.xml"
    xml.write_text(XML.replace("int a", "    int a"), encoding="utf-8")
    res = runner.invoke(cli, ["fix", "code-indent", str(xml)])
    assert res.exit_code == 0, res.output
    assert "····int a = 1 && 2;" in xml.read_text(encoding="utf-8")
    res = runner.invoke(cli, ["fix", "code-chars", str(xml), "--to-fullwidth", "--sin-marcas"])
    assert res.exit_code == 0, res.output
    assert "····int a ＝ 1 ＆＆ 2；\n```" in xml.read_text(encoding="utf-8")


def test_split_xml_un_archivo_por_pregunta(tmp_path):
    banco = tmp_path / "banco.xml"
    banco.write_text(XML.replace("<quiz>", '<quiz><question type="category"><category><text>$course$/C</text></category></question>'), encoding="utf-8")
    assert split_file(banco) == 2
    uno = (tmp_path / "uno.xml").read_text(encoding="utf-8")
    preguntas = parse_xml(uno)["questions"]
    assert [p["type"] for p in preguntas] == ["Category", "MC"]
    assert "#include <stdio.h>" in uno
    assert (tmp_path / "dos.xml").exists()


def test_tree_export_xml_con_codigo_produce_xml_valido(tmp_path):
    banco = tmp_path / "banco.xml"
    banco.write_text(XML, encoding="utf-8")
    res = runner.invoke(cli, ["tree", "export", str(banco), "-o", str(tmp_path / "arbol")])
    assert res.exit_code == 0, res.output
    for archivo in (tmp_path / "arbol").rglob("*.xml"):
        ET.parse(archivo)
    res = runner.invoke(cli, ["tree", "collect", str(tmp_path / "arbol"), "-o", str(tmp_path / "otra.xml")])
    assert res.exit_code == 0, res.output
    ET.parse(tmp_path / "otra.xml")


def test_ensure_cdata_no_se_come_los_text_vacios():
    xml = "<q><a><text/></a><b><text>x &lt; y</text></b></q>"
    salida, cambios = ensure_cdata_in_text_blocks(xml)
    assert cambios == 1
    assert salida == "<q><a><text/></a><b><text><![CDATA[x &lt; y]]></text></b></q>"


def test_formato_xml_deja_las_guardas_solas_en_su_linea():
    from voight.core.formatter import format_xml_content

    xml = ('<quiz><question type="essay"><questiontext format="markdown"><text><![CDATA['
           'Dado el código ```c int x = 1;\nreturn x;``` y luego texto]]></text></questiontext></question></quiz>')
    salida = format_xml_content(xml)
    assert "Dado el código\n```c\nint x = 1;\nreturn x;\n```\ny luego texto" in salida
    assert format_xml_content(salida) == salida


def test_aislar_guardas_conserva_la_marca_de_lenguaje():
    from voight.core.codigo import aislar_guardas

    # La palabra pegada a la apertura es la marca, aunque no sea un lenguaje conocido de antemano.
    assert aislar_guardas("Ej. ```kotlin val x = 1\n```")[0] == "Ej.\n```kotlin\nval x = 1\n```"
    # Con una cantidad impar de guardas no se sabe cuál abre: el texto queda igual.
    assert aislar_guardas("texto ```c\nint x;") == ("texto ```c\nint x;", 0)
