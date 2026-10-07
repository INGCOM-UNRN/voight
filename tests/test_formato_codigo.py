"""`fix code-format`: clang-format conservando la convención de cada archivo."""

import shutil

import pytest

from voight.core.formato_codigo import comando_clang_format, formatear_archivo, formatear_texto

COMANDO = comando_clang_format()
pytestmark = pytest.mark.skipif(COMANDO is None, reason="requiere clang-format o uvx")


def test_formatea_c_protegido_y_conserva_las_marcas():
    gift = "::P::[markdown]Ver\n```c\nint main（）｛int x＝1；if（x）｛return x；｝↵\n｝\n```\n{=a ~b}"
    nuevo, cambios = formatear_texto(gift, "gift", COMANDO)
    assert cambios == 1
    assert "int main（） ｛↵\n····int x ＝ 1；↵\n····if （x） ｛↵\n········return x；↵\n····｝↵\n｝↵\n```" in nuevo


def test_formatea_java_en_xml_sin_proteger():
    xml = ("<quiz><question><questiontext><text><![CDATA[```java\npublic class A{public static void main(String[] a)"
           "{System.out.println(1);}}\n```]]></text></questiontext></question></quiz>")
    nuevo, cambios = formatear_archivo(xml, "xml", COMANDO)
    assert cambios == 1
    assert "public class A {\n    public static void main(String[] a) {\n        System.out.println(1);\n    }\n}" in nuevo


def test_gift_sin_proteger_se_escapa_y_lo_que_no_es_c_queda_igual():
    gift = "::P:: Ver\n```c\nint f(){return 1;}\n```\n```\nx = 1\n```\n{=a ~b}"
    nuevo, cambios = formatear_texto(gift, "gift", COMANDO)
    assert cambios == 1
    assert "```c\nint f() \\{\n    return 1;\n\\}\n```" in nuevo  # formateado y con las llaves escapadas
    assert "```\nx = 1\n```" in nuevo


@pytest.mark.skipif(shutil.which("gaff") is None, reason="gaff no está instalado")
def test_format_gaff_formatea_y_vuelve_a_proteger(tmp_path):
    from click.testing import CliRunner

    from voight.cli import cli

    banco = tmp_path / "a.gift"
    banco.write_text("::P:: ¿Qué imprime?\n```c\nint x=3;\nif(x>2){x++;}\n```\n{=3 ~2}\n", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(cli, ["fix", "format", "--fullwidth", str(banco)]).exit_code == 0
    res = runner.invoke(cli, ["fix", "format", "--gaff", str(banco)])
    assert res.exit_code == 0, res.output
    texto = banco.read_text(encoding="utf-8")
    assert "if （x ＞ 2）↵\n｛↵\n····x++；↵\n｝↵\n```" in texto
    assert runner.invoke(cli, ["fix", "format", "--gaff", "--check", str(banco)]).exit_code == 0
