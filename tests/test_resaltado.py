"""Ola 14 (QoL #628): resaltado de C en HTML con CSS en línea para Moodle, sin scripts en el navegador."""

from pathlib import Path

from typer.testing import CliRunner

from voight.cli import app
from voight.core.moodle_health import auditar_texto, limpiar_html_archivo
from voight.core.resaltado import resaltar_c, resaltar_texto

XML = """<?xml version="1.0" encoding="UTF-8"?>
<quiz>
  <question type="multichoice">
    <name><text>suma</text></name>
    <questiontext format="markdown">
      <text><![CDATA[¿Qué imprime?

```c
int a = 3; // tres
printf("%d\\n", a < 4);
```
]]></text>
    </questiontext>
    <answer fraction="100" format="markdown"><text>1</text></answer>
    <answer fraction="0" format="markdown"><text>0</text></answer>
  </question>
</quiz>
"""


def test_tokens_con_estilo_en_linea_y_html_escapado():
    salida = resaltar_c('#include <stdio.h>\nint main(void) { char *s = "a<b"; return 0x1F; } // fin\n')
    assert salida.startswith('<pre class="voight-resaltado" style="background:#f6f8fa;')
    assert '<span style="color:#d73a49">#include &lt;stdio.h&gt;</span>' in salida
    assert '<span style="color:#005cc5">int</span> <span style="color:#6f42c1">main</span>' in salida
    assert '<span style="color:#032f62">"a&lt;b"</span>' in salida
    assert '<span style="color:#d73a49;font-weight:bold">return</span>' in salida
    assert '<span style="color:#6a737d;font-style:italic">// fin</span>' in salida
    assert "<script" not in salida and "class=\"hljs" not in salida


def test_solo_los_bloques_c_y_el_resto_del_texto_igual():
    texto = "Mirá:\n\n```c\nint x;\n```\n\nY este no:\n\n```java\nint y;\n```\n"
    nuevo, cambios = resaltar_texto(texto)
    assert cambios == 1
    assert nuevo.startswith("Mirá:\n\n<pre ") and "```java\nint y;\n```" in nuevo


def test_codigo_protegido_fullwidth_vuelve_a_ascii():
    nuevo, cambios = resaltar_texto("```c\nint·x·＝·1；↵\n```\n")
    assert cambios == 1 and '<span style="color:#005cc5">int</span> x = <span style="color:#005cc5">1</span>;' in nuevo


def test_el_resaltado_no_cuenta_como_html_obsoleto_ni_se_limpia(tmp_path: Path):
    banco = tmp_path / "suma.xml"
    banco.write_text(XML, encoding="utf-8")
    res = CliRunner().invoke(app, ["fix", "highlight", str(banco)])
    assert res.exit_code == 0, res.output
    resaltado = banco.read_text(encoding="utf-8")
    assert "voight-resaltado" in resaltado and 'format="markdown"' in resaltado
    assert auditar_texto(resaltado, "xml")["html_obsoleto"] == 0
    assert limpiar_html_archivo(resaltado, "xml") == resaltado
    # Y sigue siendo un Moodle XML que voight lee.
    assert CliRunner().invoke(app, ["health", str(banco)]).exit_code == 0


def test_gift_se_omite_con_aviso(tmp_path: Path):
    banco = tmp_path / "b.gift"
    banco.write_text("::p:: ¿Qué?\n```c\nint x;\n```\n{=1 ~2}\n", encoding="utf-8")
    res = CliRunner().invoke(app, ["fix", "highlight", str(banco)])
    assert res.exit_code == 0 and "gift-to-xml" in res.output
    assert "<pre" not in banco.read_text(encoding="utf-8")
