"""Regresión de MOODLE-D0501: `tatsu` era una dependencia declarada, compilada en cada
`GiftParser()` y verificada por el doctor como "requerida", pero su único camino de parseo
(`_parse_raw`) no se llamaba desde ningún lado: todo usa el parser manual."""

import subprocess
import sys
import textwrap
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def test_el_paquete_no_importa_tatsu():
    codigo = textwrap.dedent(
        """
        import sys
        sys.modules["tatsu"] = None  # cualquier `import tatsu` falla
        import voight.core.parser as p
        from voight.core.parser import GiftParser
        GiftParser()._manual_parse("::t:: 2+2? {=4 ~5}")
        """
    )
    res = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr


def test_tatsu_ya_no_esta_declarado_como_dependencia():
    texto = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
    assert "tatsu" not in texto.lower()


def test_ninguna_fuente_del_paquete_menciona_tatsu():
    for archivo in (RAIZ / "src").rglob("*.py"):
        assert "tatsu" not in archivo.read_text(encoding="utf-8").lower(), archivo


def test_el_parser_se_instancia_sin_compilar_una_gramatica():
    from voight.core.parser import GiftParser

    parser = GiftParser()
    assert not hasattr(parser, "_parser")


def test_el_doctor_informa_los_requisitos_reales_de_synth_y_ai():
    """MOODLE-D0802: el README decía 'ninguno obligatorio' y el doctor no sondeaba gcc, el
    motor de síntesis ni la API key; en cambio verificaba tatsu, que nadie usaba."""
    import json
    from click.testing import CliRunner
    from voight.cli import cli

    res = CliRunner().invoke(cli, ["doctor", "--json"])
    componentes = {c["componente"] for c in json.loads(res.output)["componentes"]}
    assert any("GCC" in c for c in componentes)
    assert any("alucarD" in c for c in componentes)
    assert any("ia: " in c and "(comando ai)" in c for c in componentes)  # proveedor de IA (N-ECO-26)
    assert not any("TatSu" in c for c in componentes)


def test_el_readme_declara_donde_vive_la_sintesis_y_sus_requisitos():
    texto = (RAIZ / "README.md").read_text(encoding="utf-8")
    assert "delegado a `idkfa`" not in texto
    assert "alucarD" in texto and "gcc" in texto and "GEMINI_API_KEY" in texto
    assert "Ninguno obligatorio" not in texto
