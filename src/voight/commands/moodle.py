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


@moodle_app.command(name="backup-quiz")
def backup_quiz(
    rutas: List[Path] = typer.Argument(None, exists=True, help="Archivos .gift/.xml o directorios del repositorio."),
    output_file: Path = typer.Option(..., "-o", "--output", help="Archivo .mbz de salida para la copia de seguridad."),
    titulo: str = typer.Option("Cuestionario", "-t", "--titulo", "--title", help="Título o nombre del cuestionario."),
    preguntas_por_categoria: int = typer.Option(
        1, "-k", "--preguntas-por-categoria", help="Cantidad de preguntas aleatorias a extraer por cada categoría."
    ),
    recursivo: bool = typer.Option(True, "-r/--no-recursive", help="Recorrer los subdirectorios recursivamente."),
    tiempo_limite: int = typer.Option(3600, "--tiempo-limite", help="Límite de tiempo en segundos (por defecto 3600s = 1 hora)."),
    calificacion_maxima: float = typer.Option(10.0, "--calificacion-maxima", help="Calificación máxima del cuestionario."),
    intentos: int = typer.Option(1, "--intentos", help="Número de intentos permitidos (1 por defecto)."),
    shuffle_respuestas: bool = typer.Option(True, "--shuffle/--no-shuffle", help="Barajar respuestas."),
    output_json: bool = typer.Option(False, "--json", help="Emite el resultado como JSON versionado."),
):
    """Crea un backup de cuestionario (.mbz) con preguntas aleatorias por categoría.

    Unifica las preguntas de la estructura de directorios y genera un paquete MBZ
    (Moodle 2 backup de actividad) listo para restaurar directamente en cualquier
    curso de Moodle sin requerir plugins externos ni web services.
    """
    from voight.core.moodle_backup import generar_quiz_mbz

    if not rutas:
        rutas = [Path(".")]

    try:
        res = generar_quiz_mbz(
            rutas=rutas,
            archivo_salida=output_file,
            titulo=titulo,
            preguntas_por_categoria=preguntas_por_categoria,
            recursivo=recursivo,
            tiempo_limite=tiempo_limite,
            calificacion_maxima=calificacion_maxima,
            intentos=intentos,
            shuffle_respuestas=shuffle_respuestas,
        )
    except Exception as e:
        fail(f"Error generando backup del cuestionario: {e}")

    if output_json:
        emitir_json("moodle backup-quiz", res)
        return

    click.echo(
        f"✓ Backup de cuestionario generado exitosamente en {output_file}:\n"
        f"  - {res['categorias']} categorías encontradas\n"
        f"  - {res['preguntas']} preguntas totales en el banco\n"
        f"  - {res['slots']} slots de preguntas aleatorias configurados en el cuestionario"
    )

