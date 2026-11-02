"""Comandos que hablan con un sitio Moodle."""

from pathlib import Path
from typing import List, Optional

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
        fail("Falta el token del servicio web: --token, MOODLE_TOKEN o `voight config set moodle-token`.")
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
    output_file: Optional[Path] = typer.Option(None, "-o", "--output", help="Archivo .mbz de salida (obligatorio salvo con --plan)."),
    titulo: str = typer.Option("Cuestionario", "-t", "--titulo", "--title", help="Título o nombre del cuestionario."),
    plan: bool = typer.Option(False, "--plan", help="Revisar cupos y configuración sin generar ningún MBZ."),
    preguntas_por_categoria: int = typer.Option(
        1, "-k", "--preguntas-por-categoria", min=1, help="Cantidad de preguntas aleatorias a extraer por cada categoría."
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
    from voight.core.quiz_plan import planificar_quiz

    if not rutas:
        rutas = [Path(".")]

    if plan:
        try:
            resumen = planificar_quiz(rutas, preguntas_por_categoria, recursivo, titulo=titulo,
                                     tiempo_limite=tiempo_limite, calificacion_maxima=calificacion_maxima,
                                     intentos=intentos, shuffle_respuestas=shuffle_respuestas)
        except (ValueError, OSError) as exc:
            fail(str(exc))
        if output_json:
            emitir_json("moodle backup-quiz plan", resumen)
        else:
            click.echo(f"Plan: {resumen['titulo']} · {resumen['preguntas']} preguntas · {resumen['slots']} slots")
            click.echo(f"Tiempo: {tiempo_limite}s · Intentos: {intentos} · Nota máxima: {calificacion_maxima} · Barajar: {shuffle_respuestas}")
            for cupo in resumen["cupos"]:
                click.echo(f"  {cupo['categoria']}: {cupo['disponibles']} disponibles / "
                           f"{cupo['solicitadas']} solicitadas / {cupo['faltantes']} faltantes")
            for error in resumen["errores"]:
                click.echo(f"  Error: {error}")
        if not resumen["ok"]:
            raise typer.Exit(code=1)
        return
    if output_file is None:
        raise typer.BadParameter("indicá -o/--output para generar el MBZ, o usá --plan")

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



def _limite(valor, unidad=""):
    if valor is None:
        return "sin dato"
    return f"{valor}{unidad}" if valor else "sin límite"



@moodle_app.command(name="inspeccionar")
def inspeccionar(
    archivo: Path = typer.Argument(..., exists=True, dir_okay=False, help="Copia .mbz (tar o ZIP)."),
    output_json: bool = typer.Option(False, "--json", help="Resumen como JSON versionado."),
):
    """Inspecciona preguntas, categorías, cupos y configuración sin extraer ni restaurar."""
    from voight.core.mbz_inspector import inspeccionar_mbz

    try:
        resumen = inspeccionar_mbz(archivo)
    except ValueError as exc:
        fail(str(exc))
    if output_json:
        emitir_json("moodle inspeccionar", resumen)
        return
    click.echo(f"MBZ: {archivo.name} · Moodle {resumen['moodle_release'] or 'sin versión declarada'}")
    click.echo(f"Banco: {resumen['preguntas']} preguntas / {resumen['versiones']} versiones / "
               f"{len(resumen['categorias'])} categorías")
    for categoria in resumen["categorias"]:
        click.echo(f"  {categoria['nombre']}: {categoria['preguntas']} preguntas {categoria['tipos']}")
    for quiz in resumen["cuestionarios"]:
        click.echo(f"Cuestionario: {quiz['titulo']} · {quiz['slots']} slots "
                   f"({quiz['aleatorios']} aleatorios, {quiz['fijos']} fijos)")
        click.echo(f"  Tiempo: {_limite(quiz['tiempo_limite'], 's')} · Intentos: {_limite(quiz['intentos'])} · "
                   f"Nota máxima: {quiz['calificacion_maxima'] if quiz['calificacion_maxima'] is not None else 'sin dato'} · "
                   f"Barajar: {('sí' if quiz['shuffle_respuestas'] else 'no') if quiz['shuffle_respuestas'] is not None else 'sin dato'}")
        for cupo in quiz["cupos"]:
            nombres = ", ".join(c['nombre'] or f"id={c['id']}" for c in cupo["categorias"])
            click.echo(f"  Cupo: {cupo['slots']} slots sobre [{nombres or 'sin filtro de categoría'}]")
            filtros = cupo["filtro"].get("filter", {})
            subcategorias = filtros.get("category", {}).get("filteroptions", {}).get("includesubcategories")
            click.echo(f"    Incluir subcategorías: {subcategorias if subcategorias is not None else 'sin dato'}")
            otros = {clave: valor for clave, valor in filtros.items() if clave != "category"}
            if otros:
                import json
                click.echo(f"    Otros filtros: {json.dumps(otros, ensure_ascii=False, sort_keys=True)}")
    for aviso in resumen["avisos"]:
        click.echo(f"Aviso: {aviso}")
