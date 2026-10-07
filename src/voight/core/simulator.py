"""Simulador de examen balanceado a partir del banco de preguntas."""

from __future__ import annotations

import random
from typing import List, Dict, Any


def simular_examen_aleatorio(
    banco: List[Dict[str, Any]],
    cantidad_preguntas: int = 10,
    seed: int | None = 42,
) -> List[Dict[str, Any]]:
    """Extrae una muestra aleatoria balanceada de preguntas del banco."""
    rng = random.Random(seed)
    if len(banco) <= cantidad_preguntas:
        return list(banco)
    return rng.sample(banco, cantidad_preguntas)
