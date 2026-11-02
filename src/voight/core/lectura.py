"""Lectura determinista de bancos mixtos para las herramientas docentes."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from voight.core.banco import expandir_rutas, formato_de, parse_archivo


def leer_preguntas(rutas: Iterable[str | Path], recursivo: bool = True) -> list[dict]:
    raices = [Path(ruta) for ruta in rutas]
    archivos = sorted(
        {p.resolve() for p in expandir_rutas(raices, recursivo) if formato_de(p)}
    )
    preguntas = []
    for archivo in archivos:
        resultado = parse_archivo(archivo)
        if not resultado.get("success", False):
            error = resultado.get("error", {})
            raise ValueError(
                f"{archivo}: {error.get('message', 'no se pudo leer el banco')}"
            )
        categoria = "General"
        for raiz in raices:
            if raiz.is_dir() and archivo.is_relative_to(raiz.resolve()):
                padre = archivo.relative_to(raiz.resolve()).parent.as_posix()
                categoria = padre if padre != "." else "General"
                break
        indice = 0
        for pregunta in resultado.get("questions", []):
            if pregunta.get("type") == "Category":
                categoria = (pregunta.get("title") or "").removeprefix(
                    "$course$"
                ).strip("/") or "General"
                continue
            indice += 1
            preguntas.append(
                {
                    **pregunta,
                    "archivo": str(archivo),
                    "categoria": categoria,
                    "indice": indice,
                }
            )
    if not preguntas:
        raise ValueError("No se encontraron preguntas en las rutas especificadas.")
    return preguntas
