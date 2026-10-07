import typer
from pathlib import Path

from voight.commands.common import LLM_OPTION, fail


def ui(
    directorio: str = typer.Argument(".", exists=True, file_okay=False),
    llm: bool = LLM_OPTION,
    host: str = typer.Option("127.0.0.1", "--host", show_default=True, help="Host del servidor web."),
    port: int = typer.Option(5000, "--port", show_default=True, help="Puerto del servidor web."),
    debug: bool = typer.Option(False, "--debug/--no-debug", help="Modo debug de Flask."),
):
    """Abre el editor web local (cerebro) sobre DIRECTORIO.

    Permite navegar y editar preguntas en Moodle XML y GIFT desde el navegador.
    Requiere el extra 'ui': uv tool install "questions[ui] @ git+https://github.com/INGCOM-UNRN/moodle-toolbox"
    """
    try:
        from voight.ui.app import run
    except ImportError as e:
        fail(
            f"Faltan dependencias del editor web ({e}). "
            'Instalalas con: uv tool install "questions[ui] @ git+https://github.com/INGCOM-UNRN/moodle-toolbox"'
            "  (en un entorno de desarrollo: uv sync --extra ui)"
        )
    run(str(Path(directorio).resolve()), host=host, port=port, debug=debug)
