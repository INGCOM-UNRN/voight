"""Lo que alucarD escribe en un GIFT llega al XML y vuelve: `[corte]`, tamaños, categorías y PlantUML."""
import xml.etree.ElementTree as ET

import pytest
from typer.testing import CliRunner

from voight.cli import app
from voight.core.codigo import diagnosticar_codigo
from voight.core.converter import gift_to_xml, xml_to_gift
from voight.core.formatter import _bloques_gift, format_content
from voight.core.formulas import a_preprocesar
from voight.core.moodle_gift import corregir, revisar, sin_cortes
from voight.core.parser import parse_gift
from voight.core.tree import _protect_backslashes_in_code, gift_collect, xml_collect
from voight.core.unifier import unificar

PLANTUML = """::uml::[markdown]Mirá el diagrama
```plantuml
// [centrado] [ancho, 60%]
class Lista {
  +x: int
}

note right
  //itálica//
end note
A -> B : x = 1 #hola \\n fin
```
¿Qué es?
{=a ~b}

::otra::Segunda {T}
"""


def enunciado(gift, indice=0):
    return parse_gift(gift)["questions"][indice]["stem"]["text"]


def test_corte_pasa_a_un_comentario_de_html_y_vuelve():
    gift = "::a::[markdown]Uno\n// [corte]\nDos\n{}\n"
    xml = gift_to_xml(gift)
    assert "<!--corte-->" in xml
    assert "Uno\n// [corte]\nDos\n{}" in xml_to_gift(xml)


def test_corte_antes_de_las_respuestas_o_en_ellas_no_queda():
    assert "corte" not in gift_to_xml("::a::Uno\n// [corte]\n{\n=a\n// [corte]\n~b\n}\n")


def test_corte_en_texto_plano_no_se_veria():
    assert "corte" not in enunciado("::a::[plain]Uno\n// [corte]\nDos\n{}\n")


def test_las_opciones_de_una_tabla_llegan_al_xml_y_vuelven():
    gift = "::a::[markdown]Uno\n```tabla\n// [centrado]\n| a |\n|---|\n```\n{}\n"
    assert "// [centrado]" in gift_to_xml(gift)
    assert "// [centrado]\n| a |" in xml_to_gift(gift_to_xml(gift))


def test_category_de_una_pregunta_vale_solo_para_ella():
    xml = gift_to_xml("$CATEGORY: $course$/top/A\n\n// [category, B/C]\n::u::x {T}\n\n::d::y {T}\n")
    categorias = [q.findtext("category/text") for q in ET.fromstring(xml).findall("question")
                  if q.get("type") == "category"]
    assert categorias == ["$course$/top/A", "$course$/top/B/C", "$course$/top/A"]


def test_el_tamano_de_un_desarrollo_da_sus_renglones():
    assert "<responsefieldlines>20<" in gift_to_xml("// [tag, desarrollo-grande]\n::a::x\n{}\n")
    assert "<responsefieldlines>10<" in gift_to_xml("::a::x\n{}\n")


def test_la_sintaxis_vieja_se_lee_como_alucard():
    (q,) = parse_gift("::a::Texto [tags: uno, dos] [category: X]\n{desarrollo:grande}\n")["questions"]
    assert q["type"] == "Essay" and q["stem"]["text"] == "Texto"
    assert q["tags"] == ["uno", "dos", "desarrollo-grande"]


def test_format_deja_el_ensayo_en_un_renglon():
    assert format_content("::a::x\n{}\n", "gift").endswith("x\n{}\n")


def test_corregir_migra_a_lo_que_acepta_moodle():
    gift = "// [tag:x]\n::a::Hola: mundo [tags: y]\n{desarrollo:grande}\n"
    assert len(revisar(gift)) == 4
    corregido = corregir(gift)
    assert revisar(corregido) == []
    assert "// [tag, x]\n// [tag, y, desarrollo-grande]\n::a::Hola\\: mundo\n{}" in corregido


def test_corregir_no_toca_diagramas_ni_formulas():
    gift = "::a::$x:y$\n```plantuml\nA -> B : hola\n```\n{}\n"
    assert revisar(gift) == [] and corregir(gift) == gift


def test_el_comando_fix_moodle(tmp_path):
    banco = tmp_path / "a.gift"
    banco.write_text("::a::x: y {desarrollo}\n", encoding="utf-8")
    resultado = CliRunner().invoke(app, ["fix", "moodle", str(banco)])
    assert resultado.exit_code == 0
    assert banco.read_text(encoding="utf-8") == "::a::x\\: y {}\n"


def test_plantuml_no_se_toca_al_parsear():
    assert len(parse_gift(PLANTUML)["questions"]) == 2
    texto = enunciado(PLANTUML)
    assert "class Lista {\n  +x: int\n}\n\nnote right\n  //itálica//" in texto
    assert "A -> B : x = 1 #hola \\n fin" in texto
    assert "// [centrado] [ancho, 60%]" in texto


def test_plantuml_vuelve_crudo_del_xml():
    gift = xml_to_gift(gift_to_xml(PLANTUML))
    assert "class Lista {\n  +x: int\n}\n\nnote right\n  //itálica//" in gift
    assert "A -> B : x = 1 #hola \\n fin" in gift


def test_format_y_bloques_respetan_el_renglon_en_blanco_de_plantuml():
    assert len(_bloques_gift(PLANTUML)) == 2
    assert "}\n\nnote right" in format_content(PLANTUML, "gift")


def test_la_auditoria_no_toma_plantuml_ni_tabla_por_codigo():
    assert diagnosticar_codigo(PLANTUML, "gift")["sin_proteger"] == 0
    assert diagnosticar_codigo(PLANTUML, "gift")["comentarios"] == 0


def test_unify_no_cambia_las_barras_de_plantuml():
    assert "\\n fin" in _protect_backslashes_in_code(PLANTUML)


def test_plantuml_cuenta_como_diagrama_a_preprocesar():
    assert a_preprocesar(PLANTUML)["diagramas"] == 1


GIFT_CON_CORTES = "::a::[markdown]Uno\n// [corte]\nDos\n```plantuml\n// [corte]\nA -> B\n```\n{}\n"
XML_CON_CORTES = ('<quiz><question type="essay"><name><text>a</text></name><questiontext format="markdown">'
                  '<text><![CDATA[Uno\n\n<!--corte-->\n\nDos]]></text></questiontext>'
                  '<generalfeedback format="html"><text><![CDATA[<p>x</p><!-- corte --><p>y</p>]]></text></generalfeedback>'
                  '</question></quiz>')


def test_sin_cortes_conserva_los_parrafos():
    assert sin_cortes("Uno\n\n<!--corte-->\n\nDos") == "Uno\n\nDos"
    assert sin_cortes("<p>x</p><!-- CORTE --><p>y</p>") == "<p>x</p><p>y</p>"
    assert sin_cortes("Uno\n// [corte]\nDos\n") == "Uno\nDos\n"


def test_sin_cortes_no_toca_otros_comentarios_ni_plantuml():
    assert sin_cortes("// [tag, a]\n<!--otro-->\n") == "// [tag, a]\n<!--otro-->\n"
    assert "// [corte]\nA -> B" in sin_cortes(GIFT_CON_CORTES)


def test_unify_a_gift_saca_los_cortes_y_no_toca_la_fuente(tmp_path):
    fuente, salida = tmp_path / "a.gift", tmp_path / "out" / "u.gift"
    fuente.write_text("::a::[markdown]Uno\n// [corte]\nDos\n{}\n", encoding="utf-8")
    unificar([fuente], salida, formato="gift")
    assert "corte" not in salida.read_text(encoding="utf-8")
    assert "// [corte]" in fuente.read_text(encoding="utf-8")


@pytest.mark.parametrize("incrustar", [True, False])
def test_unify_a_xml_saca_los_cortes_de_todos_los_campos(tmp_path, incrustar):
    fuente, salida = tmp_path / "a.xml", tmp_path / "out" / "u.xml"
    fuente.write_text(XML_CON_CORTES, encoding="utf-8")
    unificar([fuente], salida, formato="xml", incrustar=incrustar)
    texto = salida.read_text(encoding="utf-8")
    assert "corte" not in texto and "Uno\n\nDos" in texto
    assert "<!--corte-->" in fuente.read_text(encoding="utf-8")


def test_tree_collect_saca_los_cortes(tmp_path):
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "a.gift").write_text("::a::Uno\n// [corte]\nDos\n{}\n", encoding="utf-8")
    (tmp_path / "in" / "a.xml").write_text(XML_CON_CORTES, encoding="utf-8")
    gift_collect(tmp_path / "in", tmp_path / "u.gift")
    xml_collect(tmp_path / "in", tmp_path / "u.xml")
    assert "corte" not in (tmp_path / "u.gift").read_text(encoding="utf-8")
    assert "corte" not in (tmp_path / "u.xml").read_text(encoding="utf-8")


def test_convert_no_fusiona_y_conserva_los_cortes():
    assert "<!--corte-->" in gift_to_xml("::a::Uno\n// [corte]\nDos\n{}\n")


def test_las_marcas_de_numeros_viajan_y_vuelven():
    gift = "::a::[markdown]Uno\n// [numerar]\n```c\nint a;\n```\n// [sin-numerar]\n```c\nint b;\n```\n{}\n"
    xml = gift_to_xml(gift)
    assert "<!--numerar-->" in xml and "<!--sin-numerar-->" in xml
    vuelta = xml_to_gift(xml)
    assert "// [numerar]\n```c" in vuelta and "// [sin-numerar]\n```c" in vuelta


def test_unify_saca_las_marcas_de_numeros():
    assert sin_cortes("Uno\n// [numerar]\n```c\n```\n") == "Uno\n```c\n```\n"
    assert sin_cortes("Uno\n\n<!--sin-numerar-->\n\nDos") == "Uno\n\nDos"

