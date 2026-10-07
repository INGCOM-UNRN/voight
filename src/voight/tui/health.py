"""TUI (Textual) para recorrer los hallazgos de `health` y aplicar los arreglos disponibles.

A la izquierda, los errores y advertencias; al medio, las preguntas o archivos
afectados; a la derecha, el archivo con la pregunta. `f` aplica el arreglo automático
al archivo seleccionado y `F` a todos los del hallazgo (con confirmación); `e` abre
el archivo en $EDITOR y `r` vuelve a auditar.
"""
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Callable, Dict, List, Optional

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Label, ListItem, ListView, Static

from voight.core.hallazgos import ARREGLOS, archivos_de, arreglar, elementos, hallazgos, linea_de


class Confirmar(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancelar", "Cancelar"), Binding("s", "confirmar", "Sí")]

    def __init__(self, mensaje: str):
        super().__init__()
        self.mensaje = mensaje

    def compose(self) -> ComposeResult:
        with Vertical(id="dialogo"):
            yield Label(self.mensaje)
            with Horizontal(id="botones"):
                yield Button("Aplicar (s)", variant="warning", id="si")
                yield Button("Cancelar (esc)", id="no")

    def on_button_pressed(self, evento: Button.Pressed) -> None:
        self.dismiss(evento.button.id == "si")

    def action_confirmar(self) -> None:
        self.dismiss(True)

    def action_cancelar(self) -> None:
        self.dismiss(False)


class HealthApp(App):
    """Recorrido de los hallazgos. `exit` devuelve {clave: [archivos arreglados]}."""

    TITLE = "voight health"
    CSS = """
    #hallazgos { width: 30%; border: round $primary; }
    #elementos { width: 30%; border: round $secondary; }
    #vista { width: 40%; border: round $secondary; padding: 0 1; }
    #encabezado { height: auto; color: $text-muted; }
    #estado { height: 1; padding: 0 1; background: $panel; }
    #dialogo { width: 70; height: auto; border: thick $warning; padding: 1 2; background: $surface; }
    #botones { height: auto; margin-top: 1; }
    Confirmar { align: center middle; }
    """
    BINDINGS = [
        Binding("tab", "focus_next", "Cambiar de panel", show=False),
        Binding("f", "arreglar", "Arreglar archivo"),
        Binding("F", "arreglar_todos", "Arreglar todos"),
        Binding("e", "editar", "Editar"),
        Binding("r", "reauditar", "Reauditar"),
        Binding("q", "salir", "Salir"),
    ]

    def __init__(self, auditar: Callable[[], dict]):
        super().__init__()
        self.auditar = auditar
        self.resultado = auditar()
        self.lista: List[dict] = []
        self.items: List[dict] = []
        self.arreglados: Dict[str, List[str]] = {}

    # --- armado -------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield ListView(id="hallazgos")
            yield ListView(id="elementos")
            with VerticalScroll(id="vista"):
                yield Static(id="encabezado")
                yield Static(id="texto")
        yield Static(id="estado")
        yield Footer()

    def on_mount(self) -> None:
        self._cargar_hallazgos()
        self.query_one("#hallazgos", ListView).focus()

    def _cargar_hallazgos(self, indice: int = 0) -> None:
        self.lista = hallazgos(self.resultado)
        resumen = self.resultado["resumen"]
        self.sub_title = f"{resumen['total_errores']} errores · {resumen['total_advertencias']} advertencias"
        vista = self.query_one("#hallazgos", ListView)
        vista.clear()
        for h in self.lista:
            marca = "❌" if h["nivel"] == "error" else "⚠"
            arreglo = " 🔧" if h["arreglo"] else ""
            vista.append(ListItem(Label(f"{marca} {h['cantidad']:>4}  {h['descripcion']}{arreglo}")))
        if self.lista:
            vista.index = min(indice, len(self.lista) - 1)
            self._cargar_elementos()
        else:
            self.query_one("#elementos", ListView).clear()
            self.query_one("#texto", Static).update("✅ Sin hallazgos.")
        self._estado()

    # --- vista --------------------------------------------------------------

    def _hallazgo(self) -> Optional[dict]:
        indice = self.query_one("#hallazgos", ListView).index
        return self.lista[indice] if self.lista and indice is not None else None

    def _elemento(self) -> Optional[dict]:
        indice = self.query_one("#elementos", ListView).index
        return self.items[indice] if self.items and indice is not None else None

    def _cargar_elementos(self) -> None:
        h = self._hallazgo()
        self.items = elementos(self.resultado, h["clave"]) if h else []
        vista = self.query_one("#elementos", ListView)
        vista.clear()
        for e in self.items[:2000]:
            nombre = Path(e["archivo"]).name if e["archivo"] else "—"
            vista.append(ListItem(Label(f"{e['titulo'] or nombre}"[:60])))
        if self.items:
            vista.index = 0
        self._mostrar()

    def _mostrar(self) -> None:
        e, h = self._elemento(), self._hallazgo()
        encabezado, texto = self.query_one("#encabezado", Static), self.query_one("#texto", Static)
        if e is None:
            encabezado.update("")
            texto.update("")
            return
        lineas = [e["archivo"] or "", e["detalle"]]
        if h and h["arreglo"]:
            lineas.append(f"🔧 f: {ARREGLOS[h['clave']][0]}")
        encabezado.update("\n".join(x for x in lineas if x))
        if not e["archivo"] or not Path(e["archivo"]).exists():
            texto.update("")
            return
        contenido = Path(e["archivo"]).read_text(encoding="utf-8", errors="replace")
        inicio = linea_de(contenido, e["titulo"])
        salida = Text()
        for i, linea in enumerate(contenido.splitlines()):
            salida.append(linea + "\n", style="bold" if inicio and i == inicio else None)
        texto.update(salida)
        self.query_one("#vista", VerticalScroll).scroll_to(y=max(0, inicio - 2), animate=False)

    def _estado(self, mensaje: str = "") -> None:
        total = sum(len(v) for v in self.arreglados.values())
        self.query_one("#estado", Static).update(mensaje or f"{total} archivos arreglados en esta sesión · "
                                                           "tab: cambiar de panel")

    def on_list_view_highlighted(self, evento: ListView.Highlighted) -> None:
        if evento.list_view.id == "hallazgos":
            self._cargar_elementos()
        else:
            self._mostrar()

    # --- acciones -----------------------------------------------------------

    def _registrar(self, clave: str, archivos: List[Path]) -> int:
        hechos = [str(a) for a in archivos if Path(a).exists() and arreglar(Path(a), clave)]
        self.arreglados.setdefault(clave, []).extend(hechos)
        return len(hechos)

    def action_arreglar(self) -> None:
        h, e = self._hallazgo(), self._elemento()
        if not h or not e or not e["archivo"]:
            return
        if not h["arreglo"]:
            self._estado("Este hallazgo no tiene arreglo automático: e para editar el archivo.")
            return
        n = self._registrar(h["clave"], [Path(e["archivo"])])
        self._reauditar(f"{'✓ Arreglado' if n else 'Sin cambios'}: {e['archivo']}")

    def action_arreglar_todos(self) -> None:
        h = self._hallazgo()
        if not h or not h["arreglo"]:
            self._estado("Este hallazgo no tiene arreglo automático.")
            return
        archivos = archivos_de(self.resultado, h["clave"])

        def decidir(confirmado: Optional[bool]) -> None:
            if confirmado:
                n = self._registrar(h["clave"], archivos)
                self._reauditar(f"✓ {n} de {len(archivos)} archivos arreglados ({ARREGLOS[h['clave']][0]}).")

        self.push_screen(Confirmar(f"¿{ARREGLOS[h['clave']][0].capitalize()} en {len(archivos)} archivos?"), decidir)

    def action_editar(self) -> None:
        e = self._elemento()
        if not e or not e["archivo"]:
            return
        editor = shlex.split(os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi")
        linea = linea_de(Path(e["archivo"]).read_text(encoding="utf-8", errors="replace"), e["titulo"]) + 1
        with self.suspend():
            subprocess.run([*editor, f"+{linea}", e["archivo"]])
        self._reauditar(f"Editado: {e['archivo']}")

    def _reauditar(self, mensaje: str = "") -> None:
        indice = self.query_one("#hallazgos", ListView).index or 0
        self.resultado = self.auditar()
        self._cargar_hallazgos(indice)
        self._estado(mensaje)

    def action_reauditar(self) -> None:
        self._reauditar("Auditoría actualizada.")

    def action_salir(self) -> None:
        self.exit(self.arreglados)
