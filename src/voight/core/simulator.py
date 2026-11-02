"""Muestreo uniforme reproducible, sin reemplazo, de preguntas de un banco."""

from __future__ import annotations

import random
from typing import Any


def simular_examen_aleatorio(
    banco: list[dict[str, Any]], cantidad_preguntas: int = 10, seed: int | None = 42
) -> list[dict[str, Any]]:
    """Selecciona exactamente la cantidad solicitada sin modificar el banco."""
    if type(cantidad_preguntas) is not int or cantidad_preguntas < 1:
        raise ValueError("La cantidad de preguntas debe ser un entero mayor que cero.")
    if cantidad_preguntas > len(banco):
        raise ValueError(
            f"Se piden {cantidad_preguntas} preguntas, pero el banco tiene {len(banco)}."
        )
    return random.Random(seed).sample(banco, cantidad_preguntas)
