import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv, set_key

CONFIG_DIR = Path.home() / ".voight"
ENV_FILE = CONFIG_DIR / ".env"

def get_api_key() -> Optional[str]:
    """Obtiene la API Key desde el entorno o el archivo de configuración global."""
    # 1. Intentar desde el entorno (incluye .env local si existe)
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    
    # 2. Intentar desde el archivo de configuración global
    if not api_key and ENV_FILE.exists():
        load_dotenv(ENV_FILE)
        api_key = os.getenv("GEMINI_API_KEY")
        
    return api_key

def get_model() -> str:
    """Obtiene el modelo por defecto desde el entorno o la configuración global."""
    load_dotenv()
    model = os.getenv("GEMINI_MODEL")
    
    if not model and ENV_FILE.exists():
        load_dotenv(ENV_FILE)
        model = os.getenv("GEMINI_MODEL")
        
    return model or "gemini-2.0-flash"

def save_api_key(api_key: str):
    """Guarda la API Key en el archivo de configuración global."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not ENV_FILE.exists():
        ENV_FILE.touch(mode=0o600)
    
    # Usar python-dotenv para guardar de forma persistente
    set_key(str(ENV_FILE), "GEMINI_API_KEY", api_key)

def save_model(model: str):
    """Guarda el modelo por defecto en el archivo de configuración global."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not ENV_FILE.exists():
        ENV_FILE.touch(mode=0o600)
    
    set_key(str(ENV_FILE), "GEMINI_MODEL", model)

def delete_api_key():
    """Elimina la API Key configurada."""
    if ENV_FILE.exists():
        ENV_FILE.unlink()

def save_typesafe_key(api_key: str):
    """Guarda la TYPESAFE_API_KEY (Jev, usada por `ai --mode classify`) en la configuración global."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not ENV_FILE.exists():
        ENV_FILE.touch(mode=0o600)
    set_key(str(ENV_FILE), "TYPESAFE_API_KEY", api_key)


def _leer(variable: str):
    load_dotenv()
    valor = os.getenv(variable)
    if not valor and ENV_FILE.exists():
        load_dotenv(ENV_FILE)
        valor = os.getenv(variable)
    return valor


def get_anthropic_key():
    """ANTHROPIC_API_KEY del entorno o de ~/.voight/.env (si no hay, el SDK prueba sus otras fuentes)."""
    return _leer("ANTHROPIC_API_KEY")


def get_proveedor() -> str:
    """Proveedor por defecto de `voight ai`: gemini (histórico) o claude."""
    return (_leer("VOIGHT_PROVEEDOR") or "gemini").lower()


def save_anthropic_key(api_key: str):
    """Guarda la ANTHROPIC_API_KEY (Claude, para `ai --proveedor claude`) en la configuración global."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not ENV_FILE.exists():
        ENV_FILE.touch(mode=0o600)
    set_key(str(ENV_FILE), "ANTHROPIC_API_KEY", api_key)


def save_proveedor(proveedor: str):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not ENV_FILE.exists():
        ENV_FILE.touch(mode=0o600)
    set_key(str(ENV_FILE), "VOIGHT_PROVEEDOR", proveedor)


def save_moodle_token(token: str):
    """Guarda el MOODLE_TOKEN (servicio web, para `moodle subir`) en la configuración global."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not ENV_FILE.exists():
        ENV_FILE.touch(mode=0o600)
    set_key(str(ENV_FILE), "MOODLE_TOKEN", token)
