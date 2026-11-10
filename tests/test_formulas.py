"""Fórmulas en GIFT y Moodle XML: se leen sin romperse, se avisan en GIFT y se incrustan al fusionar."""

import base64
import xml.etree.ElementTree as ET

import pytest
from click.testing import CliRunner

from voight.cli import cli
from voight.core.converter import gift_to_xml
from voight.core.formulas import a_preprocesar, avisos_gift
from voight.core.hallazgos import elementos
from voight.core.incrustar import ErrorIncrustacion
from voight.core.moodle_health import auditar_archivos
from voight.core.parser import parse_gift
from voight.core.unifier import unificar

runner = CliRunner()

GIFT = r"""$CATEGORY: $course$/mate

::suma:: [markdown]¿Cuánto vale $\sum_{i=1}^{4} i$ si $n \neq 0$?
{
    =`10`
    ~$\frac{1}{2}$
}

::matriz:: [markdown]Sea $$A = \begin{pmatrix} 1 & 2 \\ 3 & 4 \end{pmatrix}$$ {T}
"""

TABLA = "::t::[markdown]Mirá\n```tabla\n// [centrado]\n| a | b |\n|---|---|\n| `x` | $|y|$ |\n```\n{}\n"
DIAGRAMA = "::d::[markdown]Mirá\n```estructura\ntype: stack\nvalues: [1]\n```\n{T}\n"


def _xml(pregunta: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<quiz>{pregunta}</quiz>\n'


def _multichoice(enunciado: str, formato: str = "html", opcion: str = "uno") -> str:
    return (f'<question type="multichoice"><name><text>q</text></name>'
            f'<questiontext format="{formato}"><text><![CDATA[{enunciado}]]></text></questiontext>'
            f'<answer fraction="100" format="html"><text><![CDATA[{opcion}]]></text></answer></question>')


class MotorFalso:
    def __init__(self):
        self.dibujadas = []

    def a_svg(self, fuente, bloque=False):
        if "ROTA" in fuente:
            raise ValueError("comando desconocido")
        self.dibujadas.append((fuente, bloque))
        return f"<svg>{fuente}</svg>"


@pytest.fixture
def motor(monkeypatch):
    monkeypatch.setenv("VOIGHT_SIN_CACHE", "1")
    falso = MotorFalso()
    monkeypatch.setattr("voight.core.incrustar.motor_formulas", lambda: falso)
    return falso


def _fusionar(tmp_path, xml):
    fuente = tmp_path / "fuente"
    fuente.mkdir(exist_ok=True)
    (fuente / "q.xml").write_text(xml, encoding="utf-8")
    salida = tmp_path / "salida.xml"
    assert unificar([fuente], salida) == 1
    return ET.parse(salida).getroot().find("question")


def test_el_parser_no_corta_una_pregunta_en_las_llaves_de_una_formula():
    preguntas = [q for q in parse_gift(GIFT)["questions"] if q["type"] != "Category"]
    assert [q["type"] for q in preguntas] == ["MC", "TF"]
    assert r"$\sum_{i=1}^{4} i$" in preguntas[0]["stem"]["text"]
    assert r"$n \neq 0$" in preguntas[0]["stem"]["text"]
    assert r"\\ 3 & 4" in preguntas[1]["stem"]["text"]
    assert [c["text"]["text"] for c in preguntas[0]["choices"]] == ["`10`", r"$\frac{1}{2}$"]


def test_gift_to_xml_conserva_las_formulas():
    xml = gift_to_xml(GIFT)
    assert r"$\sum_{i=1}^{4} i$" in xml and r"$\frac{1}{2}$" in xml and "0" not in xml


def test_el_igual_escapado_de_una_opcion_es_un_igual():
    pregunta = parse_gift("::a::Elegí {\n=$x \\= 1$\n~$y$\n}\n")["questions"][0]
    assert pregunta["choices"][0]["text"]["text"] == "$x = 1$"


@pytest.mark.parametrize("texto", ["cuesta $100 y $200", "`$a$`", "```\n$a$\n```", "\\$5", "// $a$",
                                   "$CATEGORY: $course$/top"])
def test_lo_que_no_es_una_formula(texto):
    assert a_preprocesar(texto) == {"diagramas": 0, "tablas": 0, "formulas": 0}


def test_cuenta_diagramas_y_formulas():
    assert a_preprocesar(GIFT + "\n" + DIAGRAMA + "\n" + TABLA) == {"diagramas": 1, "tablas": 1, "formulas": 4}
    assert a_preprocesar("::a::\n```mermaid\ngraph TD\n```\n{T}\n")["diagramas"] == 1


def test_avisa_los_gift_que_moodle_no_dibuja(tmp_path):
    con, sin = tmp_path / "con.gift", tmp_path / "sin.gift"
    con.write_text(DIAGRAMA, encoding="utf-8")
    sin.write_text("::a::Texto {T}\n", encoding="utf-8")
    (aviso,) = avisos_gift([con, sin])
    assert aviso.startswith(f"Advertencia: {con} tiene 1 diagramas, 0 tablas y 0 fórmulas")


def test_health_lo_informa_como_advertencia_solo_en_gift(tmp_path):
    gift, xml = tmp_path / "a.gift", tmp_path / "b.xml"
    gift.write_text(GIFT, encoding="utf-8")
    xml.write_text(_xml(_multichoice("$x$")), encoding="utf-8")
    resultado = auditar_archivos([gift, xml])
    claves = {a["clave"]: a["cantidad"] for a in resultado["resumen"]["advertencias"]}
    assert claves["gift_a_preprocesar"] == 1
    assert [e["archivo"] for e in elementos(resultado, "gift_a_preprocesar")] == [str(gift)]


def test_unify_a_gift_advierte_por_stderr(tmp_path):
    (tmp_path / "a.gift").write_text(GIFT, encoding="utf-8")
    r = runner.invoke(cli, ["unify", str(tmp_path / "a.gift"), "-o", str(tmp_path / "s.gift")])
    assert r.exit_code == 0 and "Advertencia" in r.stderr


def test_al_fusionar_una_formula_queda_como_imagen_en_el_renglon(tmp_path, motor):
    q = _fusionar(tmp_path, _xml(_multichoice(r"<p>Sea $\frac{a}{b}$ y \(x &lt; y\).</p>$$z$$")))
    campo = q.find("questiontext")
    texto = campo.find("text").text
    assert "$" not in texto and r"\(" not in texto
    assert 'alt="\\frac{a}{b}" style="vertical-align:middle"' in texto
    assert 'alt="z" style="display:block;margin:0.5em auto"' in texto
    assert motor.dibujadas == [(r"\frac{a}{b}", False), ("x < y", False), ("z", True)]
    archivos = campo.findall("file")
    assert len(archivos) == 3 and all(f.get("name").startswith("formula-") for f in archivos)
    assert base64.b64decode(archivos[0].text) == rb"<svg>\frac{a}{b}</svg>"
    assert f'@@PLUGINFILE@@/{archivos[0].get("name")}' in texto


def test_en_markdown_tambien_y_el_codigo_no_se_toca(tmp_path, motor):
    q = _fusionar(tmp_path, _xml(_multichoice("Sea $a_1$ y `$b$`\n\n```c\n$c$\n```", "markdown")))
    texto = q.find("questiontext/text").text
    assert '<img src="@@PLUGINFILE@@/formula-' in texto and "`$b$`" in texto and "$c$" in texto
    assert motor.dibujadas == [("a_1", False)]


def test_las_opciones_de_multichoice_tambien(tmp_path, motor):
    q = _fusionar(tmp_path, _xml(_multichoice("Elegí", opcion="$x$")))
    assert "<img" in q.find("answer/text").text and q.find("answer/file") is not None


def test_una_respuesta_corta_sigue_siendo_texto(tmp_path, motor):
    q = _fusionar(tmp_path, _xml('<question type="shortanswer"><name><text>q</text></name>'
                                 '<questiontext format="html"><text>Elegí</text></questiontext>'
                                 '<answer fraction="100" format="html"><text>$x$</text></answer></question>'))
    assert q.find("answer/text").text == "$x$"


def test_el_signo_pesos_escapado_no_es_formula(tmp_path, motor):
    q = _fusionar(tmp_path, _xml(_multichoice(r"Cuesta \$5 y $100 o $200")))
    assert q.find("questiontext/text").text == "Cuesta &#36;5 y $100 o $200" and not motor.dibujadas


def test_fusionar_dos_veces_no_vuelve_a_dibujar(tmp_path, motor):
    q = _fusionar(tmp_path, _xml(_multichoice("Sea $x$")))
    primera = q.find("questiontext/text").text
    (tmp_path / "fuente" / "q.xml").unlink()
    (tmp_path / "fuente" / "q.xml").write_bytes(ET.tostring(ET.Element("quiz")))
    raiz = ET.Element("quiz")
    raiz.append(q)
    q2 = _fusionar(tmp_path, ET.tostring(raiz, encoding="unicode"))
    assert q2.find("questiontext/text").text == primera and len(motor.dibujadas) == 1


def test_una_formula_rota_corta_la_fusion_con_su_pregunta(tmp_path, motor):
    with pytest.raises(ErrorIncrustacion, match=r"q <questiontext>: fórmula inválida «ROTA»"):
        _fusionar(tmp_path, _xml(_multichoice("Sea $ROTA$")))


def test_sin_alucard_avisa_como_instalarlo(tmp_path, monkeypatch):
    monkeypatch.setenv("VOIGHT_SIN_CACHE", "1")
    monkeypatch.setattr("voight.core.incrustar.motor_formulas", lambda: None)
    with pytest.raises(ErrorIncrustacion, match="alucarD"):
        _fusionar(tmp_path, _xml(_multichoice("Sea $x$")))


def test_sin_incrustar_quedan_como_texto(tmp_path, motor):
    fuente = tmp_path / "q.xml"
    fuente.write_text(_xml(_multichoice("Sea $x$")), encoding="utf-8")
    salida = tmp_path / "s.xml"
    unificar([fuente], salida, incrustar=False)
    assert "$x$" in salida.read_text(encoding="utf-8") and not motor.dibujadas


def test_con_alucard_dibuja_la_formula_de_verdad(tmp_path, monkeypatch):
    pytest.importorskip("generador_examenes.matematica")
    monkeypatch.setenv("VOIGHT_SIN_CACHE", "1")
    q = _fusionar(tmp_path, _xml(_multichoice(r"Sea $\sum_{i=1}^{n} i$")))
    assert b"<svg" in base64.b64decode(q.find("questiontext/file").text)


class TablasFalsas:
    def __call__(self, cuerpo):
        if "ROTA" in cuerpo:
            raise ValueError("opción desconocida")
        return "<table>" + cuerpo.strip().replace("\n", " ") + "</table>"


@pytest.fixture
def tablas(monkeypatch):
    monkeypatch.setattr("voight.core.incrustar.motor_tablas", lambda: TablasFalsas())


def test_al_fusionar_una_tabla_pasa_a_html(tmp_path, motor, tablas):
    q = _fusionar(tmp_path, _xml(_multichoice("Mirá\n```tabla\n| a |\n|---|\n```\nFin", "markdown")))
    texto = q.find("questiontext/text").text
    assert "```" not in texto and "Mirá\n\n\n<table>| a | |---|</table>\n\n\nFin" == texto


def test_la_formula_de_una_celda_es_una_imagen(tmp_path, motor, tablas):
    q = _fusionar(tmp_path, _xml(_multichoice("```tabla\n| $|x|$ |\n|---|\n```", "markdown")))
    texto = q.find("questiontext/text").text
    assert 'alt="|x|"' in texto and "VOIGHTFORMULA" not in texto and q.find("questiontext/file") is not None


def test_una_tabla_invalida_corta_la_fusion(tmp_path, motor, tablas):
    with pytest.raises(ErrorIncrustacion, match="tabla inválida: opción desconocida"):
        _fusionar(tmp_path, _xml(_multichoice("```tabla\n// [ROTA]\n| a |\n```", "markdown")))


def test_sin_alucard_una_tabla_avisa_como_instalarlo(tmp_path, monkeypatch):
    monkeypatch.setattr("voight.core.incrustar.motor_tablas", lambda: None)
    with pytest.raises(ErrorIncrustacion, match="alucarD"):
        _fusionar(tmp_path, _xml(_multichoice("```tabla\n| a |\n```", "markdown")))


def test_con_alucard_la_tabla_es_html_de_verdad(tmp_path, monkeypatch):
    pytest.importorskip("generador_examenes.tablas")
    monkeypatch.setenv("VOIGHT_SIN_CACHE", "1")
    q = _fusionar(tmp_path, _xml(_multichoice(
        "```tabla\n// [centrado]\n| a | b |\n|---|---|\n| `x` | $|y|$ |\n```", "markdown")))
    texto = q.find("questiontext/text").text
    assert "<table" in texto and "<code>x</code>" in texto and 'alt="|y|"' in texto and "centrado" not in texto
