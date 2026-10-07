"""Calidad del banco: metadatos de clasificación, blueprint y señales de redacción en health."""

from voight.core.moodle_xml import parse_xml
from voight.core.parser import parse_gift


def test_metadatos_de_clasificacion_en_gift_y_xml():
    gift = "// [tag:x] [bloom:B3-aplicar] [dificultad-enunciado:3.4/5] [clasificacion:jev-1.13.0 confianza=1]\n::A:: q {T}"
    assert parse_gift(gift)["questions"][0]["metadata"] == {
        "bloom": "aplicar", "dificultad_enunciado": 3.4, "clasificador": "jev-1.13.0", "confianza": [1.0]}
    xml = ('<quiz><!-- question: 1 --><!-- [bloom:B1-recordar] [dificultad-respuestas:2/5] -->'
           '<question type="truefalse"><name><text>x</text></name><questiontext><text>q</text></questiontext>'
           '<tags><tag><text>dificultad-enunciado:4</text></tag></tags></question>'
           '<question type="truefalse"><name><text>y</text></name><questiontext><text>q</text></questiontext></question></quiz>')
    primera, segunda = parse_xml(xml)["questions"]
    assert primera["metadata"] == {"bloom": "recordar", "dificultad_respuestas": 2.0, "dificultad_enunciado": 4.0}
    assert "metadata" not in segunda  # el comentario es de la pregunta que sigue, no de todas


def test_health_clasificacion_y_blueprint(tmp_path):
    from voight.core.moodle_health import auditar_archivos, generar_reporte_markdown

    gift = "$CATEGORY: $course$/C/Punteros\n\n"
    for i in range(5):
        gift += f"// [bloom:B{1 + i % 2}-{'recordar' if i % 2 == 0 else 'comprender'}] [dificultad-enunciado:{1 + i}/5]\n::P{i}:: q{i}? {{=a ~b ~c}}\n\n"
    gift += "$CATEGORY: $course$/C/Arreglos\n\n// [bloom:B4-analizar]\n::A:: q? {=a ~b ~c}\n\n::S:: sin clasificar {=a ~b ~c}\n"
    (tmp_path / "banco.gift").write_text(gift, encoding="utf-8")
    sub = tmp_path / "Java" / "Excepciones"
    sub.mkdir(parents=True)
    (sub / "e.gift").write_text("// [bloom:B5-evaluar]\n::E:: q? {=a ~b ~c}\n", encoding="utf-8")

    res = auditar_archivos([tmp_path / "banco.gift", sub / "e.gift"])
    cla = res["clasificacion"]
    assert cla["evaluables"] == 8 and cla["clasificadas"] == 7
    assert cla["bloom"]["recordar"] == 3 and cla["bloom"]["analizar"] == 1 and cla["bloom"]["evaluar"] == 1
    assert cla["dificultad_enunciado_media"] == 3.0
    assert set(cla["blueprint"]) == {"C/Punteros", "C/Arreglos", "Java/Excepciones"}
    assert cla["categorias_sin_niveles_altos"] == [{"categoria": "C/Punteros", "clasificadas": 5}]
    assert any(a["clave"] == "sin_niveles_altos" for a in res["resumen"]["advertencias"])
    reporte = generar_reporte_markdown(res, "banco")
    assert "## Clasificación (Bloom y dificultad)" in reporte and "| C/Punteros | 3 | 2 | · | · | · | · | 5 |" in reporte


def test_health_redaccion():
    from voight.core.moodle_health import auditar_redaccion
    from voight.core.parser import parse_gift as p

    gift = (
        "::A:: ¿Cuál es correcta? {=uno ~dos ~Todas las anteriores}\n\n"
        "::B:: ¿Cuál de estas NO es válida? {=a ~b ~c}\n\n"
        "::C:: ¿Cuál de estas no es válida? {=a ~b ~c}\n\n"
        "::D:: ¿Cuál es **incorrecta**? {~a =b ~c}\n\n"
        "::E:: Defina puntero {=Una variable que guarda la dirección de memoria de otra ~x ~y}\n"
    )
    res = auditar_redaccion(p(gift)["questions"])
    assert res["preguntas_revisadas"] == 5
    assert res["posicion_correcta"] == {"1": 4, "2": 1} and res["correcta_primera"] == 4
    assert [i["titulo"] for i in res["preguntas_opciones_problematicas"]] == ["A"]
    assert [(i["titulo"], i["negaciones"]) for i in res["preguntas_negacion_sin_resaltar"]] == [("C", ["no es"])]
    assert [i["titulo"] for i in res["preguntas_distractores_debiles"]] == ["E"]


def test_moodle_xml_expone_los_campos_de_moodle():
    from voight.core.moodle_xml import parse_xml

    xml = ('<quiz><question type="multichoice"><name><text>x</text></name><questiontext><text>q</text></questiontext>'
           '<penalty>0.3333333</penalty><defaultgrade>1</defaultgrade><shuffleanswers>0</shuffleanswers>'
           '<answer fraction="100"><text>a</text></answer></question></quiz>')
    assert parse_xml(xml)["questions"][0]["moodle"] == {"penalty": "0.3333333", "defaultgrade": "1", "shuffleanswers": "0"}


def test_health_metadatos_de_moodle_por_categoria(tmp_path):
    from voight.core.moodle_health import auditar_archivos

    def pregunta(nombre, penalty, grade):
        return (f'<question type="multichoice"><name><text>{nombre}</text></name><questiontext><text>q</text>'
                f'</questiontext><penalty>{penalty}</penalty><defaultgrade>{grade}</defaultgrade>'
                '<answer fraction="100"><text>a</text></answer><answer fraction="0"><text>b</text></answer></question>')
    xml = ('<quiz><question type="category"><category><text>$course$/C</text></category></question>'
           + pregunta("a", "0.3333333", "1") + pregunta("b", "0.33333330", "1.0") + pregunta("c", "0.1", "1") + "</quiz>")
    (tmp_path / "b.xml").write_text(xml, encoding="utf-8")
    moo = auditar_archivos([tmp_path / "b.xml"])["moodle"]
    assert moo["preguntas_revisadas"] == 3
    assert moo["inconsistencias"] == [{"categoria": "C", "tipo": "MC", "campo": "penalty",
                                       "valores": {"0.333333": 2, "0.1": 1}}]


def test_health_csv_una_fila_por_pregunta(tmp_path):
    import csv

    from click.testing import CliRunner

    from voight.cli import cli

    (tmp_path / "b.gift").write_text(
        "$CATEGORY: $course$/C\n\n// [bloom:B3-aplicar] [dificultad-enunciado:2.5/5]\n"
        "::A:: ¿Cuál NO es? {=Una respuesta bastante más larga que el resto #bien ~x ~y ####gen}\n\n"
        "::B:: ¿Cuál? {~%33.33%a ~%33.33%b ~%33.33%c ~d}\n", encoding="utf-8")
    salida = tmp_path / "salud.csv"
    res = CliRunner().invoke(cli, ["health", str(tmp_path / "b.gift"), "--csv", str(salida), "--json"])
    assert '"_preguntas"' not in res.output
    filas = list(csv.DictReader(salida.open(encoding="utf-8")))
    a, b = filas
    assert (a["titulo"], a["categoria"], a["bloom"], a["dificultad_enunciado"]) == ("A", "C", "aplicar", "2.5")
    assert (a["opciones"], a["correctas"], a["feedback_general"], a["opciones_con_feedback"]) == ("3", "1", "1", "1")
    assert a["correcta_mas_larga"] == "1" and a["distractores_debiles"] == "2" and a["negacion_sin_resaltar"] == "0"
    assert b["fraccion_invalida"] == "1" and b["sin_correcta"] == "0"
