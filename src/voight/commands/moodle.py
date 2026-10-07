"""Comandos que hablan con un sitio Moodle."""

from pathlib import Path
from typing import List

import click
import typer

from voight.commands.common import LLM_OPTION, emitir_json, fail

moodle_app = typer.Typer(help="Operaciones sobre un sitio Moodle (servicio web).")


@moodle_app.callback()
def moodle(llm: bool = LLM_OPTION):
    """Operaciones sobre un sitio Moodle (servicio web)."""


@moodle_app.command(name="subir")
def subir(
    rutas: List[Path] = typer.Argument(..., exists=True, help="Archivos .gift/.xml o directorios (las carpetas son categorías)."),
    url: str = typer.Option(..., "--url", envvar="MOODLE_URL", help="URL del sitio Moodle (o MOODLE_URL)."),
    curso: int = typer.Option(..., "--curso", "--course", help="id del curso destino (conviene uno de prueba para probar la importación)."),
    token: str = typer.Option(None, "--token", help="Token del servicio web (o MOODLE_TOKEN, también en ~/.voight/.env)."),
    recursive: bool = typer.Option(True, "-r/--no-recursive", help="Recorrer los subdirectorios."),
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="Preparar el XML y mostrar qué se subiría, sin contactar a Moodle."),
    guardar: Path = typer.Option(None, "--guardar", "--save", help="Guardar también el Moodle XML que se sube."),
    output_json: bool = typer.Option(False, "--json", help="Emite el resultado como JSON versionado."),
):
    """Sube preguntas a un curso de Moodle (requiere el plugin local_questions_importer_ws).

    Convierte y unifica GIFT/XML en un Moodle XML, lo sube al área de borradores con
    webservice/upload.php y lo importa con local_questions_importer_ws_import_xml.
    """
    from voight.core.moodle_ws import importar, preparar_xml, resolver_token, subir_borrador
    from voight.core.moodle_xml import parse_xml

    try:
        nombre, contenido, cantidad = preparar_xml(rutas, recursive)
    except ValueError as e:
        fail(str(e))
    preguntas = [q for q in parse_xml(contenido.decode("utf-8")).get("questions", []) if q["type"] != "Category"]
    if guardar:
        guardar.write_bytes(contenido)
    if dry_run:
        click.echo(f"🧪 Se subirían {len(preguntas)} preguntas de {cantidad} archivos ({len(contenido)} bytes) "
                   f"al curso {curso} de {url}.")
        return
    token = resolver_token(token)
    if not token:
        fail("Falta el token del servicio web: --token, MOODLE_TOKEN o `voight config set-moodle-token`.")
    try:
        itemid = subir_borrador(url, token, nombre, contenido)
        respuesta = importar(url, token, curso, itemid)
    except RuntimeError as e:
        fail(str(e))
    if output_json:
        emitir_json("moodle subir", {"curso": curso, "preguntas": len(preguntas), "archivos": cantidad,
                                     "itemid": itemid, "respuesta": respuesta})
        return
    click.echo(f"✓ {len(preguntas)} preguntas importadas en el curso {curso} (borrador {itemid}).")
    if respuesta not in (None, {}, []):
        click.echo(f"  Moodle respondió: {respuesta}")
