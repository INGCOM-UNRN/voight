import pytest

flask = pytest.importorskip("flask", reason="editor web: requiere el extra opcional 'ui' (uv sync --extra ui)")

from voight.ui.app import create_app  # noqa: E402


@pytest.fixture()
def cliente(tmp_path):
    (tmp_path / "banco.gift").write_text(
        "::Q GIFT:: ¿1+1? {\n=2 # sí\n~3\n}\n", encoding="utf-8"
    )
    (tmp_path / "pregunta.xml").write_text(
        '''<?xml version="1.0" encoding="UTF-8"?>
<quiz><question type="multichoice"><name><text><![CDATA[Q XML]]></text></name>
<questiontext format="html"><text><![CDATA[¿3+3?]]></text></questiontext>
<answer fraction="100" format="html"><text><![CDATA[6]]></text></answer>
<answer fraction="0" format="html"><text><![CDATA[7]]></text></answer></question></quiz>''',
        encoding="utf-8",
    )
    return create_app(str(tmp_path)).test_client()


def test_arbol_lista_ambos_formatos(cliente):
    arbol = cliente.get("/api/tree").get_json()
    nombres = {i["name"] for i in arbol}
    assert nombres == {"banco.gift", "pregunta.xml"}
    por_nombre = {i["name"]: i for i in arbol}
    assert por_nombre["banco.gift"]["format"] == "gift"
    assert por_nombre["pregunta.xml"]["format"] == "xml"


def test_get_question_gift_normaliza_al_contrato_del_editor(cliente):
    q = cliente.get("/api/question/banco.gift").get_json()
    assert q["type"] == "multichoice"
    assert q["name"] == "Q GIFT"
    assert q["source_format"] == "gift"
    fracciones = [a["fraction"] for a in q["answers"]]
    assert fracciones == ["100", "0"]
    assert q["answers"][0]["feedback"] == "sí"


def test_put_gift_guarda_y_vuelve_a_leer(cliente):
    q = cliente.get("/api/question/banco.gift").get_json()
    q["questiontext"] = "¿1+1? (editada)"
    r = cliente.put("/api/question/banco.gift", json=q).get_json()
    assert r.get("success")

    q2 = cliente.get("/api/question/banco.gift").get_json()
    assert q2["questiontext"] == "¿1+1? (editada)"


def test_get_xml_permanece_intacto(cliente):
    q = cliente.get("/api/question/pregunta.xml").get_json()
    assert q["name"] == "Q XML"
    assert len(q["answers"]) == 2


def test_busqueda_por_texto(cliente):
    resultados = cliente.get("/api/search?q=xml").get_json()
    assert any(r["filepath"] == "pregunta.xml" for r in resultados)


def test_path_traversal_bloqueado(cliente):
    assert cliente.get("/api/question/../../etc/passwd").status_code in (400, 404)


def test_arbol_informa_la_cantidad_de_opciones(tmp_path):
    (tmp_path / "cat").mkdir()
    (tmp_path / "cat" / "mc.gift").write_text("::MC:: ¿x? {=a ~b ~c ~d}\n", encoding="utf-8")
    (tmp_path / "cat" / "vf.gift").write_text("::VF:: ¿x? {T}\n", encoding="utf-8")
    (tmp_path / "par.gift").write_text("::P:: Uní. {=a -> 1 =b -> 2 =c -> 3}\n", encoding="utf-8")
    (tmp_path / "roto.xml").write_text("<quiz><question", encoding="utf-8")
    arbol = create_app(str(tmp_path)).test_client().get("/api/tree").get_json()
    por_nombre = {i["name"]: i for i in arbol}
    hijos = {i["name"]: i for i in por_nombre["cat"]["children"]}
    assert hijos["mc.gift"]["options"] == 4
    assert hijos["vf.gift"]["options"] is None
    assert por_nombre["par.gift"]["options"] == 3
    assert por_nombre["roto.xml"]["options"] is None


def test_arbol_opciones_xml(cliente):
    arbol = cliente.get("/api/tree").get_json()
    assert {i["name"]: i["options"] for i in arbol} == {"banco.gift": 2, "pregunta.xml": 2}
