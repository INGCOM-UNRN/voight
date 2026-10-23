"""Configuración global de voight: `~/.voight/.env`, con un único registro de claves.

`voight config set|get|unset|show` trabajan sobre `CLAVES`; cada clave es una variable
de entorno, así que lo que está en el entorno siempre gana sobre lo guardado. Al
arrancar, la CLI pone lo guardado en el entorno (`cargar_entorno`) sin pisar nada: de
ahí lo leen yutani.ia (GEMINI_API_KEY, ANTHROPIC_API_KEY), `moodle subir` (MOODLE_URL,
MOODLE_TOKEN) y `ai --mode classify` (TYPESAFE_API_KEY).

El proveedor y el modelo de IA comunes a todo el ecosistema viven en
`~/.config/p1/ia.toml` (yutani.ia); `proveedor` y `modelo` de acá son sólo de voight.
`VOIGHT_CONFIG_DIR` cambia el directorio (los tests lo usan para no tocar el del usuario).
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from dotenv import dotenv_values, load_dotenv, set_key, unset_key


@dataclass(frozen=True)
class Clave:
    variable: str
    descripcion: str
    secreta: bool = True


CLAVES: Dict[str, Clave] = {
    "gemini-key": Clave("GEMINI_API_KEY", "clave de Gemini (proveedor google de `voight ai`)"),
    "anthropic-key": Clave("ANTHROPIC_API_KEY", "clave de Claude (proveedor claude de `voight ai`)"),
    "typesafe-key": Clave("TYPESAFE_API_KEY", "clave de Jev para `voight ai --mode classify`"),
    "moodle-token": Clave("MOODLE_TOKEN", "token del servicio web para `voight moodle subir`"),
    "moodle-url": Clave("MOODLE_URL", "URL del sitio Moodle para `voight moodle subir`", secreta=False),
    "proveedor": Clave("VOIGHT_PROVEEDOR", "proveedor de IA de `voight ai` (sobre el de ~/.config/p1/ia.toml)",
                       secreta=False),
    "modelo": Clave("VOIGHT_MODELO", "modelo de IA de `voight ai` (sobre el de ~/.config/p1/ia.toml)",
                    secreta=False),
}


def directorio_config() -> Path:
    return Path(os.environ.get("VOIGHT_CONFIG_DIR") or Path.home() / ".voight")


def archivo_env() -> Path:
    return directorio_config() / ".env"


def clave(nombre: str) -> Clave:
    """La clave por su nombre en `voight config` o por su variable (GEMINI_API_KEY…)."""
    if nombre in CLAVES:
        return CLAVES[nombre]
    for c in CLAVES.values():
        if c.variable == nombre.upper():
            return c
    raise KeyError(nombre)


def _guardadas() -> Dict[str, Optional[str]]:
    archivo = archivo_env()
    return dotenv_values(archivo) if archivo.exists() else {}


# Lo que `cargar_entorno` puso en el entorno desde el archivo (no cuenta como "entorno").
_CARGADAS: Dict[str, str] = {}


def leer(variable: str) -> Tuple[Optional[str], Optional[str]]:
    """(valor, origen): el entorno gana sobre `~/.voight/.env`."""
    actual = os.environ.get(variable)
    if actual and _CARGADAS.get(variable) != actual and actual != _guardadas().get(variable):
        return actual, "entorno"
    valor = _guardadas().get(variable)
    if valor:
        return valor, str(archivo_env())
    return None, None


def guardar(variable: str, valor: str) -> Path:
    """Guarda la variable en `~/.voight/.env` (creado con permisos 600)."""
    archivo = archivo_env()
    archivo.parent.mkdir(parents=True, exist_ok=True)
    if not archivo.exists():
        archivo.touch(mode=0o600)
    set_key(str(archivo), variable, valor)
    return archivo


def borrar(variable: str) -> bool:
    """Quita SÓLO esa variable de `~/.voight/.env`; True si estaba."""
    archivo = archivo_env()
    if not archivo.exists() or variable not in _guardadas():
        return False
    unset_key(str(archivo), variable)
    if variable in _CARGADAS and os.environ.get(variable) == _CARGADAS.pop(variable):
        del os.environ[variable]
    return True


def ocultar(valor: str) -> str:
    if len(valor) <= 8:
        return "*" * len(valor)
    return valor[:4] + "*" * (len(valor) - 8) + valor[-4:]


def _leer(variable: str) -> Optional[str]:
    return leer(variable)[0]


def get_proveedor() -> Optional[str]:
    """`VOIGHT_PROVEEDOR` (entorno o ~/.voight/.env), si está; si no, decide yutani.ia."""
    valor = _leer("VOIGHT_PROVEEDOR")
    return valor.lower() if valor else None


def get_modelo() -> Optional[str]:
    """`VOIGHT_MODELO` (entorno o ~/.voight/.env), si está."""
    return _leer("VOIGHT_MODELO")


def cargar_entorno(local: bool = False) -> None:
    """Pone en el entorno lo guardado con `voight config` sin pisar lo que ya esté; con
    `local`, también el `.env` del directorio de trabajo (como hizo siempre `voight ai`)."""
    if local:
        load_dotenv()
    for variable, valor in _guardadas().items():
        if valor is not None and variable not in os.environ:
            os.environ[variable] = valor
            _CARGADAS[variable] = valor
