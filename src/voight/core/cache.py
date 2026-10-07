"""Caché de respuestas de modelos por contenido (hash de lo que se envió).

Volver a procesar un banco ya procesado no gasta tokens: la respuesta se guarda bajo
el SHA-256 de todo lo que determina el resultado (modo, instrucción, modelo y texto
enviado). Vive en $XDG_CACHE_HOME/questions (por defecto ~/.cache/questions) y se
puede desactivar con QUESTIONS_SIN_CACHE=1 o con la opción --sin-cache de cada comando.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional


def directorio_cache() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "questions"


class Cache:
    def __init__(self, espacio: str, activa: bool = True, raiz: Optional[Path] = None):
        self.activa = activa and not os.environ.get("QUESTIONS_SIN_CACHE")
        self.dir = (raiz or directorio_cache()) / espacio
        self.aciertos = 0

    @staticmethod
    def clave(*partes: Any) -> str:
        texto = json.dumps(partes, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(texto.encode("utf-8")).hexdigest()

    def _ruta(self, clave: str) -> Path:
        return self.dir / clave[:2] / f"{clave}.json"

    def obtener(self, clave: str) -> Optional[Any]:
        if not self.activa:
            return None
        ruta = self._ruta(clave)
        try:
            valor = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        self.aciertos += 1
        return valor

    def guardar(self, clave: str, valor: Any) -> None:
        if not self.activa:
            return
        ruta = self._ruta(clave)
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            temporal = ruta.with_suffix(".tmp")
            temporal.write_text(json.dumps(valor, ensure_ascii=False), encoding="utf-8")
            temporal.replace(ruta)
        except OSError:
            pass  # la caché nunca impide procesar
