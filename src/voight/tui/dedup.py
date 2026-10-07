"""TUI (Textual) para revisar los duplicados y decidir cuáles eliminar.

A la izquierda, los grupos; a la derecha, la pregunta que se conserva y el duplicado
en revisión, lado a lado y con las líneas distintas resaltadas. Nada se borra hasta
confirmar con `a`; al aplicar, cada eliminación queda en el log con la ruta completa.
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import List, Optional

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Label, ListItem, ListView, Static

from voight.core.lector import Archivo, Unidad
from voight.core.converter import question_to_gift
from voight.core.deduplicar import Revision, aplicar, registrar


def texto_de(u: Unidad) -> str:
    """Cómo se ve la pregunta: el bloque GIFT original o, en XML, su vista en GIFT."""
    if u.formato == "gift":
        return u.original
    return question_to_gift(u.pregunta)


_RESALTADO = "bold black on yellow"


def _palabras(linea_a: str, linea_b: str, ta: Text, tb: Text) -> None:
    """Dentro de un par de líneas distintas, resalta sólo las palabras que cambian."""
    pa, pb = re.split(r"(\s+)", linea_a), re.split(r"(\s+)", linea_b)
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, pa, pb, autojunk=False).get_opcodes():
        estilo = None if op == "equal" else _RESALTADO
        ta.append("".join(pa[i1:i2]), style=estilo)
        tb.append("".join(pb[j1:j2]), style=estilo)
    ta.append("\n")
    tb.append("\n")


def resaltar(a: str, b: str) -> tuple[Text, Text]:
    """Los dos textos con lo que difiere resaltado: palabras en las líneas cambiadas, líneas
    enteras en las que sobran de un lado."""
    lineas_a, lineas_b = a.splitlines(), b.splitlines()
    ta, tb = Text(), Text()
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, lineas_a, lineas_b, autojunk=False).get_opcodes():
        if op == "equal":
            for linea in lineas_a[i1:i2]:
                ta.append(linea + "\n")
                tb.append(linea + "\n")
            continue
        pares = min(i2 - i1, j2 - j1) if op == "replace" else 0
        for k in range(pares):
            _palabras(lineas_a[i1 + k], lineas_b[j1 + k], ta, tb)
        for linea in lineas_a[i1 + pares:i2]:
            ta.append(linea + "\n", style=_RESALTADO)
        for linea in lineas_b[j1 + pares:j2]:
            tb.append(linea + "\n", style=_RESALTADO)
    return ta, tb


class Confirmar(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancelar", "Cancelar"), Binding("s", "confirmar", "Sí")]

    def __init__(self, mensaje: str):
        super().__init__()
        self.mensaje = mensaje

    def compose(self) -> ComposeResult:
        with Vertical(id="dialogo"):
            yield Label(self.mensaje)
            with Horizontal(id="botones"):
                yield Button("Eliminar (s)", variant="error", id="si")
                yield Button("Cancelar (esc)", id="no")

    def on_button_pressed(self, evento: Button.Pressed) -> None:
        self.dismiss(evento.button.id == "si")

    def action_confirmar(self) -> None:
        self.dismiss(True)

    def action_cancelar(self) -> None:
        self.dismiss(False)


class DedupApp(App):
    """Revisión interactiva de duplicados. `exit` devuelve el resultado de aplicar (o None)."""

    TITLE = "voight dedup"
    CSS = """
    #grupos { width: 28%; border: round $primary; }
    #comparacion { width: 72%; }
    .panel { width: 1fr; border: round $secondary; padding: 0 1; }
    .panel.elimina { border: round $error; }
    .panel.conserva { border: round $success; }
    .encabezado { height: auto; color: $text-muted; }
    #estado { height: 1; padding: 0 1; background: $panel; }
    #dialogo { width: 70; height: auto; border: thick $error; padding: 1 2; background: $surface; }
    #botones { height: auto; margin-top: 1; }
    Confirmar { align: center middle; }
    """
    BINDINGS = [
        Binding("right,l", "siguiente", "Siguiente duplicado"),
        Binding("left,h", "anterior", "Anterior"),
        Binding("d", "alternar", "Eliminar/conservar"),
        Binding("p", "principal", "Conservar ésta"),
        Binding("c", "conservar_todas", "Conservar todas"),
        Binding("a", "aplicar", "Aplicar"),
        Binding("q", "salir", "Salir sin cambios"),
    ]

    def __init__(self, archivos: List[Archivo], revision: Revision, umbral: float, log: Path,
                 respaldo: Optional[Path] = None):
        super().__init__()
        self.respaldo = respaldo
        self.archivos = archivos
        self.revision = revision
        self.umbral = umbral
        self.ruta_log = log
        self.grupo = 0
        self.indice = 1  # miembro en revisión (el 0 es el principal al empezar)

    # --- armado -------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield ListView(*[ListItem(Label(self._etiqueta(g))) for g in range(len(self.revision))], id="grupos")
            with Vertical(id="comparacion"):
                with Horizontal():
                    with VerticalScroll(classes="panel", id="izquierda"):
                        yield Static(classes="encabezado", id="enc-izq")
                        yield Static(id="txt-izq")
                    with VerticalScroll(classes="panel", id="derecha"):
                        yield Static(classes="encabezado", id="enc-der")
                        yield Static(id="txt-der")
        yield Static(id="estado")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = f"umbral {self.umbral:g} · {len(self.revision)} grupos"
        self.query_one(ListView).focus()
        self._mostrar()

    # --- vista --------------------------------------------------------------

    def _etiqueta(self, g: int) -> str:
        principal = self.revision.principal[g]
        titulo = principal.pregunta.title or "<sin título>"
        return f"✗{self.revision.a_eliminar(g)}/{len(self.revision.miembros[g]) - 1}  {titulo[:40]}"

    def _otros(self) -> List[Unidad]:
        principal = self.revision.principal[self.grupo]
        return [u for u in self.revision.miembros[self.grupo] if u is not principal]

    def _actual(self) -> Optional[Unidad]:
        otros = self._otros()
        return otros[(self.indice - 1) % len(otros)] if otros else None

    def _encabezado(self, u: Unidad, rol: str) -> str:
        estado = "ELIMINAR" if self.revision.se_elimina(u) else "CONSERVAR"
        similitud = self.revision.similitud.get(id(u), 1.0)
        return f"{rol} · {estado} · similitud {similitud:.3f} · {u.pregunta.type}\n{u.archivo}"

    def _mostrar(self) -> None:
        if not len(self.revision):
            return
        principal, actual = self.revision.principal[self.grupo], self._actual()
        izquierda, derecha = resaltar(texto_de(principal), texto_de(actual) if actual else "")
        self.query_one("#enc-izq", Static).update(self._encabezado(principal, "Principal"))
        self.query_one("#txt-izq", Static).update(izquierda)
        panel_der = self.query_one("#derecha")
        if actual is not None:
            otros = self._otros()
            posicion = f"Duplicado {otros.index(actual) + 1}/{len(otros)}"
            self.query_one("#enc-der", Static).update(self._encabezado(actual, posicion))
            self.query_one("#txt-der", Static).update(derecha)
            elimina = self.revision.se_elimina(actual)
            panel_der.set_class(elimina, "elimina")
            panel_der.set_class(not elimina, "conserva")
        self.query_one("#izquierda").set_class(True, "conserva")
        self.query_one("#estado", Static).update(
            f"Grupo {self.grupo + 1}/{len(self.revision)} · se eliminarán {self.revision.a_eliminar()} preguntas "
            f"· log: {self.ruta_log.resolve()}")
        lista = self.query_one(ListView)
        if lista.children:
            lista.children[self.grupo].query_one(Label).update(self._etiqueta(self.grupo))

    def on_list_view_highlighted(self, evento: ListView.Highlighted) -> None:
        if evento.list_view.index is not None and evento.list_view.index != self.grupo:
            self.grupo = evento.list_view.index
            self.indice = 1
            self._mostrar()

    # --- acciones -----------------------------------------------------------

    def action_siguiente(self) -> None:
        self.indice += 1
        self._mostrar()

    def action_anterior(self) -> None:
        self.indice -= 1
        self._mostrar()

    def action_alternar(self) -> None:
        actual = self._actual()
        if actual is not None:
            self.revision.alternar(self.grupo, actual)
            self._mostrar()

    def action_principal(self) -> None:
        actual = self._actual()
        if actual is not None:
            anterior = self.revision.principal[self.grupo]
            self.revision.hacer_principal(self.grupo, actual)
            self.indice = self._otros().index(anterior) + 1  # se sigue viendo el par
            self._mostrar()

    def action_conservar_todas(self) -> None:
        self.revision.conservar_todas(self.grupo)
        self._mostrar()

    def action_aplicar(self) -> None:
        cantidad = self.revision.a_eliminar()
        if not cantidad:
            self.exit(None)
            return

        def decidir(confirmado: Optional[bool]) -> None:
            if not confirmado:
                return
            grupos = self.revision.grupos()
            cambios = aplicar(self.archivos, grupos, self.respaldo)
            registrar(grupos, cambios, self.ruta_log, self.umbral)
            self.exit({"eliminadas": cantidad, **cambios})

        self.push_screen(Confirmar(f"¿Eliminar {cantidad} preguntas? Se registran en {self.ruta_log.resolve()}."), decidir)

    def action_salir(self) -> None:
        self.exit(None)
