"""Secciones de código: fullwidth, marcas · y ↵, en GIFT y en Moodle XML por igual."""

import xml.etree.ElementTree as ET

from questions.core.codigo import (
    diagnosticar_codigo,
    transformar_archivo,
    transformar_codigo,
    transformar_fragmento,
)
from questions.core.parser import parse_gift

GIFT = """::P::[markdown]¿Qué imprime?
```c
#include <stdio.h>

int main() {
    int x = 5;
    if (x == 5) {
        printf("%d\\n", x); // ok
    }
}
```
{
    =`5↵`
    ~`a {b}`
}
"""


def _xml(texto: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<quiz><question type="multichoice">'
        "<name><text>P</text></name>"
        f'<questiontext format="markdown"><text><![CDATA[{texto}]]></text></questiontext>'
        '<generalfeedback format="markdown"><text/></generalfeedback>'
        '<answer fraction="100"><text><![CDATA[`a == b`]]></text></answer>'
        "</question></quiz>"
    )


def test_fullwidth_y_marcas_en_un_bloque():
    salida = transformar_fragmento("int main() {\n    return 0;\n}\n", contexto="xml")
    assert salida == "int main（） ｛↵\n····return 0；↵\n｝\n"


def test_simbolos_que_chocan_con_gift():
    salida = transformar_fragmento('a == b; c = ~d # e: "f" \\n // g', contexto="xml", espacios=False, saltos=False)
    assert salida == "a ⩵ b； c ＝ ～d ＃ e： ＂f＂ ＼n ／／ g"


def test_marcas_idempotentes_y_ultima_linea_sin_salto():
    una = transformar_fragmento("a\n  b\nc\n", contexto="xml")
    assert una == "a↵\n··b↵\nc\n"
    assert transformar_fragmento(una, contexto="xml") == una


def test_ultima_linea_en_blanco_lleva_salto():
    assert transformar_fragmento("a\n\n", contexto="xml") == "a↵\n↵\n"


def test_variantes_historicas_pasan_a_la_forma_canonica():
    # U+2007 (figure space) y U+037E (punto y coma griego) de los bancos XML.
    salida = transformar_fragmento("\u2007\u2007x \u037e\n", contexto="xml", fullwidth=True, saltos=False)
    assert salida == "··x ；\n"


def test_entidades_sin_punto_y_coma_no_se_interpretan():
    # html.unescape convertiría `&not` en `¬`: en C es & seguido de un identificador.
    salida = transformar_fragmento("p = &not_found; q = &lt;", contexto="xml", espacios=False, saltos=False)
    assert "¬" not in salida
    assert salida == "p ＝ ＆not_found； q ＝ ＜"


def test_gift_ida_y_vuelta_es_estable_y_parsea_igual():
    fw, cambios = transformar_codigo(GIFT, contexto="gift", fullwidth=True)
    assert cambios == 2
    assert transformar_codigo(fw, contexto="gift", fullwidth=True) == (fw, 0)
    normal, _ = transformar_codigo(fw, contexto="gift", fullwidth=False)
    assert transformar_codigo(normal, contexto="gift", fullwidth=True)[0] == fw
    # El original tiene una línea en blanco en el código: la pregunta se partía en dos.
    assert len(parse_gift(GIFT)["questions"]) == 2
    for texto in (fw, normal):
        preguntas = parse_gift(texto)["questions"]
        assert [(p["type"], len(p["choices"])) for p in preguntas] == [("MC", 2)]


def test_gift_normal_escapa_y_conserva_lineas_vacias():
    fw, _ = transformar_codigo(GIFT, contexto="gift", fullwidth=True)
    normal, _ = transformar_codigo(fw, contexto="gift", fullwidth=False)
    assert "int main() \\{" in normal
    assert 'printf("%d\\\\n", x);' in normal
    assert "\n↵\n" in normal  # la línea en blanco conserva su marca
    stem = parse_gift(normal)["questions"][0]["stem"]["text"]
    assert 'printf("%d\\n", x); // ok' in stem


def test_salto_a_mitad_de_linea_es_contenido_del_autor():
    texto = "salida: `hola↵mundo↵`"
    normal, _ = transformar_codigo(texto, fullwidth=False)
    assert normal == texto


def test_html_pre_code_escapa_al_restaurar():
    texto = "<pre><code>if (a &lt; b) {\n  x();\n}</code></pre>"
    fw, _ = transformar_codigo(texto, fullwidth=True, saltos=False)
    assert fw == "<pre><code>if （a ＜ b） ｛\n··x（）；\n｝</code></pre>"
    normal, _ = transformar_codigo(fw, fullwidth=False)
    assert normal == "<pre><code>if (a &lt; b) {\n  x();\n}</code></pre>"


def test_xml_cdata_y_text_vacio():
    xml = _xml("```c\nif (a == b) {\n    f();\n}\n```")
    fw, cambios = transformar_archivo(xml, "xml", fullwidth=True)
    assert cambios == 2
    ET.fromstring(fw)
    assert "if （a ⩵ b） ｛↵\n····f（）；↵\n｝\n```" in fw
    # El texto después de <text/> también se procesa (la respuesta).
    assert "`a ⩵ b`" in fw
    assert transformar_archivo(fw, "xml", fullwidth=True) == (fw, 0)


def test_xml_texto_escapado_pasa_a_cdata():
    xml = "<quiz><question><questiontext><text>Ver `a &lt; b`</text></questiontext></question></quiz>"
    fw, cambios = transformar_archivo(xml, "xml", fullwidth=True)
    assert cambios == 1
    assert "<text><![CDATA[Ver `a ＜ b`]]></text>" in fw


def test_gift_y_xml_producen_el_mismo_codigo():
    codigo = "```c\nwhile (i != 0) {\n\ti--;\n}\n```"
    gift, _ = transformar_archivo(f"::P:: {codigo}\n{{=a ~b}}", "gift", fullwidth=True)
    xml, _ = transformar_archivo(_xml(codigo), "xml", fullwidth=True)
    esperado = "while （i !＝ 0） ｛↵\n····i--；↵\n｝\n"
    assert esperado in gift
    assert esperado in xml


def test_diagnostico_con_el_mismo_criterio_en_ambos_formatos():
    assert diagnosticar_codigo(GIFT, "gift")["sin_proteger"] == 2
    assert diagnosticar_codigo(GIFT, "gift")["lineas_vacias"] == 1
    fw, _ = transformar_codigo(GIFT, contexto="gift", fullwidth=True)
    assert diagnosticar_codigo(fw, "gift") == {"secciones": 3, "sin_proteger": 0, "variantes": 0, "lineas_vacias": 0,
                                               "comentarios": 0, "sin_lenguaje": 0}
    assert diagnosticar_codigo("```\nint a;\n// nota\n```", "gift")["comentarios"] == 1
    assert diagnosticar_codigo("```\nint a;\n```\n```c\nint b;\n```")["sin_lenguaje"] == 1
    # GIFT escapado (forma normal) no cuenta como sin proteger.
    assert diagnosticar_codigo("`a \\= b`", "gift")["sin_proteger"] == 0
    assert diagnosticar_codigo("`a \\= b`", "xml")["sin_proteger"] == 1
    assert diagnosticar_codigo("`\u2007x`", "xml")["variantes"] == 1


def test_codigo_en_linea_no_cruza_otra_opcion_en_gift():
    # Un ` sin cerrar no debe comerse la opción siguiente.
    texto = "{\n    =`a #fb\n    ~b `c`\n}"
    salida, _ = transformar_codigo(texto, contexto="gift", fullwidth=True)
    assert "=`a #fb" in salida
    assert "~b `c`" in salida


def test_el_fuente_no_depende_de_caracteres_que_nfc_altera():
    # El mapa original se corrompió así: U+037E y los espacios especiales escritos
    # literalmente se vuelven `;` y espacios comunes al normalizar el archivo.
    import unicodedata
    from pathlib import Path

    import questions.core.codigo as codigo

    fuente = Path(codigo.__file__).read_text(encoding="utf-8")
    assert unicodedata.normalize("NFC", fuente) == fuente
    assert not any(c in fuente for c in "\u2007\u2000\u00a0\u3000")


def test_detectar_y_etiquetar_lenguaje():
    from questions.core.codigo import detectar_lenguaje, etiquetar_lenguaje, etiquetar_lenguaje_archivo

    assert detectar_lenguaje("＃include ＜stdio.h＞") == "c"
    assert detectar_lenguaje('System.out.println（＂a＂）；') == "java"
    assert detectar_lenguaje("def f(x):\n    return x") == "python"
    assert detectar_lenguaje("x = 1") is None
    texto = "a\n```\nint *p = NULL;\n```\nb\n```\nx = 1\n```\n```c\nint y;\n```"
    nuevo, cambios = etiquetar_lenguaje(texto)
    assert cambios == 1 and nuevo.startswith("a\n```c\nint *p = NULL;\n```") and "```\nx = 1\n```" in nuevo
    assert etiquetar_lenguaje(texto, por_defecto="c")[1] == 2
    xml = "<quiz><question><questiontext><text><![CDATA[```\nprintf(\"x\");\n```]]></text></questiontext></question></quiz>"
    assert "```c\nprintf" in etiquetar_lenguaje_archivo(xml, "xml")[0]


def test_etiquetar_lenguaje_no_toma_un_cierre_por_apertura():
    from questions.core.codigo import etiquetar_lenguaje

    # El cierre del primer bloque seguido de texto que termina en ':' (señal de Python) y
    # otro bloque: antes se etiquetaba el cierre como ```python y se rompían ambos.
    texto = "```c\nint a = 1;\n```\ny luego:\n```java\nint b = 2;\n```\n¿Qué cambia?"
    assert etiquetar_lenguaje(texto) == (texto, 0)
    assert etiquetar_lenguaje(texto, por_defecto="c") == (texto, 0)
    # Bloques pegados: sólo se etiqueta la apertura sin lenguaje.
    pegados = "```c\nint a;\n```\n```\nint main(){return 0;}\n```"
    assert etiquetar_lenguaje(pegados) == ("```c\nint a;\n```\n```c\nint main(){return 0;}\n```", 1)


def test_backticks_sin_cerrar():
    from questions.core.codigo import backticks_sin_cerrar

    assert not backticks_sin_cerrar("```c\nchar c = '`';\n```\n¿Qué guarda?")
    assert not backticks_sin_cerrar("```c\nint a;\n```\n```c\nint b;\n```")
    assert not backticks_sin_cerrar("Usá `x` y\n```c\nint a;\n```")
    assert backticks_sin_cerrar("```c\nint a;\n")
    assert backticks_sin_cerrar("```c\nint a;\n```\n```\nint b;\n")
    assert backticks_sin_cerrar("usa `x y listo")
