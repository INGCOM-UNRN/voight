"""Configuración común de la suite."""

import pytest


@pytest.fixture(autouse=True)
def cache_aislada(tmp_path, monkeypatch):
    """Cada test usa su propia caché de respuestas de modelos (nunca ~/.cache del usuario)."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    # Ni `voight config` ni los tests tocan el ~/.voight/.env del usuario.
    monkeypatch.setenv("VOIGHT_CONFIG_DIR", str(tmp_path / "voight-config"))
    monkeypatch.delenv("VOIGHT_SIN_CACHE", raising=False)


@pytest.fixture(autouse=True)
def configuracion_limpia():
    """El .voight.toml se cachea por ruta: cada test empieza sin lo leído por otro."""
    from voight.core.configuracion import limpiar_cache

    limpiar_cache()
    yield
    limpiar_cache()


@pytest.fixture(autouse=True)
def entorno_restaurado():
    """La CLI carga ~/.voight/.env en os.environ al arrancar: cada test deja el entorno como estaba."""
    import os

    from voight.core import config

    antes = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(antes)
    config._CARGADAS.clear()
