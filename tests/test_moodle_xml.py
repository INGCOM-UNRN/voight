"""Moodle XML al modelo unificado y análisis de repositorios mixtos (GIFT + XML)."""

import itertools
import json
import random

from click.testing import CliRunner

from voight.cli import cli
from voight.core.banco import buscar_archivos, parse_archivo
from voight.core.converter import gift_to_xml
from voight.core.moodle_xml import parse_xml
from voight.core.parser import parse_gift
from voight.core.validator import AnalizadorBanco

runner = CliRunner()

XML = """<?xml version="1.0" encoding="UTF-8"?>
<quiz>
  <question type="category"><category><text>$course$/C/Punteros</text></category></question>
  <question type="multichoice">
    <name><text>Opción múltiple</text></name>
    <questiontext format="markdown"><text><![CDATA[¿Cuál?]]></text></questiontext>
    <generalfeedback format="markdown"><text>General</text></generalfeedback>
    <idnumber>P-01</idnumber>
    <answer fraction="100" format="markdown"><text>Sí</text><feedback><text>Bien</text></feedback></answer>
    <answer fraction="50"><text>Más o menos</text><feedback><text/></feedback></answer>
    <answer fraction="0"><text>No</text></answer>
    <tags><tag><text>punteros</text></tag></tags>
  </question>
  <question type="truefalse">
    <name><text>VF</text></name>
    <questiontext format="html"><text>&lt;p&gt;¿Cierto?&lt;/p&gt;</text></questiontext>
    <answer fraction="0"><text>true</text><feedback><text>No</text></feedback></answer>
    <answer fraction="100"><text>false</text><feedback><text>Sí</text></feedback></answer>
  </question>
  <question type="numerical">
    <name><text>Num</text></name>
    <questiontext><text>¿Pi?</text></questiontext>
    <answer fraction="100"><text>3.14</text><tolerance>0.01</tolerance></answer>
  </question>
  <question type="matching">
    <name><text>Emparejar</text></name>
    <questiontext><text>Uní</text></questiontext>
    <subquestion><text>a</text><answer><text>1</text></answer></subquestion>
    <subquestion><text>b</text><answer><text>2</text></answer></subquestion>
  </question>
  <question type="cloze"><name><text>Cloze</text></name><questiontext><text>{1:SA:=x}</text></questiontext></question>
</quiz>
"""


def test_parse_xml_al_modelo_unificado():
    resultado = parse_xml(XML)
    assert resultado["success"] and resultado["questionCount"] == 6
    cat, mc, tf, num, match, cloze = resultado["questions"]
    assert cat == {"type": "Category", "title": "$course$/C/Punteros"}
    assert mc["type"] == "MC" and mc["title"] == "Opción múltiple" and mc["id"] == "P-01"
    assert mc["tags"] == ["punteros"] and mc["globalFeedback"]["text"] == "General"
    assert mc["stem"] == {"format": "markdown", "text": "¿Cuál?"}
    sí, parcial, no = mc["choices"]
    assert sí["is_correct"] and "weight" not in sí and sí["feedback"]["text"] == "Bien"
    assert not parcial["is_correct"] and parcial["weight"] == 50 and "feedback" not in parcial
    assert not no["is_correct"] and "weight" not in no
    assert tf["type"] == "TF" and tf["isTrue"] is False
    assert tf["trueFeedback"]["text"] == "No" and tf["falseFeedback"]["text"] == "Sí"
    assert tf["stem"]["format"] == "html" and tf["stem"]["text"] == "<p>¿Cierto?</p>"
    assert num["choices"][0]["text"]["text"] == "3.14:0.01"
    assert [p["subanswer"] for p in match["matchPairs"]] == ["1", "2"]
    assert cloze["type"] == "Cloze" and cloze["hasEmbeddedAnswers"]


def test_parse_xml_error_con_ubicacion():
    resultado = parse_xml("<quiz><question></quiz>")
    assert not resultado["success"]
    assert resultado["error"]["location"]["line"] == 1


def test_gift_y_su_conversion_a_xml_dan_el_mismo_modelo():
    gift = "::MC:: ¿Cuál? {=Sí #Bien ~%50%Medio ~No #Mal ####General}\n\n::VF:: ¿Cierto? {T}\n"
    desde_gift = parse_gift(gift)["questions"]
    desde_xml = parse_xml(gift_to_xml(gift))["questions"]

    def esencia(p):
        return (
            p["type"], p.get("title"), p["stem"]["text"],
            [(c["is_correct"], c.get("weight"), c["text"]["text"], (c.get("feedback") or {}).get("text"))
             for c in p.get("choices", [])],
            (p.get("globalFeedback") or {}).get("text"), p.get("isTrue"),
        )

    assert [esencia(p) for p in desde_gift] == [esencia(p) for p in desde_xml]


def test_buscar_y_parsear_ambos_formatos(tmp_path):
    (tmp_path / "a.gift").write_text("::A:: ¿Qué? {=a ~b}\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.xml").write_text(XML, encoding="utf-8")
    (tmp_path / ".oculto").mkdir()
    (tmp_path / ".oculto" / "c.xml").write_text(XML, encoding="utf-8")
    archivos = buscar_archivos(tmp_path)
    assert [a.name for a in archivos] == ["a.gift", "b.xml"]
    assert [parse_archivo(a)["formato"] for a in archivos] == ["gift", "xml"]


def test_analizador_cuenta_por_formato_y_detecta_duplicados_entre_formatos(tmp_path):
    gift = "::Punteros:: ¿Qué guarda un puntero en C? {=Una dirección de memoria ~Un valor entero ~Un carácter}\n"
    (tmp_path / "a.gift").write_text(gift, encoding="utf-8")
    (tmp_path / "b.xml").write_text(gift_to_xml(gift), encoding="utf-8")
    analizador = AnalizadorBanco(similarity_threshold=0.85)
    analizador.scan_directory(str(tmp_path))
    assert dict(analizador.stats.by_format) == {"gift": 1, "xml": 1}
    assert analizador.stats.total_questions == 2
    assert len(analizador.duplicates) == 1
    datos = analizador.to_json()
    par = datos["duplicates"][0]
    assert {par["question1"]["format"], par["question2"]["format"]} == {"gift", "xml"}
    assert datos["stats"]["questionsByFormat"] == {"gift": 1, "xml": 1}


def test_filtrado_por_prefijos_igual_a_fuerza_bruta():
    random.seed(7)
    vocab = [f"w{i}" for i in range(40)]
    for umbral in (0.5, 0.7, 0.85, 0.95):
        analizador = AnalizadorBanco(similarity_threshold=umbral)
        textos = []
        for _ in range(12):
            base = random.sample(vocab, random.randint(0, 10))
            textos.append(base)
            textos.append(base[:-1] + [random.choice(vocab)])
        analizador.all_questions = [{"full_text": " ".join(t)} for t in textos]
        analizador.find_duplicates()
        rapido = sorted((d["index1"], d["index2"]) for d in analizador.duplicates)
        bruto = sorted(
            (i, j) for i, j in itertools.combinations(range(len(textos)), 2)
            if analizador._combined_similarity(analizador.all_questions[i], analizador.all_questions[j]) >= umbral
        )
        assert rapido == bruto


def test_validate_y_analyze_con_xml(tmp_path):
    (tmp_path / "b.xml").write_text(XML, encoding="utf-8")
    res = runner.invoke(cli, ["validate", str(tmp_path / "b.xml")])
    assert res.exit_code == 0, res.output
    assert "Archivo válido" in res.output and "Preguntas encontradas: 6" in res.output
    res = runner.invoke(cli, ["validate", str(tmp_path), "--json"])
    assert res.exit_code == 0, res.output
    assert json.loads(res.output)["directories"]["stats"]["byFormat"] == {"xml": 1}
    res = runner.invoke(cli, ["analyze", "stats", str(tmp_path), "--json"])
    datos = json.loads(res.output)
    assert datos["stats"]["byType"]["MC"] == 1 and datos["stats"]["byCategory"] == {"$course$/C/Punteros": 1}


def test_parser_gift_respeta_escapes_en_opciones():
    preguntas = parse_gift("::T:: Q {=Con `\\=\\=` compara ~Usa `\\=\\=\\=` #no \\#1 ~otra}")["questions"]
    textos = [c["text"]["text"] for c in preguntas[0]["choices"]]
    assert textos == ["Con `==` compara", "Usa `===`", "otra"]
    assert preguntas[0]["choices"][1]["feedback"]["text"] == "no #1"
