"""Lector único y separación de GIFT consistente en todos los comandos."""


from voight.core.parser import parse_gift

# La línea en blanco está dentro de las llaves: no termina la pregunta.
CON_BLANCO = (
    "$CATEGORY: $course$/Funciones\n\n"
    "::Cuerpo:: ¿Qué devuelve f? {\n"
    "=int f(void) \\{\n\n    return 1;\\}\n"
    "~nada\n}\n\n"
    "::Otra:: ¿Sí? {T}\n"
)


def _preguntas(texto: str) -> list:
    return [q for q in parse_gift(texto)["questions"] if q["type"] != "Category"]


def test_tree_export_no_parte_preguntas_con_lineas_en_blanco(tmp_path):
    from voight.core.tree import gift_export

    banco = tmp_path / "banco.gift"
    banco.write_text(CON_BLANCO, encoding="utf-8")
    assert gift_export(banco, tmp_path / "arbol") == 2
    archivos = sorted((tmp_path / "arbol").rglob("*.gift"))
    assert len(archivos) == 2
    titulos = sorted(q["title"] for a in archivos for q in _preguntas(a.read_text(encoding="utf-8")))
    assert titulos == ["Cuerpo", "Otra"]
    cuerpo = (tmp_path / "arbol" / "Funciones" / "cuerpo.gift").read_text(encoding="utf-8")
    assert "return 1;" in cuerpo and "~nada" in cuerpo and cuerpo.rstrip().endswith("}")


def test_unify_no_parte_preguntas_con_lineas_en_blanco(tmp_path):
    from voight.core.unifier import unificar

    (tmp_path / "arbol" / "Funciones").mkdir(parents=True)
    (tmp_path / "arbol" / "Funciones" / "a.gift").write_text(CON_BLANCO.split("\n\n", 1)[1], encoding="utf-8")
    destino = tmp_path / "todo.gift"
    unificar([tmp_path / "arbol"], destino, formato="gift", recursivo=True)
    preguntas = _preguntas(destino.read_text(encoding="utf-8"))
    assert [q["title"] for q in preguntas] == ["Cuerpo", "Otra"]
    assert "return 1;" in preguntas[0]["choices"][0]["text"]["text"]


def test_una_pregunta_sin_cerrar_no_se_traga_el_resto():
    from voight.core.formatter import _bloques_gift

    texto = ("::Rota:: ¿Qué imprime `if (x) {`? {\n=algo\n~otra\n\n"
             "// [tag:java]\n// CAT: Clases\n::Sana:: ¿Sí? {T}\n\n"
             "$CATEGORY: $course$/Otra\n\n::Tercera:: ¿No? {F}\n")
    bloques = _bloques_gift(texto)
    assert len(bloques) == 4 and bloques[1].startswith("// [tag:java]") and bloques[2].startswith("$CATEGORY")
    titulos = [q["title"] for q in _preguntas(texto)]
    assert titulos[-2:] == ["Sana", "Tercera"]
    # Código con línea en blanco y llaves abiertas: sigue siendo una sola pregunta.
    assert len(_bloques_gift(CON_BLANCO)) == 3


def test_unify_protege_las_barras_del_codigo_respetando_los_escapes():
    from voight.core.tree import _protect_backslashes_in_code as proteger

    assert proteger("en C termina con `\\\\0`.") == "en C termina con `＼0`."          # \\ es una barra
    assert proteger('`printf("\\n")`') == '`printf("＼n")`'                          # barra cruda
    assert proteger("`a \\{ b \\}`") == "`a \\{ b \\}`"                              # escapes de GIFT
    assert proteger("```c\nputs(\"\\\\\\\\\");\n```") == "```c\nputs(\"＼＼\");\n```"   # \\\\ son dos
    assert proteger("fuera \\\\ del código") == "fuera \\\\ del código"


def test_health_lee_cada_archivo_una_vez_con_los_mismos_resultados(tmp_path):
    from voight.core.moodle_health import auditar_archivos

    crlf = tmp_path / "crlf.gift"
    crlf.write_bytes("::A:: ¿Sí?\r\n{T}\r\n\r\n::B:: ¿No? {F}\r\n".encode("utf-8"))
    latin = tmp_path / "latin.gift"
    latin.write_bytes("::C:: ¿Qué <font>es</font>? {T}\n".encode("latin-1"))
    resultado = auditar_archivos([crlf, latin])
    assert resultado["estructura"]["total_preguntas"] == 2  # las de crlf.gift
    errores = resultado["archivos"]["errores"]
    assert [e["archivo"] for e in errores] == [str(latin)] and "Error leyendo archivo" in errores[0]["error"]
    # El archivo ilegible igual se audita como texto (HTML obsoleto).
    assert [h["archivo"] for h in resultado["html_obsoleto"]] == [str(latin)]


def test_xml_a_gift_protege_el_cloze_como_las_demas_preguntas():
    from voight.core.converter import xml_to_gift

    xml = ("<quiz><question type=\"cloze\"><name><text>Completar</text></name>"
           "<questiontext format=\"html\"><text><![CDATA[<p>Completá:</p>\n<pre>\nint f(void) {\n"
           "    // paso 1\n    int x = {1:NUMERICAL:=1:0};\n    \n    return x;\n}\n</pre>]]></text></questiontext>"
           "</question><question type=\"truefalse\"><name><text>Otra</text></name>"
           "<questiontext><text>¿Sí?</text></questiontext><answer fraction=\"100\"><text>true</text></answer>"
           "</question></quiz>")
    preguntas = _preguntas(xml_to_gift(xml))
    assert [(q["type"], q.get("title")) for q in preguntas] == [("Description", "Completar"), ("TF", "Otra")]
    texto = preguntas[0]["stem"]["text"]
    assert "paso 1" in texto and "return x;" in texto  # ni el // ni la línea en blanco la cortan
