"""TUI (Textual) para revisar las clasificaciones de Bloom con poca confianza.

A la izquierda, las preguntas que el modelo clasificó con confianza baja (de la menos
a la más confiable); a la derecha, la pregunta, la clasificación actual y la escala.
`1`–`6` elige el nivel de Bloom, `+`/`-` ajusta la dificultad del enunciado y `a`
acepta la del modelo. Nada se escribe hasta `s`: entonces cada corrección queda en el
comentario de la pregunta (clasificador `manual`, que reclasificar no pisa) y, con
un CSV de referencias, también en él para calibrar.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Footer, Header, Label, ListItem, ListView, Static

from voight.core.lector import Archivo, Unidad
from voight.core.clasificacion import BLOOM, CODIGO_BLOOM, Clasificacion, confianza_minima, corregida, guardar_correcciones
from voight.core.converter import question_to_gift

NIVELES = list(BLOOM)


def texto_de(u: Unidad) -> str:
    return u.original if u.formato == "gift" else question_to_gift(u.pregunta)


class ClasificacionApp(App):
    """Revisión de clasificaciones. `exit` devuelve el resultado de guardar (o None)."""

    TITLE = "voight ai --mode classify --revisar"
    CSS = """
    #preguntas { width: 35%; border: round $primary; }
    #detalle { width: 65%; border: round $secondary; padding: 0 1; }
    #estado { height: 1; padding: 0 1; background: $panel; }
    """
    BINDINGS = [
        *[Binding(str(i), f"bloom({i})", NIVELES[i - 1], show=False) for i in range(1, 7)],
        Binding("plus,equals_sign", "dificultad(1)", "+dificultad", show=False),
        Binding("minus", "dificultad(-1)", "-dificultad", show=False),
        Binding("a", "aceptar", "Aceptar la del modelo"),
        Binding("u", "deshacer", "Deshacer"),
        Binding("s", "guardar", "Guardar"),
        Binding("q", "salir", "Salir sin guardar"),
    ]

    def __init__(self, archivos: List[Archivo], unidades: List[Unidad], tags: bool = False,
                 referencias: Optional[Path] = None):
        super().__init__()
        self.archivos = archivos
        self.unidades = unidades
        self.tags = tags
        self.referencias = referencias
        self.correcciones: Dict[int, Clasificacion] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield ListView(*[ListItem(Label(self._etiqueta(u))) for u in self.unidades], id="preguntas")
            with VerticalScroll(id="detalle"):
                yield Static(id="texto")
        yield Static(id="estado")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = f"{len(self.unidades)} preguntas para revisar"
        self.query_one(ListView).focus()
        self._mostrar()

    # --- vista --------------------------------------------------------------

    def _actual(self) -> Optional[Unidad]:
        i = self.query_one(ListView).index
        return self.unidades[i] if self.unidades and i is not None else None

    def _meta(self, u: Unidad) -> dict:
        return getattr(u.pregunta, "metadata", None) or {}

    def _etiqueta(self, u: Unidad) -> str:
        c = self.correcciones.get(id(u))
        if c is not None:
            return f"✎ {CODIGO_BLOOM[c.bloom]} {(u.pregunta.title or '<sin título>')[:40]}"
        meta = self._meta(u)
        confianza = confianza_minima(u)
        return (f"  {CODIGO_BLOOM.get(meta.get('bloom'), 'B?')} {confianza if confianza is not None else '?':<4} "
                f"{(u.pregunta.title or '<sin título>')[:40]}")

    def _mostrar(self) -> None:
        u = self._actual()
        if u is None:
            return
        meta, c = self._meta(u), self.correcciones.get(id(u))
        salida = Text()
        salida.append(f"{u.archivo}\n", style="dim")
        salida.append(f"Modelo: {CODIGO_BLOOM.get(meta.get('bloom'), 'B?')}-{meta.get('bloom', '?')} · "
                      f"enunciado {meta.get('dificultad_enunciado', '?')}/5 · confianza {meta.get('confianza', '?')}\n")
        if c is not None:
            salida.append(f"Corrección: {CODIGO_BLOOM[c.bloom]}-{c.bloom} · enunciado {c.enunciado:g}/5\n", style="bold green")
        salida.append("\n" + texto_de(u) + "\n\n")
        elegido = c.bloom if c is not None else meta.get("bloom")
        for i, (nivel, descripcion) in enumerate(BLOOM.items(), 1):
            estilo = "bold reverse" if nivel == elegido else None
            salida.append(f"{i} {CODIGO_BLOOM[nivel]}-{nivel}: ", style=estilo)
            salida.append(descripcion + "\n", style="dim" if nivel != elegido else None)
        self.query_one("#texto", Static).update(salida)
        self._estado()

    def _estado(self, mensaje: str = "") -> None:
        destino = f" · referencias: {self.referencias}" if self.referencias else ""
        self.query_one("#estado", Static).update(
            mensaje or f"{len(self.correcciones)} correcciones sin guardar{destino} · 1–6 Bloom, +/- dificultad")

    def _refrescar(self, u: Unidad) -> None:
        lista = self.query_one(ListView)
        lista.children[self.unidades.index(u)].query_one(Label).update(self._etiqueta(u))
        self._mostrar()

    def on_list_view_highlighted(self, evento: ListView.Highlighted) -> None:
        self._mostrar()

    # --- acciones -----------------------------------------------------------

    def _siguiente(self) -> None:
        lista = self.query_one(ListView)
        if lista.index is not None and lista.index + 1 < len(self.unidades):
            lista.index += 1

    def action_bloom(self, nivel: int) -> None:
        u = self._actual()
        if u is None:
            return
        anterior = self.correcciones.get(id(u))
        enunciado = anterior.enunciado if anterior is not None else None
        self.correcciones[id(u)] = corregida(u, NIVELES[nivel - 1], enunciado)
        self._refrescar(u)
        self._siguiente()

    def action_aceptar(self) -> None:
        u = self._actual()
        if u is not None and self._meta(u).get("bloom") in BLOOM:
            self.correcciones[id(u)] = corregida(u, self._meta(u)["bloom"])
            self._refrescar(u)
            self._siguiente()

    def action_dificultad(self, delta: int) -> None:
        u = self._actual()
        if u is None:
            return
        c = self.correcciones.get(id(u)) or corregida(u, self._meta(u).get("bloom") or "comprender")
        self.correcciones[id(u)] = corregida(u, c.bloom, min(5.0, max(1.0, round(c.enunciado) + delta)), c.respuestas)
        self._refrescar(u)

    def action_deshacer(self) -> None:
        u = self._actual()
        if u is not None and self.correcciones.pop(id(u), None) is not None:
            self._refrescar(u)

    def action_guardar(self) -> None:
        if not self.correcciones:
            self.exit(None)
            return
        resultado = guardar_correcciones(self.archivos, self.correcciones, self.tags, self.referencias, self.unidades)
        self.exit({"correcciones": len(self.correcciones), **resultado})

    def action_salir(self) -> None:
        self.exit(None)
