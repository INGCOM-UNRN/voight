"""Metadatos de clasificación de una pregunta (los que escribe `ai --mode classify`).

Se leen del comentario `// [bloom:B3-aplicar] [dificultad-enunciado:3.4/5] …` (GIFT), del
`<!-- … -->` que precede al `<question>` (XML) o de los tags de Moodle `bloom:aplicar`,
`dificultad-enunciado:3`, `dificultad-respuestas:2` (con `--tags`).
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

NIVELES_BLOOM = ("recordar", "comprender", "aplicar", "analizar", "evaluar", "crear")

_BLOOM = re.compile(r"\[bloom:\s*(?:B\d-)?([a-záéíóú]+)\s*\]", re.I)
_DIFICULTAD = re.compile(r"\[dificultad-(enunciado|respuestas):\s*([\d.]+)\s*(?:/\s*5)?\s*\]", re.I)
_MARCA = re.compile(r"\[clasificacion:\s*([^\]\s]+)", re.I)
_CONFIANZA = re.compile(r"\[clasificacion:[^\]]*?confianza=([\d.,]+)", re.I)


def leer_clasificacion(texto: str, tags: Iterable[str] = ()) -> dict:
    """{'bloom', 'dificultad_enunciado', 'dificultad_respuestas', 'clasificador', 'confianza'} presentes.

    `confianza` es la lista de confianzas del clasificador (bloom, enunciado[, respuestas]).
    """
    datos: dict = {}
    m = _BLOOM.search(texto or "")
    if m and m.group(1).lower() in NIVELES_BLOOM:
        datos["bloom"] = m.group(1).lower()
    for campo, valor in _DIFICULTAD.findall(texto or ""):
        datos[f"dificultad_{campo.lower()}"] = float(valor)
    m = _MARCA.search(texto or "")
    if m:
        datos["clasificador"] = m.group(1)
    m = _CONFIANZA.search(texto or "")
    if m:
        try:
            datos["confianza"] = [float(c) for c in m.group(1).strip(",").split(",") if c]
        except ValueError:
            pass
    for tag in tags:
        clave, _, valor = tag.partition(":")
        if clave == "bloom" and valor in NIVELES_BLOOM:
            datos.setdefault("bloom", valor)
        elif clave in ("dificultad-enunciado", "dificultad-respuestas"):
            try:
                datos.setdefault(f"dificultad_{clave.split('-')[1]}", float(valor))
            except ValueError:
                pass
    return datos


def codigo_bloom(nivel: Optional[str]) -> Optional[str]:
    return f"B{NIVELES_BLOOM.index(nivel) + 1}" if nivel in NIVELES_BLOOM else None
