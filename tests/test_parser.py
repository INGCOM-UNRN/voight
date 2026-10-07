from voight.core.parser import parse_gift_file

def test_parse_simple_gift(tmp_path):
    gift_content = "::Title:: Question {=Ans ~Wrong}"
    d = tmp_path / "test.gift"
    d.write_text(gift_content)
    
    result = parse_gift_file(str(d))
    
    assert result["success"] is True
    assert result["questionCount"] == 1
    assert result["questions"][0]["title"] == "Title"
    assert result["questions"][0]["type"] == "MC"

def test_parse_multiple_questions(tmp_path):
    gift_content = "::Q1:: Q1 {=A}\n\n::Q2:: Q2 {=B}"
    d = tmp_path / "test.gift"
    d.write_text(gift_content)
    
    result = parse_gift_file(str(d))
    
    assert result["questionCount"] == 2
    assert result["questions"][0]["title"] == "Q1"
    assert result["questions"][1]["title"] == "Q2"


def test_palabra_faltante():
    from voight.core.parser import parse_gift

    q = parse_gift("::MW:: El {=gato ~perro #no} maúlla.")["questions"][0]
    assert q["type"] == "MC" and q["stem"]["text"] == "El _____ maúlla."
    assert [c["text"]["text"] for c in q["choices"]] == ["gato", "perro"]
    q = parse_gift("::SA:: Dos más dos es {=cuatro =4} siempre.")["questions"][0]
    assert q["type"] == "Short" and q["stem"]["text"] == "Dos más dos es _____ siempre."
    # Las llaves del código no son un bloque de respuestas.
    for texto in ("::C:: `int f(){=1}` es código", "::D:: if (a) {x=1;} listo"):
        assert parse_gift(texto)["questions"][0]["type"] == "Description"


def test_numerica_con_rango():
    from voight.core.parser import parse_gift

    q = parse_gift("::N:: Entre uno y cinco {#1..5}")["questions"][0]
    assert q["type"] == "Numerical" and q["choices"][0]["text"]["text"] == "1..5"


def test_rango_numerico_a_xml():
    from voight.core.converter import gift_to_xml, valor_y_tolerancia

    assert valor_y_tolerancia("1..5") == ("3", "2")
    assert valor_y_tolerancia("3:0.5") == ("3", "0.5")
    assert valor_y_tolerancia("7") == ("7", "")
    xml = gift_to_xml("::N:: Entre uno y cinco {#1..5}\n")
    assert "<![CDATA[3]]>" in xml and "<tolerance>2</tolerance>" in xml
