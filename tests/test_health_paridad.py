"""`health` sobre el modelo unificado: mismas métricas para GIFT y Moodle XML."""

import json

from click.testing import CliRunner

from voight.cli import cli
from voight.core.converter import gift_to_xml
from voight.core.moodle_health import (
    auditar_archivos,
    auditar_feedback,
    auditar_longitudes,
    auditar_opciones,
    auditar_porcentajes,
    generar_reporte_markdown,
    limpiar_html_archivo,
)
from voight.core.parser import parse_gift

runner = CliRunner()

BANCO = """::Larga:: ¿Qué es un puntero? {
    =Una variable que guarda la dirección de memoria de otra variable del programa #Bien
    ~Un número #Mal
    ~Una letra
    ~Un tipo
}

::Pocas:: ¿Sí? {=Sí ~No}

::Parcial:: Elegí {=Correcta ~%50%Media ~%-50%Mala ~Otra}

::Multiple:: Elegí dos {~%50%A ~%50%B ~%-100%C}

::Invalida:: Elegí {~%33.33%A ~%33.33%B ~%33.33%C ~D}

::Repetida:: ¿Cuál? {=uno ~dos ~Dos ~tres ####Repasá}

::VF:: ¿Cierto? {T#No#Sí}
"""


def _preguntas(texto=BANCO):
    return parse_gift(texto)["questions"]


def test_porcentajes_respuesta_unica_multiple_e_invalidas():
    res = auditar_porcentajes(_preguntas())
    assert res["total_preguntas"] == 6
    # =Correcta con crédito parcial es válida; ~%50% ~%50% suma 100.
    assert res["preguntas_inconsistentes"] == []
    invalidas = res["fracciones_invalidas"]
    assert [i["titulo"] for i in invalidas] == ["Invalida"]
    assert invalidas[0]["fracciones"] == [33.33, 33.33, 33.33]
    sin_100 = auditar_porcentajes(_preguntas("::X:: Q {~%60%a ~%30%b ~c}"))
    assert sin_100["preguntas_inconsistentes"][0]["suma_positivos"] == 90
    assert auditar_porcentajes(_preguntas("::X:: Q {~a ~b}"))["preguntas_sin_correcta"][0]["titulo"] == "X"


def test_feedback_general_y_por_opcion():
    res = auditar_feedback(_preguntas())
    assert res["total_preguntas"] == 7
    assert res["con_feedback_global"] == 1
    sin = {p["titulo"] for p in res["preguntas_sin_feedback"]}
    assert sin == {"Pocas", "Parcial", "Multiple", "Invalida"}
    parcial = {p["titulo"]: p["opciones_sin_feedback"] for p in res["preguntas_feedback_parcial"]}
    assert parcial == {"Larga": 2, "Repetida": 4}
    assert res["opciones_total"] == 4 + 2 + 4 + 3 + 4 + 4 + 2
    assert res["opciones_con_feedback"] == 4


def test_cantidad_de_opciones_y_repetidas():
    res = auditar_opciones(_preguntas(), min_opciones=3)
    assert res["distribucion_mc"] == {"2": 1, "3": 1, "4": 4}
    assert [p["titulo"] for p in res["preguntas_pocas_opciones"]] == ["Pocas"]
    assert res["preguntas_opciones_repetidas"][0]["repetidas"] == ["dos"]


def test_longitud_relativa_de_las_respuestas():
    res = auditar_longitudes(_preguntas(), umbral=1.5)
    larga = {p["titulo"]: p["razon"] for p in res["preguntas_correcta_mas_larga"]}
    # En "Parcial" cuentan como correctas las de crédito positivo: 6.5 vs 4 caracteres.
    assert set(larga) == {"Larga", "Parcial"}
    assert larga["Larga"] > 5 and larga["Parcial"] == 1.62
    assert res["correcta_es_la_mas_larga"] >= 1
    assert 0 < res["correcta_es_la_mas_larga_esperado"] < res["preguntas_revisadas"]


def test_mismo_banco_en_gift_y_en_xml_da_el_mismo_diagnostico(tmp_path):
    gift = tmp_path / "banco.gift"
    xml = tmp_path / "banco.xml"
    gift.write_text(BANCO, encoding="utf-8")
    xml.write_text(gift_to_xml(BANCO), encoding="utf-8")
    res_gift = auditar_archivos([gift])
    res_xml = auditar_archivos([xml])

    def sin_archivos(valor):
        if isinstance(valor, dict):
            return {k: sin_archivos(v) for k, v in valor.items() if k != "archivo"}
        if isinstance(valor, list):
            return [sin_archivos(v) for v in valor]
        return valor

    for seccion in ("porcentajes", "retroalimentacion", "opciones", "longitud"):
        assert sin_archivos(res_gift[seccion]) == sin_archivos(res_xml[seccion]), seccion
    assert res_gift["estructura"]["por_tipo"] == res_xml["estructura"]["por_tipo"]


def test_reporte_markdown_incluye_las_secciones_nuevas(tmp_path):
    banco = tmp_path / "banco.gift"
    banco.write_text(BANCO, encoding="utf-8")
    reporte = generar_reporte_markdown(auditar_archivos([banco]), "banco.gift")
    for titulo in ("Estadísticas Generales", "Calidad y Claves de Corrección", "Retroalimentación",
                   "Cantidad de Opciones", "Longitud Relativa de las Respuestas", "Código"):
        assert f"## {titulo}" in reporte
    assert "Moodle rechaza al importar" in reporte


def test_codigo_y_backticks_sin_cerrar(tmp_path):
    banco = tmp_path / "c.gift"
    banco.write_text("::C:: Ver\n```c\nint a = 1;\n\nint b;\n```\n{=`x ~y}\n", encoding="utf-8")
    res = auditar_archivos([banco])
    assert res["codigo"]["sin_proteger"] == 1
    assert res["codigo"]["lineas_vacias"] == 1
    assert res["estructura"]["preguntas_codigo_sin_cerrar"][0]["titulo"] == "C"


def test_limpiar_html_en_xml_solo_dentro_de_text():
    xml = ('<quiz><question type="essay"><questiontext format="html">'
           '<text><![CDATA[<font color="red">Hola</font>]]></text></questiontext></question></quiz>')
    limpio = limpiar_html_archivo(xml, "xml")
    assert "<![CDATA[Hola]]>" in limpio
    assert '<questiontext format="html">' in limpio


def test_cli_health_directorio_mixto_json(tmp_path):
    (tmp_path / "a.gift").write_text(BANCO, encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.xml").write_text(gift_to_xml(BANCO), encoding="utf-8")
    res = runner.invoke(cli, ["health", str(tmp_path), "-r", "--json"])
    assert res.exit_code == 1, res.output  # BANCO tiene porcentajes que Moodle rechaza
    datos = json.loads(res.output)
    assert datos["ok"] is False
    claves = {e["clave"]: e["cantidad"] for e in datos["resumen"]["errores"]}
    assert claves == {"fracciones_invalidas": 2}
    assert datos["formato"] == "mixto"
    assert datos["archivos"]["por_formato"] == {"gift": 1, "xml": 1}
    assert datos["estructura"]["total_preguntas"] == 14
    assert len(datos["porcentajes"]["fracciones_invalidas"]) == 2


def test_cli_health_md_y_opciones(tmp_path):
    banco = tmp_path / "a.xml"
    banco.write_text(gift_to_xml(BANCO), encoding="utf-8")
    salida = tmp_path / "salud.md"
    res = runner.invoke(cli, ["health", str(banco), "--md", str(salida), "--min-opciones", "5"])
    assert res.exit_code == 1, res.output
    assert "❌ 1 errores" in res.output
    texto = salida.read_text(encoding="utf-8")
    assert "`a.xml`" in texto and "opción múltiple: 5" in texto
    assert "## Resultado" in texto and "**Error:** 1 preguntas con porcentajes que Moodle rechaza" in texto


def test_cli_health_codigos_de_salida(tmp_path):
    sano = tmp_path / "sano.gift"
    sano.write_text("::P:: ¿Cuál? {=a #bien ~b #mal ~c #mal}\n", encoding="utf-8")
    res = runner.invoke(cli, ["health", str(sano)])
    assert res.exit_code == 0, res.output
    assert "✅ Sin errores" in res.output
    # Sin feedback general es sólo una advertencia: falla únicamente con --estricto.
    con_advertencia = tmp_path / "adv.gift"
    con_advertencia.write_text("::P:: ¿Cuál? {=a ~b ~c}\n", encoding="utf-8")
    assert runner.invoke(cli, ["health", str(con_advertencia)]).exit_code == 0
    assert runner.invoke(cli, ["health", str(con_advertencia), "--estricto"]).exit_code == 1
    # Una línea en blanco en el código de un GIFT corta la pregunta: es un error.
    roto = tmp_path / "roto.gift"
    roto.write_text("::P:: Ver\n```c\nint a;\n\nint b;\n```\n{=a ~b ~c}\n", encoding="utf-8")
    res = runner.invoke(cli, ["health", str(roto), "--json"])
    assert res.exit_code == 1
    claves = {e["clave"] for e in json.loads(res.output)["resumen"]["errores"]}
    assert "codigo_gift_lineas_vacias" in claves


def test_cli_health_directorio_sin_r_sugiere_recursivo(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.gift").write_text("::P:: Q {=a ~b ~c}\n", encoding="utf-8")
    res = runner.invoke(cli, ["health", str(tmp_path)])
    assert res.exit_code == 1
    assert "usá -r" in res.output


def test_reporte_de_banco_vacio_no_inventa_porcentajes(tmp_path):
    vacio = tmp_path / "v.xml"
    vacio.write_text("<quiz></quiz>", encoding="utf-8")
    reporte = generar_reporte_markdown(auditar_archivos([vacio]), "v.xml")
    assert "**Cobertura de Feedback:** — (0 sin explicación)" in reporte


def test_cli_health_json_y_md_juntos(tmp_path):
    banco = tmp_path / "a.gift"
    banco.write_text("::P:: ¿Cuál? {=a #bien ~b #no ~c #no ####g}\n", encoding="utf-8")
    salida = tmp_path / "salud.md"
    res = runner.invoke(cli, ["health", str(banco), "--json", "--md", str(salida)])
    assert res.exit_code == 0 and json.loads(res.output)["ok"] is True
    assert salida.read_text(encoding="utf-8").startswith("# 🏥 Informe de Salud")
