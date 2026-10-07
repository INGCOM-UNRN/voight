"""google-genai debe ser opcional (N-MOODLE-02).

Como dependencia obligatoria arrastraba a toda instalación cryptography,
urllib3, pyasn1, idna y anyio, con avisos de seguridad conocidos, aunque solo
`voight ai` la usa.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_google_genai_esta_en_el_extra_ai_y_no_en_las_dependencias_base():
    proyecto = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    assert not any(d.startswith("google-genai") for d in proyecto["dependencies"])
    assert any(d.startswith("google-genai") for d in proyecto["optional-dependencies"]["ai"])


def test_el_modulo_ai_se_importa_aunque_falte_google_genai(monkeypatch):
    import importlib.util
    import sys

    import voight.core.ai as original

    # Una copia aislada del módulo: recargar el real dejaría clases viejas (Unidad…) en
    # los módulos que ya lo importaron y rompería los tests que corren después.
    monkeypatch.setitem(sys.modules, "google", None)
    spec = importlib.util.spec_from_file_location("ai_sin_google_genai", original.__file__)
    modulo = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, modulo)  # @dataclass busca el módulo en sys.modules
    spec.loader.exec_module(modulo)
    assert modulo.genai is None
    assert original.genai is not None or "google" not in sys.modules
