import click
import typer
from pathlib import Path
from typing import List, Optional

from voight.commands.common import LLM_OPTION, emitir_json, fail
from voight.core.unifier import unificar


def unify(
    paths: Optional[List[Path]] = typer.Argument(None, exists=True),
    llm: bool = LLM_OPTION,
    output_file: Path = typer.Option(
        ..., "-o", "--output",
        help="Archivo de salida unificado (.gift o .xml).",
    ),
    formato: Optional[str] = typer.Option(
        None, "-f", "--format",
        click_type=click.Choice(["gift", "xml"], case_sensitive=False),
        help="Formato de salida (por defecto se deduce de la extensión del archivo de salida).",
    ),
    recursive: bool = typer.Option(
        True, "-r", "--recursive/--no-recursive",
        help="Procesar directorios recursivamente (por defecto True).",
    ),
    remove: bool = typer.Option(
        False, "--remove",
        help="Borrar los archivos fuente después de unificarlos.",
    ),
    incrustar: bool = typer.Option(
        True, "--incrustar/--no-incrustar",
        help="XML: renderiza los diagramas mermaid e incrusta las imágenes relativas en la salida."),
    formato_diagrama: str = typer.Option(
        "png", "--diagramas",
        click_type=click.Choice(["png", "svg"]),
        help="Formato de imagen de los diagramas mermaid incrustados."),
    output_json: bool = typer.Option(False, "--json", help="Emite el resultado como JSON versionado."),
):
    """Unifica árboles o grupos de archivos de preguntas (GIFT o XML) en un único archivo.

    Es la operación inversa a 'split' (también con -o): recopila preguntas
    recorriendo los directorios especificados, infiere y preserva las categorías,
    y genera un único banco monolítico (.gift o .xml).

    En Moodle XML, los bloques ```mermaid se renderizan con mermaid-cli (`mmdc`) y las
    imágenes con ruta relativa al archivo de la pregunta se incrustan en la salida.
    """
    if not paths:
        paths = [Path(".")]

    try:
        total = unificar(
            rutas=paths,
            archivo_salida=output_file,
            formato=formato,
            recursivo=recursive,
            eliminar_origen=remove,
            incrustar=incrustar,
            formato_diagrama=formato_diagrama,
        )
    except Exception as e:
        fail(f"Error durante la unificación: {e}")

    if total == 0:
        click.echo("No se encontraron preguntas para unificar.", err=True)
        raise typer.Exit(code=1)

    if output_json:
        emitir_json("unify", {"preguntas": total, "archivo": str(output_file)})
        return
    click.echo(f"✓ Unificación completada exitosamente: {total} preguntas escritas en {output_file}")
