import contextlib
import io

import click
import typer
from pathlib import Path
from typing import Optional

from voight.core import tree as core_tree
from voight.core.incrustar import ErrorIncrustacion
from voight.commands.common import LLM_OPTION, emitir_json, fail

tree_app = typer.Typer(help="Organiza bancos en árboles de directorios por categoría.")


@tree_app.callback()
def tree(llm: bool = LLM_OPTION):
    """Organiza bancos en árboles de directorios por categoría.

    Reemplaza a moodle-reorganizer: un banco monolítico GIFT/XML se exporta a
    una carpeta con 1 archivo por pregunta (organizado por categorías) y puede
    recolectarse nuevamente a un archivo único.
    """


@tree_app.command(name="export")
def export_cmd(
    archivo: Path = typer.Argument(..., exists=True),
    dir_salida: Path = typer.Option(
        ..., "-o", "--output-dir",
        help="Directorio de destino del árbol de preguntas."),
    formato: Optional[str] = typer.Option(
        None, "--formato", "--format",
        click_type=click.Choice(["gift", "xml"]),
        help="Forzar el formato (por defecto se deduce de la extensión)."),
    output_json: bool = typer.Option(False, "--json", help="Emite el resultado como JSON versionado."),
):
    """Exporta ARCHIVO (banco monolítico) a un árbol de directorios."""
    with contextlib.redirect_stdout(io.StringIO()) if output_json else contextlib.nullcontext():
        cantidad = core_tree.exportar(archivo, dir_salida, formato)
    if cantidad < 0:
        fail("La exportación falló.")
    if output_json:
        emitir_json("tree export", {"preguntas": cantidad, "directorio": str(dir_salida)})
        return
    click.echo(f"\nÁrbol generado en: {dir_salida}")


@tree_app.command(name="collect")
def collect_cmd(
    directorio: Path = typer.Argument(..., exists=True, file_okay=False),
    archivo_salida: Path = typer.Option(
        ..., "-o", "--output",
        help="Archivo monolítico de destino (.gift o .xml; define el formato)."),
    formato: Optional[str] = typer.Option(
        None, "--formato", "--format",
        click_type=click.Choice(["gift", "xml"]),
        help="Forzar el formato (por defecto se deduce de la extensión de salida)."),
    incrustar: bool = typer.Option(
        True, "--incrustar/--no-incrustar",
        help="XML: renderiza los diagramas mermaid e incrusta las imágenes relativas en la salida."),
    formato_diagrama: str = typer.Option(
        "png", "--diagramas",
        click_type=click.Choice(["png", "svg"]),
        help="Formato de imagen de los diagramas mermaid incrustados."),
    output_json: bool = typer.Option(False, "--json", help="Emite el resultado como JSON versionado."),
):
    """Recolecta DIRECTORIO en un banco monolítico único.

    En Moodle XML, los bloques ```mermaid se renderizan con mermaid-cli (`mmdc`) y las
    imágenes con ruta relativa al archivo de la pregunta se incrustan en la salida.
    """
    try:
        with contextlib.redirect_stdout(io.StringIO()) if output_json else contextlib.nullcontext():
            cantidad = core_tree.recolectar(directorio, archivo_salida, formato,
                                            incrustar=incrustar, formato_diagrama=formato_diagrama)
    except ErrorIncrustacion as e:
        fail(f"No se pudo incrustar: {e}")
    if cantidad == 0:
        click.echo("No se recolectó ninguna pregunta.", err=True)
        raise typer.Exit(code=1)
    if output_json:
        emitir_json("tree collect", {"preguntas": cantidad, "archivo": str(archivo_salida)})
