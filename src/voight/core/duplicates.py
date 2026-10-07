"""Detector de preguntas duplicadas o altamente similares en bancos Moodle."""

from __future__ import annotations

import difflib
from typing import List, Dict, Any


def detectar_preguntas_duplicadas(preguntas: List[Dict[str, Any]], umbral_similitud: float = 0.85) -> List[Dict[str, Any]]:
    """Encuentra pares de preguntas con textos o enunciados redundantes."""
    duplicados = []
    n = len(preguntas)
    for i in range(n):
        for j in range(i + 1, n):
            p1 = preguntas[i]
            p2 = preguntas[j]
            t1 = p1.get("text", "") or p1.get("enunciado", "")
            t2 = p2.get("text", "") or p2.get("enunciado", "")
            
            ratio = difflib.SequenceMatcher(None, t1.strip().lower(), t2.strip().lower()).ratio()
            if ratio >= umbral_similitud:
                duplicados.append({
                    "id1": p1.get("name", f"P_{i+1}"),
                    "id2": p2.get("name", f"P_{j+1}"),
                    "similitud": round(ratio, 2),
                    "texto_resumen": t1[:60] + "...",
                })
    return duplicados
