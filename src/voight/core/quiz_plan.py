"""Plan previo de cupos: la generación del MBZ usa las mismas validaciones."""

from __future__ import annotations

import math
from collections import Counter


def planificar_categorias(
    categorias: list[dict],
    preguntas_por_categoria: int = 1,
    titulo: str = "Cuestionario",
    tiempo_limite: int = 3600,
    calificacion_maxima: float = 10.0,
    intentos: int = 1,
    shuffle_respuestas: bool = True,
) -> dict:
    if type(preguntas_por_categoria) is not int or preguntas_por_categoria < 1:
        raise ValueError("El cupo por categoría debe ser un entero mayor que cero.")
    if tiempo_limite < 0 or intentos < 0:
        raise ValueError(
            "El tiempo límite y los intentos no pueden ser negativos (0: sin límite)."
        )
    if not math.isfinite(calificacion_maxima) or calificacion_maxima <= 0:
        raise ValueError("La calificación máxima debe ser finita y mayor que cero.")
    filas, errores = [], []
    if not categorias:
        errores.append("No se encontraron categorías con preguntas.")
    for categoria in categorias:
        tipos = Counter(q.get("type", "Desconocido") for q in categoria["questions"])
        # El escritor MBZ implementa los plugins de selección múltiple y V/F.
        no_soportados = sorted(set(tipos) - {"MC", "TF"})
        disponibles = tipos["MC"] + tipos["TF"]
        faltantes = max(0, preguntas_por_categoria - disponibles)
        fila = {
            "categoria": categoria["name"],
            "preguntas": len(categoria["questions"]),
            "disponibles": disponibles,
            "solicitadas": preguntas_por_categoria,
            "faltantes": faltantes,
            "tipos": dict(sorted(tipos.items())),
            "tipos_no_soportados": no_soportados,
        }
        filas.append(fila)
        if faltantes:
            errores.append(
                f"{categoria['name']}: se piden {preguntas_por_categoria} preguntas, "
                f"hay {disponibles}; faltan {faltantes}."
            )
        if no_soportados:
            errores.append(
                f"{categoria['name']}: el escritor MBZ no implementa estos tipos: "
                + ", ".join(no_soportados)
                + ". Usá exportación Moodle XML para conservarlos."
            )
    return {
        "ok": not errores,
        "titulo": titulo,
        "categorias": len(filas),
        "preguntas": sum(f["preguntas"] for f in filas),
        "slots": len(filas) * preguntas_por_categoria,
        "cupos": filas,
        "errores": errores,
        "configuracion": {
            "tiempo_limite": tiempo_limite,
            "calificacion_maxima": calificacion_maxima,
            "intentos": intentos,
            "shuffle_respuestas": shuffle_respuestas,
        },
    }


def planificar_quiz(
    rutas, preguntas_por_categoria: int = 1, recursivo: bool = True, **opciones
) -> dict:
    from voight.core.moodle_backup import recolectar_banco_unificado

    return planificar_categorias(
        recolectar_banco_unificado(rutas, recursivo),
        preguntas_por_categoria,
        **opciones,
    )
