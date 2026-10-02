"""Editor web: lectura y guardado de cada tipo de pregunta, en Moodle XML y GIFT."""

import pytest

flask = pytest.importorskip("flask", reason="editor web: requiere el extra opcional 'ui' (uv sync --extra ui)")

from questions.core.moodle_xml import parse_xml  # noqa: E402
from questions.ui.app import create_app  # noqa: E402


def _xml(cuerpo: str, tipo: str, nombre: str = "P", previo: str = "") -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<quiz>{previo}
<question type="{tipo}">
<name><text>{nombre}</text></name>
<questiontext format="html"><text><![CDATA[Enunciado]]></text></questiontext>
<generalfeedback format="html"><text></text></generalfeedback>
<defaultgrade>1</defaultgrade><penalty>0.3333333</penalty><hidden>0</hidden>
{cuerpo}
</question></quiz>'''


ARCHIVOS = {
    "matching.xml": _xml('''<shuffleanswers>true</shuffleanswers>
<subquestion format="html"><text><![CDATA[Perro]]></text><answer><text>Ladra</text></answer></subquestion>
<subquestion format="html"><text><![CDATA[Gato]]></text><answer><text>Maúlla</text></answer></subquestion>''', "matching"),
    "numerica.xml": _xml('''<answer fraction="100" format="moodle_auto_format"><text>3.14</text>
<feedback format="html"><text>Bien</text></feedback><tolerance>0.01</tolerance></answer>
<units><unit><multiplier>1</multiplier><unit_name>m</unit_name></unit></units>
<unitgradingtype>0</unitgradingtype>''', "numerical"),
    "calculada.xml": _xml('''<answer fraction="100"><text>{a} + {b}</text><tolerance>0.01</tolerance>
<tolerancetype>1</tolerancetype><correctanswerformat>1</correctanswerformat><correctanswerlength>2</correctanswerlength>
<feedback format="html"><text></text></feedback></answer>
<dataset_definitions><dataset_definition><status><text>private</text></status><name><text>a</text></name>
<type>calculated</type><distribution><text>uniform</text></distribution><minimum><text>1</text></minimum>
<maximum><text>10</text></maximum><decimals><text>1</text></decimals><itemcount>0</itemcount>
<dataset_items></dataset_items><number_of_items>0</number_of_items></dataset_definition></dataset_definitions>''',
                         "calculated"),
    "ordenar.xml": _xml('''<layouttype>VERTICAL</layouttype><selecttype>ALL</selecttype>
<answer fraction="1" format="html"><text>Primero</text></answer>
<answer fraction="2" format="html"><text>Segundo</text></answer>
<answer fraction="3" format="html"><text>Tercero</text></answer>''', "ordering"),
    "huecos.xml": _xml('''<shuffleanswers>1</shuffleanswers>
<selectoption><text>gato</text><group>1</group></selectoption>
<selectoption><text>perro</text><group>1</group></selectoption>''', "gapselect"),
    "arrastrar.xml": _xml('''<shuffleanswers>1</shuffleanswers>
<dragbox><text>rojo</text><group>1</group></dragbox>
<dragbox><text>azul</text><group>1</group><infinite/></dragbox>''', "ddwtos"),
    "imagen.xml": _xml('''<shuffleanswers/><file name="fondo.png" encoding="base64">iVBORw0KGgo=</file>
<drag><no>1</no><text>Norte</text><draggroup>1</draggroup></drag>
<drop><text></text><no>1</no><choice>1</choice><xleft>10</xleft><ytop>20</ytop></drop>''', "ddimageortext"),
    "cloze.xml": _xml("", "multianswer").replace("Enunciado", "Capital: {1:SHORTANSWER:=París}"),
    "ensayo.xml": _xml('''<responseformat>editor</responseformat><responserequired>1</responserequired>
<responsefieldlines>15</responsefieldlines><attachments>0</attachments>
<graderinfo format="html"><text>Mirar X</text></graderinfo>''', "essay"),
    "vf.xml": _xml('''<answer fraction="100" format="moodle_auto_format"><text>true</text>
<feedback format="html"><text>Sí</text></feedback></answer>
<answer fraction="0" format="moodle_auto_format"><text>false</text>
<feedback format="html"><text>No</text></feedback></answer>''', "truefalse"),
    # Una exportación de Moodle: categoría primero, comentario de clasificación y código con <.
    "exportado.xml": _xml('''<answer fraction="100" format="html"><text>n</text></answer>
<answer fraction="0" format="html"><text>1</text></answer>''', "multichoice", nombre="Bucle",
                          previo='''<question type="category"><category><text>$course$/Bucles</text></category></question>
<!-- [bloom:B2-comprender] -->''').replace("Enunciado", "for(i=0;i<n;i++) ¿Cuántas?"),
}


@pytest.fixture()
def cliente(tmp_path):
    for nombre, contenido in ARCHIVOS.items():
        (tmp_path / nombre).write_text(contenido, encoding="utf-8")
    app = create_app(str(tmp_path))
    app.config["RAIZ"] = tmp_path
    return app.test_client()


def _ida_y_vuelta(cliente, archivo, cambiar=None):
    q = cliente.get(f"/api/question/{archivo}").get_json()
    if cambiar:
        cambiar(q)
    r = cliente.put(f"/api/question/{archivo}", json=q).get_json()
    assert r.get("success"), r
    return cliente.get(f"/api/question/{archivo}").get_json()


@pytest.mark.parametrize("archivo,modo", [
    ("matching.xml", "pairs"), ("numerica.xml", "numerical"), ("calculada.xml", "formulas"),
    ("ordenar.xml", "ordering"), ("huecos.xml", "groups"), ("arrastrar.xml", "groups"),
    ("imagen.xml", "none"), ("cloze.xml", "none"), ("ensayo.xml", "none"), ("vf.xml", "truefalse"),
    ("exportado.xml", "choices"),
])
def test_xml_modo_y_guardar_sin_cambios_es_idempotente(cliente, archivo, modo):
    antes = cliente.get(f"/api/question/{archivo}").get_json()
    assert antes["answer_mode"] == modo
    despues = _ida_y_vuelta(cliente, archivo)
    assert despues == antes
    ruta = cliente.application.config["RAIZ"] / archivo
    assert parse_xml(ruta.read_text(encoding="utf-8"))["success"]


def test_xml_conserva_lo_que_el_editor_no_toca(cliente):
    raiz = cliente.application.config["RAIZ"]
    for archivo in ("numerica.xml", "calculada.xml", "imagen.xml", "ordenar.xml", "exportado.xml"):
        _ida_y_vuelta(cliente, archivo)
    assert "<unit_name>m</unit_name>" in (raiz / "numerica.xml").read_text(encoding="utf-8")
    calculada = (raiz / "calculada.xml").read_text(encoding="utf-8")
    assert "<dataset_definition>" in calculada and "<tolerancetype>1</tolerancetype>" in calculada
    imagen = (raiz / "imagen.xml").read_text(encoding="utf-8")
    assert "<xleft>10</xleft>" in imagen and 'name="fondo.png"' in imagen
    assert "<layouttype>VERTICAL</layouttype>" in (raiz / "ordenar.xml").read_text(encoding="utf-8")
    exportado = (raiz / "exportado.xml").read_text(encoding="utf-8")
    assert "i<n" in exportado and "&lt;" not in exportado.split("CDATA[for")[1].split("]]>")[0]
    assert "[bloom:B2-comprender]" in exportado and "$course$/Bucles" in exportado


def test_xml_lee_la_pregunta_y_no_la_categoria(cliente):
    q = cliente.get("/api/question/exportado.xml").get_json()
    assert q["type"] == "multichoice" and q["name"] == "Bucle"
    arbol = {i["name"]: i for i in cliente.get("/api/tree").get_json()}
    assert arbol["exportado.xml"]["question_type"] == "multichoice"
    assert arbol["exportado.xml"]["options"] == 2


def test_xml_matching_agrega_y_quita_pares(cliente):
    def cambiar(q):
        q["subquestions"] = [q["subquestions"][1], {"text": "Vaca", "answer": "Muge"}, {"text": "", "answer": "Relincha"}]
    q = _ida_y_vuelta(cliente, "matching.xml", cambiar)
    assert q["subquestions"] == [{"text": "Gato", "answer": "Maúlla"}, {"text": "Vaca", "answer": "Muge"},
                                 {"text": "", "answer": "Relincha"}]
    assert "<answer fraction" not in (cliente.application.config["RAIZ"] / "matching.xml").read_text(encoding="utf-8")


def test_xml_numerica_y_calculada_editan_la_tolerancia(cliente):
    def cambiar(q):
        q["answers"][0]["tolerance"] = "0.5"
        q["answers"].append({"fraction": "50", "text": "3", "tolerance": "1", "feedback": "Cerca"})
    q = _ida_y_vuelta(cliente, "numerica.xml", cambiar)
    assert [(a["text"], a["tolerance"], a["fraction"]) for a in q["answers"]] == [("3.14", "0.5", "100"), ("3", "1", "50")]

    q = _ida_y_vuelta(cliente, "calculada.xml", lambda q: q["answers"][0].update(text="{a} * 2"))
    assert q["answers"][0]["text"] == "{a} * 2" and q["datasets"] == [{"name": "a", "min": "1", "max": "10"}]


def test_xml_ordenar_guarda_el_orden(cliente):
    q = _ida_y_vuelta(cliente, "ordenar.xml", lambda q: q["answers"].reverse())
    assert [a["text"] for a in q["answers"]] == ["Tercero", "Segundo", "Primero"]
    assert [a["fraction"] for a in q["answers"]] == ["1", "2", "3"]


def test_xml_huecos_grupos_e_ilimitadas(cliente):
    q = _ida_y_vuelta(cliente, "huecos.xml", lambda q: q["choices"].append({"text": "loro", "group": "2"}))
    assert q["choices"][-1] == {"text": "loro", "group": "2", "infinite": False}

    def cambiar(q):
        q["choices"][0]["infinite"] = True
        q["choices"][1]["infinite"] = False
    q = _ida_y_vuelta(cliente, "arrastrar.xml", cambiar)
    assert [c["infinite"] for c in q["choices"]] == [True, False]


def test_xml_opciones_propias_del_tipo(cliente):
    q = _ida_y_vuelta(cliente, "ensayo.xml", lambda q: q.update(responseformat="plain", responserequired="0",
                                                                 attachments="2", graderinfo="Mirar Y"))
    assert (q["responseformat"], q["responserequired"], q["attachments"], q["graderinfo"]) == ("plain", "0", "2", "Mirar Y")

    q = _ida_y_vuelta(cliente, "vf.xml", lambda q: q.update(answers=[
        {"text": "true", "fraction": "0", "feedback": "Era falsa"}, {"text": "false", "fraction": "100", "feedback": "Bien"}]))
    assert [(a["text"], a["fraction"]) for a in q["answers"]] == [("true", "0"), ("false", "100")]


# -- GIFT --------------------------------------------------------------------

def _gift(tmp_path, contenido):
    (tmp_path / "p.gift").write_text(contenido, encoding="utf-8")
    return create_app(str(tmp_path)).test_client()


@pytest.mark.parametrize("contenido,modo", [
    ("::VF:: ¿Sí? {T#Mal#Bien}\n", "truefalse"),
    ("::M:: Uní. {=a -> 1 =b -> 2}\n", "pairs"),
    ("::N:: ¿Pi? {#3.14:0.01}\n", "numerical"),
    ("::R:: Entre uno y cinco {#1..5}\n", "numerical"),
    ("::MW:: El {=gato ~perro} maúlla.\n", "choices"),
    ("::S:: ¿Capital? {=París =paris}\n", "choices"),
    ("::E:: Escribí. {}\n", "none"),
    ("::D:: Sólo texto\n", "none"),
])
def test_gift_guardar_sin_cambios_conserva_la_pregunta(tmp_path, contenido, modo):
    cliente = _gift(tmp_path, contenido)
    antes = cliente.get("/api/question/p.gift").get_json()
    assert antes["answer_mode"] == modo
    assert _ida_y_vuelta(cliente, "p.gift") == antes


def test_gift_verdadero_falso_conserva_cada_retro(tmp_path):
    cliente = _gift(tmp_path, "::VF:: ¿Sí? {T#Mal#Bien}\n")
    q = cliente.get("/api/question/p.gift").get_json()
    assert {a["text"]: a["feedback"] for a in q["answers"]} == {"true": "Bien", "false": "Mal"}
    q = _ida_y_vuelta(cliente, "p.gift", lambda q: q.update(answers=[
        {"text": "true", "fraction": "0", "feedback": "No"}, {"text": "false", "fraction": "100", "feedback": "Eso"}]))
    assert {a["text"]: (a["fraction"], a["feedback"]) for a in q["answers"]} == {"true": ("0", "No"), "false": ("100", "Eso")}


def test_gift_emparejamiento_y_numerica(tmp_path):
    cliente = _gift(tmp_path, "::M:: Uní. {=a -> 1 =b -> 2}\n")
    q = _ida_y_vuelta(cliente, "p.gift", lambda q: q["subquestions"].append({"text": "c", "answer": "3"}))
    assert [p["answer"] for p in q["subquestions"]] == ["1", "2", "3"]

    cliente = _gift(tmp_path, "::R:: Entre uno y cinco {#1..5}\n")
    q = cliente.get("/api/question/p.gift").get_json()
    assert (q["answers"][0]["text"], q["answers"][0]["tolerance"]) == ("3", "2")


def test_gift_palabra_faltante_queda_en_su_lugar(tmp_path):
    cliente = _gift(tmp_path, "::MW:: El {=gato ~perro} maúlla.\n")
    _ida_y_vuelta(cliente, "p.gift", lambda q: q["answers"].append({"fraction": "0", "text": "loro", "feedback": ""}))
    texto = (tmp_path / "p.gift").read_text(encoding="utf-8")
    assert texto.rstrip().endswith("} maúlla.") and "~loro" in texto


def test_gift_conserva_el_resto_del_archivo_y_edita_los_tags(tmp_path):
    contenido = ("$CATEGORY: $course$/Animales\n\n// [bloom:B1-recordar]\n// [id:p1] [tag:viejo]\n"
                 "::Primera:: ¿Ladra? {T}\n\n::Segunda:: ¿Maúlla? {F}\n")
    cliente = _gift(tmp_path, contenido)
    _ida_y_vuelta(cliente, "p.gift", lambda q: q.update(questiontext="¿Ladra el perro?", tags=["nuevo"]))
    texto = (tmp_path / "p.gift").read_text(encoding="utf-8")
    assert texto.startswith("$CATEGORY: $course$/Animales\n")
    assert "// [bloom:B1-recordar]" in texto and "[id:p1]" in texto
    assert "[tag:viejo]" not in texto and "[tag:nuevo]" in texto
    assert "¿Ladra el perro?" in texto and "::Segunda:: ¿Maúlla? {F}" in texto
