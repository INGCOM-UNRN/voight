"""`fix format` alinea los bloques ```tabla; las etiquetas se escriben sin `:`."""
from voight.core.codigo import transformar_codigo
from voight.core.converter import gift_to_xml, xml_to_gift
from voight.core.formatter import alinear_tablas, format_content
from voight.core.parser import parse_gift


def bloque(*filas):
    return "```tabla\n" + "\n".join(filas) + "\n```"


def test_alinea_los_delimitadores_de_las_columnas():
    resultado = alinear_tablas(bloque("| Paso | Valor |", "|---|---|", "| `[M1]` |  |", "| a | bb |"))
    assert resultado == bloque("| Paso   | Valor |", "| ------ | ----- |", "| `[M1]` |       |", "| a      | bb    |")


def test_es_idempotente():
    una_vez = alinear_tablas(bloque("| Paso | Valor |", "|---|---|", "| `[M1]` |  |"))
    assert alinear_tablas(una_vez) == una_vez


def test_los_comentarios_de_opciones_no_se_tocan():
    resultado = alinear_tablas(bloque("// [centrado] [ancho, 80%]", "| aaaa | b |", "|---|---|"))
    assert resultado.split("\n")[1] == "// [centrado] [ancho, 80%]"
    assert "| aaaa | b   |" in resultado


def test_un_pipe_escapado_o_en_codigo_no_separa_columnas():
    resultado = alinear_tablas(bloque("| a | b |", "|---|---|", "| `x || y` | c \\| d |"))
    assert "| `x || y` | c \\| d |" in resultado and "| a        | b      |" in resultado


def test_conserva_la_alineacion_del_separador():
    resultado = alinear_tablas(bloque("| aaaaa | bbbbb | ccccc |", "|:---|:---:|---:|"))
    assert "| :---- | :---: | ----: |" in resultado


def test_los_caracteres_anchos_ocupan_dos_columnas():
    resultado = alinear_tablas(bloque("| ｛ | b |", "|---|---|", "| aaaa | c |"))
    assert "| ｛   | b   |" in resultado


def test_completa_las_filas_cortas():
    assert alinear_tablas(bloque("| a | b |", "|---|---|", "| c |")).endswith("| c   |     |\n```")


def test_otros_bloques_no_se_tocan():
    texto = "```c\n| a |\n|---|\n```"
    assert alinear_tablas(texto) == texto


def test_fix_format_alinea_en_gift_y_en_xml():
    gift = format_content("::a::[markdown]Mirá\n" + bloque("| aaa | b |", "|---|---|") + "\n{}\n", "gift")
    assert "| aaa | b   |" in gift
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<quiz><question type="essay"><name><text>a</text></name>'
           '<questiontext format="markdown"><text><![CDATA[Mirá\n' + bloque("| aaa | b |", "|---|---|")
           + ']]></text></questiontext></question></quiz>\n')
    assert "| aaa | b   |" in format_content(xml, "xml")


def test_format_es_idempotente_con_tablas():
    gift = "::a::[markdown]Mirá\n" + bloque("// [centrado]", "| aaa | b |", "|---|---|") + "\n{}\n"
    una_vez = format_content(gift, "gift")
    assert format_content(una_vez, "gift") == una_vez and "// [centrado]" in una_vez


def test_una_tabla_no_se_protege_como_codigo():
    texto = bloque("| `[x]` | b |", "|---|---|")
    assert transformar_codigo(texto, fullwidth=True, espacios=True, saltos=True, contexto="gift")[0] == texto


def test_las_etiquetas_se_leen_con_coma_y_con_dos_puntos():
    pregunta = parse_gift("// [tag, a, b] [tag, c]\n// [tag:d]\n::p::Texto {T}\n")["questions"][0]
    assert pregunta["tags"] == ["a", "b", "c", "d"]


def test_ida_y_vuelta_de_las_etiquetas_sin_dos_puntos():
    xml = gift_to_xml("// [tag, a, b]\n::p::Texto {T}\n")
    assert "<tag>" in xml
    assert xml_to_gift(xml).startswith("// [tag, a, b]\n")
