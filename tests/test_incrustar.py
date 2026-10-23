"""Diagramas mermaid e imágenes relativas incrustados al fusionar Moodle XML."""

import base64
import shutil
import stat
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from click.testing import CliRunner

from voight.cli import cli
from voight.core.incrustar import ErrorIncrustacion
from voight.core.unifier import unificar

runner = CliRunner()

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

PREGUNTA = """<?xml version="1.0" encoding="UTF-8"?>
<quiz>
  <question type="truefalse">
    <name><text>Flujo</text></name>
    <questiontext format="markdown"><text><![CDATA[Mirá:

```mermaid
graph TD
··A －－＞ B↵
```

y ![una foto](img/foto.png) ![remota](https://ejemplo.org/x.png)]]></text></questiontext>
    <generalfeedback format="html"><text><![CDATA[<p><img src="img/foto.png"></p><pre class="mermaid">graph LR
X --&gt; Y</pre>]]></text></generalfeedback>
    <answer fraction="100"><text>true</text></answer>
    <answer fraction="0"><text>false</text></answer>
  </question>
</quiz>
"""


@pytest.fixture
def mmdc_falso(tmp_path, monkeypatch):
    """Un `mmdc` que copia el código del diagrama a la salida (para ver qué recibió)."""
    script = tmp_path / "mmdc"
    script.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "a = sys.argv\n"
        "codigo = open(a[a.index('-i') + 1], encoding='utf-8').read()\n"
        "if 'ROTO' in codigo:\n"
        "    sys.exit('Error: Lexical error on line 1')\n"
        "open(a[a.index('-o') + 1], 'w', encoding='utf-8').write(codigo)\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("VOIGHT_MMDC", str(script))
    return script


def _arbol(tmp_path: Path, contenido: str = PREGUNTA) -> Path:
    arbol = tmp_path / "arbol"
    (arbol / "Tema" / "img").mkdir(parents=True)
    (arbol / "Tema" / "img" / "foto.png").write_bytes(PNG)
    (arbol / "Tema" / "q1.xml").write_text(contenido, encoding="utf-8")
    return arbol


def _campo(salida: Path, tag: str) -> ET.Element:
    campo = ET.parse(salida).getroot().find(f"question/{tag}")
    assert campo is not None
    return campo


def _archivos(campo: ET.Element) -> dict:
    return {f.get("name"): base64.b64decode(f.text) for f in campo.findall("file")}


def test_unify_incrusta_diagramas_e_imagenes_sin_tocar_la_fuente(tmp_path, mmdc_falso):
    arbol = _arbol(tmp_path)
    salida = tmp_path / "banco.xml"

    assert unificar([arbol], salida) == 1

    assert (arbol / "Tema" / "q1.xml").read_text(encoding="utf-8") == PREGUNTA

    enunciado = _campo(salida, "questiontext")
    texto = enunciado.findtext("text")
    assert "```mermaid" not in texto
    assert "![una foto](@@PLUGINFILE@@/foto.png)" in texto
    assert "https://ejemplo.org/x.png" in texto  # las absolutas no se tocan
    archivos = _archivos(enunciado)
    assert archivos["foto.png"] == PNG
    (diagrama,) = [n for n in archivos if n.startswith("mermaid-")]
    assert f"![diagrama](@@PLUGINFILE@@/{diagrama})" in texto
    # mmdc recibe el código en ASCII, sin fullwidth ni marcas.
    assert archivos[diagrama].decode() == "graph TD\n  A --> B\n"

    retro = _campo(salida, "generalfeedback")
    texto = retro.findtext("text")
    assert '<img src="@@PLUGINFILE@@/foto.png">' in texto
    assert 'class="mermaid"' not in texto
    (diagrama,) = [n for n in _archivos(retro) if n.startswith("mermaid-")]
    assert _archivos(retro)[diagrama].decode() == "graph LR\nX --> Y\n"


def test_tree_collect_incrusta_y_no_incrustar_lo_deja_como_texto(tmp_path, mmdc_falso):
    arbol = _arbol(tmp_path)
    salida = tmp_path / "banco.xml"

    r = runner.invoke(cli, ["tree", "collect", str(arbol), "-o", str(salida), "--diagramas", "svg"])
    assert r.exit_code == 0, r.output
    nombres = _archivos(_campo(salida, "questiontext"))
    assert any(n.startswith("mermaid-") and n.endswith(".svg") for n in nombres)

    r = runner.invoke(cli, ["tree", "collect", str(arbol), "-o", str(salida), "--no-incrustar"])
    assert r.exit_code == 0, r.output
    enunciado = _campo(salida, "questiontext")
    assert "```mermaid" in enunciado.findtext("text")
    assert enunciado.find("file") is None


def test_imagenes_con_el_mismo_nombre_no_se_pisan(tmp_path, mmdc_falso):
    arbol = tmp_path / "arbol"
    (arbol / "a").mkdir(parents=True)
    (arbol / "b").mkdir()
    (arbol / "a" / "x.png").write_bytes(PNG)
    (arbol / "b" / "x.png").write_bytes(PNG + b"otra")
    (arbol / "q.xml").write_text(
        '<quiz><question type="essay"><name><text>Q</text></name>'
        '<questiontext format="markdown"><text>![](a/x.png) ![](b/x.png)</text></questiontext>'
        "</question></quiz>",
        encoding="utf-8",
    )
    salida = tmp_path / "banco.xml"
    unificar([arbol], salida)

    archivos = _archivos(_campo(salida, "questiontext"))
    assert len(archivos) == 2
    assert archivos["x.png"] == PNG


def test_imagen_inexistente_o_diagrama_roto_es_error(tmp_path, mmdc_falso):
    arbol = _arbol(tmp_path, PREGUNTA.replace("img/foto.png)", "img/no-esta.png)"))
    with pytest.raises(ErrorIncrustacion, match="no-esta.png"):
        unificar([arbol], tmp_path / "banco.xml")

    arbol = _arbol(tmp_path / "otro", PREGUNTA.replace("graph TD", "ROTO"))
    r = runner.invoke(cli, ["unify", str(arbol), "-o", str(tmp_path / "banco.xml")])
    assert r.exit_code != 0
    assert "Lexical error" in r.output


def test_sin_mmdc_avisa_como_instalarlo(tmp_path, monkeypatch):
    monkeypatch.delenv("VOIGHT_MMDC", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _: None)
    with pytest.raises(ErrorIncrustacion, match="mermaid-cli"):
        unificar([_arbol(tmp_path)], tmp_path / "banco.xml")


def test_el_render_se_guarda_en_cache(tmp_path, mmdc_falso):
    arbol = _arbol(tmp_path)
    unificar([arbol], tmp_path / "uno.xml")
    mmdc_falso.unlink()  # sin mmdc, el segundo render sale de la caché
    unificar([arbol], tmp_path / "dos.xml")
    assert (tmp_path / "uno.xml").read_text() == (tmp_path / "dos.xml").read_text()


@pytest.mark.skipif(not shutil.which("mmdc"), reason="requiere mermaid-cli (mmdc)")
def test_render_real_con_mmdc(tmp_path, monkeypatch):
    monkeypatch.delenv("VOIGHT_MMDC", raising=False)
    salida = tmp_path / "banco.xml"
    unificar([_arbol(tmp_path)], salida)
    archivos = _archivos(_campo(salida, "questiontext"))
    (diagrama,) = [n for n in archivos if n.startswith("mermaid-")]
    assert archivos[diagrama].startswith(b"\x89PNG")
