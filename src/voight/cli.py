import os
import sys

import click
import typer
from yutani.cli import CONTEXTO, VARIABLE_DEPURAR, describir_error, opcion_version
from yutani.textos import traducir

from voight.core.llm_instructions import get_instructions

from voight.commands.ai import ai
from voight.commands.analyze import analyze_app
from voight.commands.config import config_app
from voight.commands.convert import convert_app
from voight.commands.dedup import dedup
from voight.commands.doctor import doctor_cmd
from voight.commands.fix import fix_app
from voight.commands.moodle import moodle_app
from voight.commands.format import format_cmd
from voight.commands.health import health_cmd
from voight.commands.spellcheck import spellcheck
from voight.commands.split import split
from voight.commands.synth import synth
from voight.commands.tree import tree_app
from voight.commands.ui import ui
from voight.commands.unify import unify
from voight.commands.validate import validate
from voight.commands.verify import verify
from voight.commands.xml import xml_app


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


app.command("doctor")(doctor_cmd)
app.command("health")(health_cmd)
app.command("ai")(ai)
app.command("validate")(validate)
app.command("dedup")(dedup)
app.command("verify")(verify)
app.command("format")(format_cmd)
app.command("split")(split)
app.command("unify")(unify)
app.command("synth")(synth)
app.command("ui")(ui)
app.command("spellcheck")(spellcheck)
# Alias históricos de `spellcheck` (LanguageTool).
app.command("languagetool")(spellcheck)
app.command("grammar")(spellcheck)

app.add_typer(config_app, name="config")
app.add_typer(convert_app, name="convert")
app.add_typer(fix_app, name="fix")
app.add_typer(analyze_app, name="analyze")
app.add_typer(tree_app, name="tree")
app.add_typer(xml_app, name="xml")
app.add_typer(moodle_app, name="moodle")

cli = typer.main.get_command(app)

# Ejecutables anteriores al cambio de nombre: siguen funcionando, con aviso.
_ALIAS_DEPRECADOS = {"questions", "moodle-toolbox"}


def _avisar_alias_deprecado() -> None:
    invocado = os.path.basename(sys.argv[0]) if sys.argv else ""
    if invocado in _ALIAS_DEPRECADOS:
        click.echo(f"Aviso: `{invocado}` ahora se llama `voight`; el nombre anterior se va a retirar.", err=True)
cli.name = "voight"


def main():
    _avisar_alias_deprecado()
    try:
        cli()
    except Exception as e:
        if os.environ.get("VOIGHT_DEBUG") or os.environ.get("QUESTIONS_DEBUG") or os.environ.get(VARIABLE_DEPURAR):
            raise
        # describir_error: los errores de datos (ruta inexistente, archivo que no es UTF-8…) en español.
        click.echo(f"Error: {describir_error(e)} (VOIGHT_DEBUG=1 o P1_DEPURAR=1 muestra el traceback "
                   "completo)", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
