
from voight.core.converter import gift_to_xml, xml_to_gift
from voight.core.parser import GiftParser


GIFT_COMPLETO = '''$CATEGORY: $course$/Matematicas/Algebra

::Suma simple:: ¿Cuánto es 2+2? {
=4 # Correcto
~5 # Revisá la suma
}

::Verdadero:: El agua hierve a 100°C. {T#Sí#No}

::Emparejar:: Uní cada operación. {
=1+1 -> 2
=2*2 -> 4
}

::Número:: ¿Raíz de 81? {#9:0.5 ~%50%8.9}

::Desarrollo:: Explique el teorema. {}

::Tema:: Enunciado sin respuesta.
'''


def test_gift_a_xml_genera_estructura_moodle():
    xml = gift_to_xml(GIFT_COMPLETO)
    assert xml.startswith("<?xml")
    for tipo in ("multichoice", "truefalse", "matching", "numerical", "essay", "description"):
        assert f'type="{tipo}"' in xml
    assert "<![CDATA[$course$/Matematicas/Algebra]]>" in xml


def test_xml_a_gift_recupera_todas_las_preguntas():
    xml = gift_to_xml(GIFT_COMPLETO)
    gift = xml_to_gift(xml)
    preguntas = GiftParser()._manual_parse(gift)
    tipos = [q.type for q in preguntas]
    assert tipos.count("MC") == 1
    assert tipos.count("TF") == 1
    assert tipos.count("Matching") == 1
    assert tipos.count("Numerical") == 1
    assert tipos.count("Essay") == 1
    assert tipos.count("Description") == 1


def test_round_trip_estable():
    """XML -> GIFT -> XML produce la misma estructura semántica."""
    xml = gift_to_xml(GIFT_COMPLETO)
    regreso = xml_to_gift(xml)
    xml2 = gift_to_xml(regreso)
    assert _normalizar(xml) == _normalizar(xml2)


def _normalizar(xml: str) -> str:
    import re
    return re.sub(r"\s+", " ", xml)


def test_numerical_conserva_valor_y_tolerancia():
    xml = gift_to_xml("::N:: R {#9:0.5}")
    assert "<text><![CDATA[9]]></text>" in xml
    assert "<tolerance>0.5</tolerance>" in xml


def test_escapes_gift_sobreviven_la_conversion():
    gift = r"::Raros:: ¿Signo de \{llaves\} y ~? {\=correcto ~otra}"
    xml = gift_to_xml(gift)
    gift2 = xml_to_gift(xml)
    pregunta = GiftParser()._manual_parse(gift2)[0]
    textos = [c.text.text for c in pregunta.choices if c.text]
    assert any("correcto" in t for t in textos)


def test_xml_con_categorias_y_preguntas_mixtas(tmp_path):
    xml = '''<?xml version="1.0"?>
<quiz>
  <question type="category"><category><text>$course$/Historia</text></category></question>
  <question type="multichoice">
    <name><text><![CDATA[Capital]]></text></name>
    <questiontext format="html"><text><![CDATA[¿Capital de Francia?]]></text></questiontext>
    <answer fraction="100" format="html"><text><![CDATA[París]]></text></answer>
    <answer fraction="0" format="html"><text><![CDATA[Roma]]></text></answer>
  </question>
</quiz>'''
    gift = xml_to_gift(xml)
    assert "$CATEGORY: $course$/Historia" in gift
    assert "::Capital::" in gift
    assert "=París" in gift
    assert "~Roma" in gift
