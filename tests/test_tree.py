
from voight.core import tree


GIFT_BANCO = '''$CATEGORY: $course$/Tema1/Subtema

::Q1:: ¿2+2? {=4}

$CATEGORY: $course$/Tema2

::Q2:: El cielo es azul. {T}
'''


def _limpiar(capsys):
    capsys.readouterr()


def test_gift_export_crea_arbol_por_categorias(tmp_path, capsys):
    banco = tmp_path / "full.gift"
    banco.write_text(GIFT_BANCO, encoding="utf-8")

    cantidad = tree.exportar(banco, tmp_path / "arbol")
    _limpiar(capsys)

    assert cantidad == 2
    assert (tmp_path / "arbol" / "Tema1" / "Subtema" / "q1.gift").exists()
    assert (tmp_path / "arbol" / "Tema2" / "q2.gift").exists()


def test_gift_round_trip_preserva_categorias_y_preguntas(tmp_path, capsys):
    banco = tmp_path / "full.gift"
    banco.write_text(GIFT_BANCO, encoding="utf-8")

    tree.exportar(banco, tmp_path / "arbol")
    tree.recolectar(tmp_path / "arbol", tmp_path / "reconstruido.gift")
    _limpiar(capsys)

    salida = (tmp_path / "reconstruido.gift").read_text(encoding="utf-8")
    assert "$course$/Tema1/Subtema" in salida
    assert "$course$/Tema2" in salida
    for fragmento in ("¿2+2?", "=4", "El cielo es azul.", "T"):
        assert fragmento in salida


def test_gift_export_con_titulos_duplicados_no_sobrescribe(tmp_path, capsys):
    banco = tmp_path / "full.gift"
    banco.write_text("::Igual:: A {T}\n\n::Igual:: B {F}\n", encoding="utf-8")

    cantidad = tree.exportar(banco, tmp_path / "arbol")
    _limpiar(capsys)

    assert cantidad == 2
    nombres = sorted(p.name for p in (tmp_path / "arbol").glob("*.gift"))
    assert nombres == ["igual.gift", "igual_1.gift"]


XML_BANCO = '''<?xml version="1.0" encoding="UTF-8"?>
<quiz>
  <question type="category"><category><text><![CDATA[$course$/Historia]]></text></category></question>
  <question type="truefalse">
    <name><text><![CDATA[TF1]]></text></name>
    <questiontext format="html"><text><![CDATA[El sol es una estrella.]]></text></questiontext>
    <answer fraction="100" format="moodle_auto_format"><text>true</text></answer>
    <answer fraction="0" format="moodle_auto_format"><text>false</text></answer>
  </question>
</quiz>'''


def test_xml_export_collect_round_trip(tmp_path, capsys):
    banco = tmp_path / "full.xml"
    banco.write_text(XML_BANCO, encoding="utf-8")

    cantidad = tree.exportar(banco, tmp_path / "arbol")
    assert cantidad == 1
    assert (tmp_path / "arbol" / "Historia" / "tf1.xml").exists()

    cantidad2 = tree.recolectar(tmp_path / "arbol", tmp_path / "reconstruido.xml")
    _limpiar(capsys)
    assert cantidad2 == 1

    salida = (tmp_path / "reconstruido.xml").read_text(encoding="utf-8")
    assert "$course$/Historia" in salida
    assert "El sol es una estrella." in salida
