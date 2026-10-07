"""voight funciona sin myst-tools ni alucarD instalados (N-MOODLE-01, N-ECO-01).

Fuera del monorepo, `voight --help` fallaba al importar myst_tools a
nivel de módulo. Ahora LanguageTool llega con el extra `languagetool` y la
síntesis con alucarD es opcional: sin ellos el CLI arranca y el comando que los
necesita explica cómo instalarlos.
"""

from __future__ import annotations

import subprocess
import sys

BLOQUEAR = "import sys; sys.modules['myst_tools'] = None; sys.modules['myst_tools.languagetool_checker'] = None; "


def _correr(codigo: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", BLOQUEAR + codigo], capture_output=True, text=True, timeout=120)


def test_la_ayuda_funciona_sin_myst_tools():
    resultado = _correr("from voight.cli import cli; cli(['--help'])")
    assert resultado.returncode == 0, resultado.stderr
    assert "grammar" in resultado.stdout


def test_spellcheck_sin_myst_tools_explica_el_extra(tmp_path):
    banco = tmp_path / "banco.gift"
    banco.write_text("::p1:: ¿Cuánto es 2+2? {=4}\n", encoding="utf-8")
    resultado = _correr(f"from voight.cli import cli; cli(['grammar', {str(banco)!r}])")
    assert resultado.returncode == 1
    assert "extra languagetool" in resultado.stderr
    assert "Traceback" not in resultado.stderr
