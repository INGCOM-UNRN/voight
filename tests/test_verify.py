"""`voight verify`: compilar y ejecutar el código de las preguntas (requiere gcc / javac)."""

import json
import shutil

import pytest
from click.testing import CliRunner

from voight.cli import cli
from voight.core.verificar import candidatos, comparar, extraer_codigo, normalizar, preparar_c, preparar_java, verificar
from voight.core.gift_model import Choice, FormattedText

runner = CliRunner()
con_gcc = pytest.mark.skipif(not shutil.which("gcc"), reason="requiere gcc")
con_javac = pytest.mark.skipif(not (shutil.which("javac") and shutil.which("java")), reason="requiere javac")


def _q(gift):
    from voight.core.parser import GiftParser
    return GiftParser()._manual_parse(gift)[0]


def _opciones(*pares):
    return [Choice(is_correct=c, text=FormattedText(text=t)) for c, t in pares]


def test_extraer_y_preparar_codigo_protegido():
    q = _q("::P::[markdown]¿Qué imprime?\n```c\nint x ＝ 5；↵\n····printf（＂%d＂, x）；\n```\n{=5 ~0}")
    lenguaje, codigo = extraer_codigo(q)
    assert lenguaje == "c" and codigo == 'int x = 5;\n    printf("%d", x);\n'
    fuente = preparar_c(codigo)
    assert "#include <stdio.h>" in fuente and "int main(void) {" in fuente
    assert preparar_java('System.out.println("a");')[0] == "Main"
    assert preparar_java("public class Hola { public static void main(String[] a) {} }")[0] == "Hola"


def test_comparar_por_niveles():
    opciones = _opciones((True, "1 95.5\\n2 88.0"), (False, "1 95.5 2 88.0"))
    assert comparar("1 95.5\n2 88.0\n", opciones)[0] == "coincide"
    assert comparar("1 95.5 2 88.0\n", opciones)[0] == "coincide_distractor"
    assert comparar('ThreeFour', _opciones((True, 'Imprimirá "ThreeFour"'), (False, 'Imprimirá "Three"')))[0] == "coincide"
    assert comparar("Hace calor\nFin", _opciones((True, "Hace calor y Fin (en líneas separadas)"), (False, "Solo Fin")))[0] == "coincide"
    assert comparar("ABC\nD", _opciones((True, "ABC y D en líneas distintas por println"), (False, "ABC D")))[0] == "revisar"
    assert candidatos("1 4 2 5 3 6 (La transpuesta)")[-1] == "1 4 2 5 3 6"
    assert normalizar("`a`↵b") == "a b"


@con_gcc
def test_verificar_c_clave_correcta_distractor_y_ub():
    ok = _q("::P::[markdown]¿Qué imprime?\n```c\nint x = 2 + 3;\nprintf(\"%d\", x);\n```\n{=5 ~6 ~Error de compilación}")
    assert verificar(ok).estado == "coincide"
    mal = _q("::P::[markdown]¿Qué imprime?\n```c\nprintf(\"%d\", 7 / 2);\n```\n{=3.5 ~3 ~4}")
    r = verificar(mal)
    assert r.estado == "coincide_distractor" and r.coincide_con == "3"
    no_compila = _q("::P::[markdown]¿Qué imprime?\n```c\nint x = ;\n```\n{=Error de compilación ~0}")
    assert verificar(no_compila).estado == "coincide"
    ub = _q("::P::[markdown]¿Qué imprime?\n```c\nint *p = 0;\nprintf(\"%d\", *p);\n```\n{=Comportamiento indefinido ~0}")
    assert verificar(ub).estado == "coincide"
    conceptual = _q("::P:: ¿Qué hace esta línea?\n```c\nint x = 1;\n```\n{=Declara e inicializa x ~Nada}")
    assert verificar(conceptual) is None


@con_javac
def test_verificar_java():
    q = _q('::P::[markdown]¿Qué imprime?\n```java\nfor (int i ＝ 0； i ＜ 3； i++) System.out.print(i)；\n```\n{=012 ~123 ~0123}')
    assert verificar(q).estado == "coincide"


@con_gcc
def test_cli_verify_json_y_codigo_de_salida(tmp_path):
    (tmp_path / "ok.gift").write_text("::A::[markdown]¿Qué imprime?\n```c\nprintf(\"hola\");\n```\n{=hola ~chau}\n", encoding="utf-8")
    res = runner.invoke(cli, ["verify", str(tmp_path), "--json"])
    assert res.exit_code == 0, res.output
    assert json.loads(res.output)["por_estado"] == {"coincide": 1}
    (tmp_path / "mal.gift").write_text("::B::[markdown]¿Qué imprime?\n```c\nprintf(\"%d\", 7 / 2);\n```\n{=3.5 ~3}\n", encoding="utf-8")
    res = runner.invoke(cli, ["verify", str(tmp_path), "--solo-problemas"])
    assert res.exit_code == 1 and "distractor" in res.output and "mal.gift" in res.output and "ok.gift" not in res.output


def test_estilo_con_un_verificador(tmp_path):
    from voight.core.verificar import revisar_estilo

    class Observacion:
        def __init__(self, codigo, linea):
            self.rule_code, self.line, self.severity, self.title = codigo, linea, "ESTILO", "t"

    class Verificador:
        def analyze(self, codigo, nombre):
            assert "int a, b;" in codigo and nombre.endswith(".c")
            return [Observacion("0x0002h", 1)]

    q = _q("::P::[markdown]¿Qué hace?\n```c\nint a, b;\n```\n{=a ~b}")
    assert revisar_estilo(q, Verificador()) == [{"regla": "0x0002h", "linea": 1, "severidad": "ESTILO", "titulo": "t"}]
    assert revisar_estilo(_q("::J:: ¿Qué?\n```java\nint a;\n```\n{=a ~b}"), Verificador()) is None


def test_cli_estilo_sin_ripley_explica_como_instalarlo(tmp_path, monkeypatch):
    import voight.core.verificar as verificar_mod

    monkeypatch.setattr(verificar_mod, "verificador_de_estilo", lambda: None)
    (tmp_path / "a.gift").write_text("::A:: q {=a ~b}\n", encoding="utf-8")
    res = runner.invoke(cli, ["verify", str(tmp_path), "--estilo"])
    assert res.exit_code == 1 and "ripley" in res.output
