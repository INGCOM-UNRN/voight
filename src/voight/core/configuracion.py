"""Configuración por repositorio de preguntas: `.voight.toml`.

Se busca subiendo desde la ruta indicada (o el directorio actual) hasta encontrar un
`.voight.toml`, la raíz del repositorio git o la raíz del sistema. Da los valores
por defecto de cada comando; una opción pasada en la línea de comandos siempre gana.

    [general]
    ignorar = ["borradores/**", "*.bak.xml"]   # rutas (relativas a la raíz) que no se procesan

    [ai]
    contexto = "Programación 1 (C), primer año"
    proveedor = "claude"
    modelo = "claude-opus-5"

    [dedup]
    umbral = 0.9
    conservar = "completa"

    [health]
    min_opciones = 4
    umbral_longitud = 1.5
    max_items = 50

    [format]
    fullwidth = true
    marcas = true
"""
from __future__ import annotations

import fnmatch
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

NOMBRE = ".voight.toml"
# Nombre anterior al cambio de questions a voight: se sigue leyendo.
NOMBRE_ANTERIOR = ".questions.toml"


@lru_cache(maxsize=64)
def _buscar(inicio: str) -> Optional[Path]:
    actual = Path(inicio).resolve()
    if actual.is_file():
        actual = actual.parent
    for directorio in (actual, *actual.parents):
        for nombre in (NOMBRE, NOMBRE_ANTERIOR):
            candidato = directorio / nombre
            if candidato.is_file():
                return candidato
        if (directorio / ".git").exists():
            return None
    return None


def buscar(rutas: Iterable = ()) -> Optional[Path]:
    """El .voight.toml que corresponde a la primera ruta (o al directorio actual)."""
    rutas = [Path(r) for r in rutas] or [Path.cwd()]
    return _buscar(str(rutas[0]))


@lru_cache(maxsize=64)
def _leer(ruta: str) -> dict:
    try:
        with open(ruta, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ValueError(f"No se pudo leer {ruta}: {e}") from None


def cargar(rutas: Iterable = ()) -> dict:
    """La configuración (con la clave interna `_raiz`), o {} si no hay .voight.toml."""
    ruta = buscar(rutas)
    if ruta is None:
        return {}
    return {**_leer(str(ruta)), "_raiz": ruta.parent}


def valor(config: dict, seccion: str, clave: str, defecto=None):
    return (config.get(seccion) or {}).get(clave, defecto)


def ignorado(ruta: Path, config: dict) -> bool:
    """True si la ruta coincide con algún patrón de [general] ignorar (relativo a la raíz)."""
    patrones = valor(config, "general", "ignorar", []) or []
    if not patrones or "_raiz" not in config:
        return False
    try:
        relativa = Path(ruta).resolve().relative_to(config["_raiz"]).as_posix()
    except ValueError:
        return False
    return any(fnmatch.fnmatch(relativa, p) or fnmatch.fnmatch(Path(relativa).name, p) for p in patrones)


def limpiar_cache() -> None:
    _buscar.cache_clear()
    _leer.cache_clear()
