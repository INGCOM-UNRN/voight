"""Regresiones de la deuda listada en el documento de mejoras (parser, conversor, contrato)."""

from voight.core.parser import parse_gift


def test_emparejamiento_con_guiones_mayor_y_escapes():
    q = parse_gift("::M:: Uní {=1-1 -> 0 =a\\=b -> c\\~d =x > y -> z ####gen}")["questions"][0]
    assert [(p["subquestion"]["text"], p["subanswer"]) for p in q["matchPairs"]] == [
        ("1-1", "0"), ("a=b", "c~d"), ("x > y", "z")]
    assert q["globalFeedback"]["text"] == "gen"


def test_numerica_respeta_escapes_en_el_feedback():
    q = parse_gift("::N:: n {#=3.14:0.01 #pi es \\=3.14 ~%50%3 #casi}")["questions"][0]
    assert [(c["text"]["text"], c["feedback"]["text"], c.get("weight")) for c in q["choices"]] == [
        ("3.14:0.01", "pi es =3.14", None), ("3", "casi", 50.0)]


def test_respuesta_corta_conserva_el_credito_parcial():
    import xml.etree.ElementTree as ET

    from voight.core.converter import gift_to_xml

    xml = gift_to_xml("::C:: Capital de Francia {=París =%50%Paris}")
    fracciones = [a.get("fraction") for a in ET.fromstring(xml).find("question").findall("answer")]
    assert fracciones == ["100", "50"]


def test_gift_a_xml_conserva_lineas_en_blanco_del_codigo_y_es_valido():
    import xml.etree.ElementTree as ET

    from voight.core.converter import gift_to_xml

    # Con la llave abierta, el parser mantiene la línea en blanco dentro de la pregunta.
    xml = gift_to_xml("::C:: Ver\n```c\nint main() {\n    int a = 1 < 2 && 3;\n\n    return a;\n}\n```\n{=x ~y}")
    texto = ET.fromstring(xml).find("question/questiontext/text").text
    assert "int a = 1 < 2 && 3;\n\n    return a;" in texto
    assert "<![CDATA[" in xml


XML_PARRAFOS = """<?xml version="1.0" encoding="UTF-8"?>
<quiz><question type="multichoice">
<name><text>Linkage</text></name>
<questiontext format="markdown"><text><![CDATA[Considere `module.c`:

```c
int a = 1;
  
// comentario
```
#ifdef WINDOWS
// código A
#endif]]></text></questiontext>
<answer fraction="100"><text><![CDATA[`p->x`]]></text></answer>
<answer fraction="0"><text>otra</text></answer>
<idnumber>L-1</idnumber>
<tags><tag><text>enlace</text></tag></tags>
</question></quiz>"""


def test_xml_a_gift_sobre_el_modelo_es_gift_valido_y_sin_perdidas():
    from voight.core.codigo import transformar_codigo
    from voight.core.converter import xml_to_gift
    from voight.core.moodle_xml import parse_xml

    gift = xml_to_gift(XML_PARRAFOS)
    assert gift.startswith("// [id:L-1] [tag:enlace]\n::Linkage::[markdown]")
    pregunta = parse_gift(gift)["questions"][0]
    original = parse_xml(XML_PARRAFOS)["questions"][0]
    assert pregunta["type"] == "MC" and pregunta["id"] == "L-1" and pregunta["tags"] == ["enlace"]

    def normal(t):
        t = transformar_codigo(t, fullwidth=False)[0]
        return "\n".join(linea.rstrip() for linea in t.split("\n"))

    # Párrafos (\n), líneas de sólo espacios en el código (↵), // y -> (protegidos).
    assert normal(pregunta["stem"]["text"]) == normal(original["stem"]["text"]).replace("// código A", "／／ código A")
    assert normal(pregunta["choices"][0]["text"]["text"]) == "`p->x`"


def test_xml_a_gift_conserva_el_html_con_su_prefijo():
    from voight.core.converter import xml_to_gift

    xml = ('<quiz><question type="truefalse"><name><text>VF</text></name><questiontext format="html">'
           '<text><![CDATA[<p>¿<b>Cierto</b>?</p>]]></text></questiontext>'
           '<answer fraction="100"><text>true</text></answer><answer fraction="0"><text>false</text></answer>'
           '</question></quiz>')
    assert xml_to_gift(xml) == "::VF::[html]<p>¿<b>Cierto</b>?</p>\n{T}\n"


def test_verdadero_falso_en_el_orden_de_moodle():
    """{T#mal#bien}: la primera retro es para quien responde mal (Moodle, qformat_gift)."""
    import xml.etree.ElementTree as ET

    from voight.core.converter import gift_to_xml, xml_to_gift

    v = parse_gift("::V:: ¿Sí? {T#Repasá#Bien ####general}")["questions"][0]
    assert v["trueFeedback"]["text"] == "Bien" and v["falseFeedback"]["text"] == "Repasá"
    assert v["globalFeedback"]["text"] == "general"
    f = parse_gift("::F:: ¿No? {F#Repasá#Bien}")["questions"][0]
    assert f["trueFeedback"]["text"] == "Repasá" and f["falseFeedback"]["text"] == "Bien"
    solo_bien = parse_gift("::S:: ¿Sí? {T##Bien}")["questions"][0]
    assert solo_bien["trueFeedback"]["text"] == "Bien" and "falseFeedback" not in solo_bien

    xml = gift_to_xml("::V:: ¿Sí? {T#Repasá#Bien}")
    retro = {a.findtext("text"): a.findtext("feedback/text") for a in ET.fromstring(xml).find("question").findall("answer")}
    assert retro == {"true": "Bien", "false": "Repasá"}
    assert "{T#Repasá#Bien}" in xml_to_gift(xml)
    assert "{T##Bien}" in xml_to_gift(gift_to_xml("::S:: ¿Sí? {T##Bien}"))


def test_validate_y_analyze_salen_con_1_ante_hallazgos(tmp_path):
    from click.testing import CliRunner

    from voight.cli import cli

    runner = CliRunner()
    (tmp_path / "ok.gift").write_text("::A:: ¿2+2? {=4 ~3 ~5}\n", encoding="utf-8")
    assert runner.invoke(cli, ["validate", str(tmp_path / "ok.gift")]).exit_code == 0
    assert runner.invoke(cli, ["analyze", "stats", str(tmp_path)]).exit_code == 0
    assert runner.invoke(cli, ["analyze", "similar", str(tmp_path)]).exit_code == 0

    (tmp_path / "mal.gift").write_text("::B:: ¿2+2? {~4 ~3}\n", encoding="utf-8")  # sin correcta
    (tmp_path / "roto.xml").write_text("<quiz><question>", encoding="utf-8")
    assert runner.invoke(cli, ["validate", str(tmp_path)]).exit_code == 1
    assert runner.invoke(cli, ["analyze", "stats", str(tmp_path), "--json"]).exit_code == 1
    (tmp_path / "copia.gift").write_text("::A:: ¿2+2? {=4 ~3 ~5}\n", encoding="utf-8")
    assert runner.invoke(cli, ["analyze", "similar", str(tmp_path), "--json"]).exit_code == 1


def test_split_gift_conserva_la_categoria_en_cada_archivo(tmp_path):
    from voight.core.splitter import split_file

    banco = tmp_path / "banco.gift"
    banco.write_text("$CATEGORY: $course$/C/Punteros\n\n// [tag:p]\n::Uno:: ¿1? {T}\n\n::Dos:: ¿2? {F}\n\n"
                     "$CATEGORY: $course$/C/Arreglos\n\n::Tres:: ¿3? {T}\n", encoding="utf-8")
    assert split_file(banco) == 3
    assert (tmp_path / "uno.gift").read_text(encoding="utf-8") == "$CATEGORY: $course$/C/Punteros\n\n// [tag:p]\n::Uno:: ¿1? {T}\n"
    assert (tmp_path / "dos.gift").read_text(encoding="utf-8").startswith("$CATEGORY: $course$/C/Punteros\n\n::Dos::")
    assert (tmp_path / "tres.gift").read_text(encoding="utf-8").startswith("$CATEGORY: $course$/C/Arreglos\n\n::Tres::")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["banco.gift", "dos.gift", "tres.gift", "uno.gift"]


def test_html_a_markdown_cambia_solo_los_campos_convertidos():
    import xml.etree.ElementTree as ET

    from voight.core.converter import html_a_markdown_xml

    xml = ('<quiz><question type="multichoice"><questiontext format="html"><text>&lt;p&gt;¿Qué hace '
           '&lt;code&gt;x++&lt;/code&gt;?&lt;/p&gt;</text></questiontext>'
           '<generalfeedback format="html"><text>Sin etiquetas</text></generalfeedback>'
           '<answer fraction="100" format="html"><text><![CDATA[<b>Incrementa</b>]]></text></answer>'
           '<answer fraction="0" format="html"><text/></answer></question></quiz>')
    nuevo, cantidad = html_a_markdown_xml(xml)
    q = ET.fromstring(nuevo).find("question")
    assert cantidad == 2
    assert q.find("questiontext").get("format") == "markdown"
    assert q.findtext("questiontext/text") == "¿Qué hace `x++`?"
    assert q.find("generalfeedback").get("format") == "html"
    assert [a.get("format") for a in q.findall("answer")] == ["markdown", "html"]
    assert q.find("answer").findtext("text") == "**Incrementa**"


def test_similitud_detecta_identicas_en_un_conjunto_chico():
    """Con el IDF sin suavizar, dos preguntas idénticas entre tres daban coseno 0."""
    from voight.core.validator import AnalizadorBanco

    analizador = AnalizadorBanco(similarity_threshold=0.9)
    texto = "Punteros qué guarda un puntero en lenguaje C una dirección un entero nada"
    analizador.all_questions = [{"full_text": texto}, {"full_text": texto}, {"full_text": "otra cosa distinta sí"}]
    analizador.find_duplicates()
    assert [(d["index1"], d["index2"]) for d in analizador.duplicates] == [(0, 1)]
    assert analizador.duplicates[0]["similarity"] > 0.99
