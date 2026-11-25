"""Los bloques de diagramas (dibu y PlantUML) no son código: voight no les aplica la sangría con ·,
los ↵, el ancho completo ni los escapes de GIFT, y los conserva al parsear y al convertir."""
import pytest
from typer.testing import CliRunner

from voight.cli import app
from voight.core.codigo import diagnosticar_codigo, transformar_archivo
from voight.core.converter import gift_to_xml, xml_to_gift
from voight.core.formulas import LENGUAJES_DIAGRAMA, a_preprocesar
from voight.core.parser import parse_gift

DIBU = """type: call_stack
frames:
  - function: main
    vars: {a: 3}
  - function: duplicar
    params:
      x: 6
    returnTo: main
"""

PLANTUML = """class Lista {
  +x: int
}
A -> B : x = 1 #hola
"""

C = """int main(void)
{
    return 0;
}
"""


def banco(lenguaje: str) -> str:
    cuerpo = PLANTUML if lenguaje in ("plantuml", "puml") else DIBU
    return (f"::diagrama::[markdown]Mirá el diagrama\n```{lenguaje}\n{cuerpo}```\ny el código\n"
            f"```c\n{C}```\n{{\n    =a\n    ~b\n}}\n")


def bloque(texto: str, lenguaje: str) -> str:
    inicio = texto.index(f"```{lenguaje}\n") + len(lenguaje) + 4
    return texto[inicio:texto.index("```", inicio)]


def test_la_lista_de_diagramas():
    assert set(LENGUAJES_DIAGRAMA) == {"estructura", "statics", "dibu", "plantuml", "puml"}


@pytest.mark.parametrize("lenguaje", LENGUAJES_DIAGRAMA)
def test_code_indent_y_code_chars_no_tocan_los_diagramas(lenguaje):
    original = banco(lenguaje)
    marcado, _ = transformar_archivo(original, "gift", fullwidth=None, espacios=True, saltos=True)
    ancho, _ = transformar_archivo(marcado, "gift", fullwidth=True, espacios=True, saltos=True)
    assert bloque(ancho, lenguaje) == bloque(original, lenguaje)
    # El código C del mismo banco sí se transforma.
    assert "····return" in bloque(ancho, "c")


@pytest.mark.parametrize("lenguaje", LENGUAJES_DIAGRAMA)
def test_los_comandos_de_voight_no_tocan_los_diagramas(tmp_path, lenguaje):
    archivo = tmp_path / "a.gift"
    archivo.write_text(banco(lenguaje), encoding="utf-8")
    for paso in (["code-indent"], ["code-chars", "--to-fullwidth"], ["format"]):
        resultado = CliRunner().invoke(app, ["fix", *paso, str(archivo)])
        assert resultado.exit_code == 0, resultado.output
    final = archivo.read_text(encoding="utf-8")
    assert bloque(final, lenguaje) == bloque(banco(lenguaje), lenguaje)
    assert "····return" in bloque(final, "c")


@pytest.mark.parametrize("lenguaje", LENGUAJES_DIAGRAMA)
def test_los_diagramas_quedan_crudos_al_parsear_y_convertir(lenguaje):
    original = banco(lenguaje)
    preguntas = parse_gift(original)["questions"]
    assert len(preguntas) == 1
    cuerpo = bloque(original, lenguaje)
    assert cuerpo in xml_to_gift(gift_to_xml(original))


@pytest.mark.parametrize("lenguaje", LENGUAJES_DIAGRAMA)
def test_la_auditoria_no_toma_los_diagramas_por_codigo(lenguaje):
    texto = f"::a::[markdown]x\n```{lenguaje}\n{DIBU}```\n{{=a ~b}}\n"
    assert diagnosticar_codigo(texto, "gift")["secciones"] == 0
    assert a_preprocesar(texto)["diagramas"] == 1
