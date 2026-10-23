"""Configuración por repositorio de preguntas: `.voight.toml` (o `.voight`).

Se busca subiendo desde la ruta indicada (o el directorio actual) hasta encontrar un
`.voight.toml` o `.voight` (ambos TOML), la raíz del repositorio git o la raíz del
sistema. `voight fix format-init` crea la sección [format] con todas sus claves. Da los valores
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

    [format]           # ver PLANTILLA_FORMAT
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
# En el mismo directorio, el primero gana.
NOMBRES = (NOMBRE, ".voight")

# Claves de [format]: la configuración completa de `voight fix format` para el banco.
CLAVES_FORMAT = ("fullwidth", "normal", "marcas", "indentacion", "gaff", "correct_first")

PLANTILLA_FORMAT = """\
# Formato del banco de preguntas: `voight fix format` toma estos valores para todo el
# árbol (se busca subiendo desde la ruta indicada). Una opción de la línea de comandos gana.
[format]
# Caracteres del código: fullwidth = true los protege (＝ ｛ ； …) y normal = true los
# restaura a ASCII. Son excluyentes; con las dos en false, no se tocan.
fullwidth = false
normal = false
# Con fullwidth: agregar las marcas · (indentación) y ↵ (fin de línea).
marcas = true
# Marcar la indentación del código con · (un punto por espacio), también con normal.
indentacion = false
# Formatear el código C con gaff (estilo de la cátedra); requiere gaff instalado.
gaff = false
# Ordenar las opciones de opción múltiple por porcentaje (la correcta primero).
correct_first = false
"""


@lru_cache(maxsize=64)
def _buscar(inicio: str) -> Optional[Path]:
    actual = Path(inicio).resolve()
    if actual.is_file():
        actual = actual.parent
    for directorio in (actual, *actual.parents):
        for nombre in NOMBRES:
            candidato = directorio / nombre
            if candidato.is_file():
                return candidato
        if (directorio / ".git").exists():
            return None
    return None


def buscar(rutas: Iterable = ()) -> Optional[Path]:
    """El .voight.toml (o .voight) que corresponde a la primera ruta (o al directorio actual)."""
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


def crear_plantilla_format(directorio: Path) -> Path:
    """Escribe la sección [format] en el archivo de configuración de `directorio`.

    Usa el `.voight.toml` o `.voight` que ya esté ahí (agrega la sección al final) o
    crea un `.voight.toml`. Si el archivo ya tiene [format], no lo toca: ValueError.
    """
    existente = next((directorio / n for n in NOMBRES if (directorio / n).is_file()), None)
    if existente is None:
        destino = directorio / NOMBRE
        destino.write_text(PLANTILLA_FORMAT, encoding="utf-8")
        return destino
    texto = existente.read_text(encoding="utf-8")
    try:
        datos = tomllib.loads(texto)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"No se pudo leer {existente}: {e}") from None
    if "format" in datos:
        raise ValueError(f"{existente} ya tiene una sección [format]")
    separador = "" if not texto or texto.endswith("\n\n") else ("\n" if texto.endswith("\n") else "\n\n")
    existente.write_text(texto + separador + PLANTILLA_FORMAT, encoding="utf-8")
    limpiar_cache()
    return existente


def limpiar_cache() -> None:
    _buscar.cache_clear()
    _leer.cache_clear()
