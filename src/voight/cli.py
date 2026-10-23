import functools
import os
import sys

import click
import typer
from typer.core import TyperGroup
from yutani.cli import CONTEXTO, VARIABLE_DEPURAR, describir_error, opcion_version
from yutani.textos import traducir

from voight.core.llm_instructions import get_instructions

from voight.commands.ai import ai
from voight.commands.analyze import similar, stats
from voight.commands.config import config_app
from voight.commands.convert import convert_app
from voight.commands.dedup import dedup
from voight.commands.doctor import doctor_cmd
from voight.commands.fix import fix_app
from voight.commands.moodle import moodle_app
from voight.commands.format import format_cmd, format_init_cmd
from voight.commands.health import health_cmd
from voight.commands.spellcheck import spellcheck
from voight.commands.split import split
from voight.commands.synth import synth
from voight.commands.tree import tree_app
from voight.commands.ui import ui
from voight.commands.unify import unify
from voight.commands.validate import validate
from voight.commands.verify import verify
from voight.commands.xml import cdata, clean_tags, rename, xml_group


def llm_callback(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.echo(get_instructions(ctx.info_name))
    ctx.exit()


def _version_instalada() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("voight")
    except PackageNotFoundError:
        return "desconocida"


# -h/--help, --version/-v y ayuda de Typer/Click en español, desde yutani (N-ECO-14). La app
# no es TyperConErrores porque main() ejecuta el comando Click y ya atrapa los errores.
traducir()
app = typer.Typer(
    context_settings=dict(CONTEXTO),
    help="Herramientas para la gestión de preguntas de Moodle.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


@app.callback()
def main_callback(
    version: bool = opcion_version("voight", _version_instalada()),  # noqa: ARG001
    llm: bool = typer.Option(
        False,
        "--llm",
        callback=llm_callback,
        is_eager=True,
        help="Muestra instrucciones generales para un LLM.",
    ),
):
    """Herramientas para la gestión de preguntas de Moodle."""


class _GrupoConPredeterminado(TyperGroup):
    """`voight health` ES el diagnóstico: el primer argumento, si no es un subcomando, va
    al comando predeterminado (`voight health banco/`) y la ayuda del grupo es la suya,
    con los subcomandos (`stats`, `similar`) al final."""

    predeterminado = "check"

    def parse_args(self, ctx, args):
        if args and args[0] not in self.commands and args[0] not in ("-h", "--help", "--llm"):
            args = [self.predeterminado, *args]
        return super().parse_args(ctx, args)

    def format_help(self, ctx, formatter):
        comando = self.commands[self.predeterminado]
        with comando.make_context(ctx.info_name, [], parent=ctx.parent, resilient_parsing=True) as sub:
            comando.format_help(sub, formatter)
        visibles = [(n, c.get_short_help_str(300)) for n, c in self.commands.items() if not c.hidden]
        if not visibles:
            return
        try:
            from rich.console import Console
            from rich.panel import Panel
            from rich.table import Table
        except ImportError:
            with formatter.section("Subcomandos"):
                formatter.write_dl(visibles)
            return
        tabla = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
        tabla.add_column(style="bold cyan", no_wrap=True)
        tabla.add_column()
        for nombre, ayuda in visibles:
            tabla.add_row(nombre, ayuda)
        Console().print(Panel(tabla, title="Subcomandos", title_align="left", border_style="dim"))


def _deprecado(funcion, viejo: str, nuevo: str):
    """El comando con su nombre anterior: avisa por stderr y sigue funcionando."""
    @functools.wraps(funcion)
    def envoltura(*args, **kwargs):
        click.echo(f"Aviso: `voight {viejo}` ahora es `voight {nuevo}`; el nombre anterior se va a retirar.", err=True)
        return funcion(*args, **kwargs)
    return envoltura


# health: la salud del banco (el diagnóstico es el propio `health`), estadísticas y similares.
health_app = typer.Typer(
    cls=_GrupoConPredeterminado,
    help="Audita la salud del banco (con `stats` y `similar` como subcomandos).",
    no_args_is_help=True,
)
health_app.command("check", hidden=True)(health_cmd)
health_app.command("stats")(stats)
health_app.command("similar")(similar)
# validate daba el mismo informe que stats y un subconjunto de los chequeos de health.
health_app.command("validate", hidden=True)(_deprecado(validate, "health validate", "health"))

# fix: todo lo que modifica archivos: formato, código, nombres, HTML, ortografía y tags.
fix_app.command("format")(format_cmd)
fix_app.command("format-init")(format_init_cmd)
fix_app.command("clean-tags")(clean_tags)
fix_app.command("grammar")(spellcheck)
# fix xml: lo que hacía ya está en fix format (CDATA), fix name-from-title y fix clean-tags.
xml_app = typer.Typer(help="Ahora es `voight fix format`, `fix name-from-title` y `fix clean-tags`.")
xml_app.callback()(xml_group)
for nombre, funcion, nuevo in (("cdata", cdata, "fix format"), ("clean-tags", clean_tags, "fix clean-tags"),
                               ("rename", rename, "fix name-from-title")):
    xml_app.command(nombre)(_deprecado(funcion, f"fix xml {nombre}", nuevo))
fix_app.add_typer(xml_app, name="xml", hidden=True)

app.command("doctor")(doctor_cmd)
app.add_typer(health_app, name="health")
app.command("ai")(ai)
app.command("dedup")(dedup)
app.command("verify")(verify)
app.command("split")(split)
app.command("unify")(unify)
app.command("synth")(synth)
app.command("ui")(ui)

app.add_typer(config_app, name="config")
app.add_typer(convert_app, name="convert")
app.add_typer(fix_app, name="fix")
# tree: `tree export` es `split -o DIR` y `tree collect`, `unify`.
app.add_typer(tree_app, name="tree", hidden=True)
app.add_typer(moodle_app, name="moodle")

# Nombres anteriores (ocultos): avisan y siguen funcionando.
app.command("validate", hidden=True)(_deprecado(validate, "validate", "health"))
app.command("format", hidden=True)(_deprecado(format_cmd, "format", "fix format"))
app.command("grammar", hidden=True)(_deprecado(spellcheck, "grammar", "fix grammar"))
app.command("spellcheck", hidden=True)(_deprecado(spellcheck, "spellcheck", "fix grammar"))
app.command("languagetool", hidden=True)(_deprecado(spellcheck, "languagetool", "fix grammar"))
analyze_viejo = typer.Typer(help="Ahora es `voight health stats` y `voight health similar`.")
analyze_viejo.command("stats")(_deprecado(stats, "analyze stats", "health stats"))
analyze_viejo.command("similar")(_deprecado(similar, "analyze similar", "health similar"))
app.add_typer(analyze_viejo, name="analyze", hidden=True)
xml_viejo = typer.Typer(help="Ahora es `voight fix format`, `fix name-from-title` y `fix clean-tags`.")
xml_viejo.callback()(xml_group)
for nombre, funcion, nuevo in (("cdata", cdata, "fix format"), ("clean-tags", clean_tags, "fix clean-tags"),
                               ("rename", rename, "fix name-from-title")):
    xml_viejo.command(nombre)(_deprecado(funcion, f"xml {nombre}", nuevo))
app.add_typer(xml_viejo, name="xml", hidden=True)

cli = typer.main.get_command(app)

cli.name = "voight"


def main():
    try:
        cli()
    except Exception as e:
        if os.environ.get("VOIGHT_DEBUG") or os.environ.get(VARIABLE_DEPURAR):
            raise
        # describir_error: los errores de datos (ruta inexistente, archivo que no es UTF-8…) en español.
        click.echo(f"Error: {describir_error(e)} (VOIGHT_DEBUG=1 o P1_DEPURAR=1 muestra el traceback "
                   "completo)", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
