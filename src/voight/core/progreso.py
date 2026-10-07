"""Barra de progreso (rich) para los comandos largos: health, classify, verify, calibrar.

Sólo se muestra si stderr es una terminal: en CI, con la salida redirigida o en los
tests no aparece y no ensucia el JSON ni los informes. Se dibuja en stderr y desaparece
al terminar.
"""
from __future__ import annotations

import os
import sys
import threading
from contextlib import contextmanager
from typing import Iterator, Optional


class Avance:
    """Lo que entrega `barra`: se llama para avanzar; `activa` dice si se ve."""

    def __init__(self, progreso=None, tarea=None):
        self._progreso, self._tarea = progreso, tarea
        self._candado = threading.Lock()
        self.activa = progreso is not None

    def __call__(self, n: int = 1) -> None:
        if self._progreso is not None:
            with self._candado:
                self._progreso.advance(self._tarea, n)


def mostrar_progreso() -> bool:
    if os.environ.get("QUESTIONS_SIN_PROGRESO"):
        return False
    try:
        return sys.stderr.isatty()
    except (AttributeError, ValueError):
        return False


@contextmanager
def barra(total: int, descripcion: str, activa: Optional[bool] = None) -> Iterator[Avance]:
    activa = mostrar_progreso() if activa is None else activa
    if not activa or total < 2:
        yield Avance()
        return
    from rich.console import Console
    from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn, TimeRemainingColumn

    columnas = (TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(),
                TimeElapsedColumn(), TextColumn("·"), TimeRemainingColumn())
    with Progress(*columnas, console=Console(stderr=True), transient=True) as progreso:
        yield Avance(progreso, progreso.add_task(descripcion, total=total))
