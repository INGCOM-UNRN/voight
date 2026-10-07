from pathlib import Path
from typing import List, Optional

import click
import typer

from voight.core.ai import PROVEEDORES, cargar_cliente, modelo_por_defecto, run_global_ai_processing
from voight.core.config import get_proveedor
from voight.core.banco import expandir_rutas
from voight.commands.common import LLM_OPTION, con_configuracion, fail


def ai(
    ctx: typer.Context,
    inputs: Optional[List[Path]] = typer.Argument(None, exists=True, help="Archivos .gift/.xml o directorios."),
    llm: bool = LLM_OPTION,
    mode: str = typer.Option(
        "improve", "--mode",
        click_type=click.Choice(["improve", "multiply", "transform", "feedback", "distractors", "classify"]),
        help="Modo: improve (mejorar), multiply (variaciones), transform (usar prompt personalizado), "
             "feedback (completar sólo la retroalimentación que falta), distractors (agregar distractores donde "
             "faltan o la correcta delata por su largo) o classify (Bloom y dificultad con Jev).",
    ),
    prompt: Optional[str] = typer.Option(None, "--prompt", help="Prompt personalizado o ruta a un archivo .txt con el prompt."),
    output: Optional[Path] = typer.Option(None, "--output", help="Directorio de salida (por defecto: output_<mode>)."),
    proveedor: Optional[str] = typer.Option(
        None, "--proveedor", "--provider", click_type=click.Choice(PROVEEDORES),
        help="Modelo de lenguaje para improve/multiply/transform/feedback/distractors: gemini o claude "
             "(por defecto: VOIGHT_PROVEEDOR o gemini)."),
    model: Optional[str] = typer.Option(
        None, "--model", help="Modelo (por defecto: gemini configurado o gemini-2.0-flash; claude-opus-5 con claude)."),
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Procesar subdirectorios recursivamente."),
    batch_size: int = typer.Option(5, "--batch-size", help="Número de preguntas por petición a la API (default: 5)."),
    in_place: bool = typer.Option(False, "-i", "--in-place", help="Escribir en la misma carpeta que el original."),
    suffix: Optional[str] = typer.Option(None, "--suffix", help="Sufijo para los nuevos archivos (usado con --in-place, ej: -ia)."),
    contexto: Optional[str] = typer.Option(
        None, "--contexto", "--context", help="classify: curso y nivel de los estudiantes (calibra Bloom y dificultad)."),
    concurrencia: int = typer.Option(4, "--concurrencia", "--concurrency", help="classify: solicitudes simultáneas a Jev."),
    reclasificar: bool = typer.Option(False, "--reclasificar", "--reclassify", help="classify: volver a clasificar las ya clasificadas."),
    tags: bool = typer.Option(False, "--tags", help="classify: escribir también tags de Moodle (bloom:…, dificultad-…)."),
    calibrar: Optional[Path] = typer.Option(
        None, "--calibrar", "--calibrate", exists=True,
        help="classify: comparar con una referencia CSV (archivo,titulo,bloom[,dificultad_enunciado,…]) sin escribir nada."),
    revisar: bool = typer.Option(
        False, "--revisar", "--review",
        help="classify: revisar en una interfaz de terminal las clasificaciones con poca confianza (extra 'tui')."),
    umbral_revision: float = typer.Option(
        0.6, "--umbral-revision", "--review-threshold", min=0.0, max=1.0,
        help="classify --revisar: confianza por debajo de la cual se pide revisar (con 1, todas las clasificadas)."),
    referencias: Optional[Path] = typer.Option(
        None, "--referencias", "--references",
        help="classify --revisar: CSV de calibración al que se agregan las correcciones (el formato de --calibrar)."),
    opciones: int = typer.Option(4, "--opciones", "--options", help="distractors: cantidad de opciones a alcanzar por pregunta."),
    precio_entrada: Optional[float] = typer.Option(
        None, "--precio-entrada", "--input-price", help="USD por millón de tokens de entrada, para estimar el costo."),
    precio_salida: Optional[float] = typer.Option(
        None, "--precio-salida", "--output-price", help="USD por millón de tokens de salida, para estimar el costo."),
    sin_cache: bool = typer.Option(
        False, "--sin-cache", "--no-cache", help="No usar ni guardar respuestas en la caché (~/.cache/voight)."),
    dry_run: bool = typer.Option(
        False, "-n", "--dry-run",
        help="Mostrar lo que se enviaría (y cuánto se ahorra) sin llamar al modelo ni escribir archivos.",
    ),
):
    """Procesamiento de preguntas GIFT y Moodle XML usando IA (Gemini).

    El modelo recibe GIFT compacto (sin comentarios, categorías ni marcas · y ↵ en el
    código); las preguntas XML se convierten a GIFT y la respuesta se aplica sobre el
    XML original, que conserva sus metadatos.

    --mode classify usa Jev (TypeSafe) para agregar a cada pregunta un comentario con su
    nivel de Bloom y la dificultad (1–5) del enunciado y de las respuestas.
    """
    if not inputs:
        fail("Debes proporcionar al menos una ruta de entrada.")

    opciones = con_configuracion(ctx, inputs, "ai", {
        "contexto": contexto, "proveedor": proveedor, "model": (model, "modelo"), "opciones": opciones})
    contexto, proveedor, model, opciones = (
        opciones["contexto"], opciones["proveedor"], opciones["model"], opciones["opciones"])
    proveedor = (proveedor or get_proveedor()).lower()
    if proveedor not in PROVEEDORES:
        fail(f"Proveedor desconocido: {proveedor} (gemini o claude).")
    active_model = model or modelo_por_defecto(proveedor)

    # Resolver prompt desde archivo si es necesario
    custom_prompt = prompt
    if custom_prompt and Path(custom_prompt).is_file():
        try:
            custom_prompt = Path(custom_prompt).read_text(encoding='utf-8').strip()
        except Exception as e:
            fail(f"Error al leer el archivo de prompt: {e}")

    # Si se provee prompt y no hay modo explícito de transform o multiply, usar transform
    if prompt and mode == 'improve':
        mode = 'transform'

    from voight.core import ai as ai_core

    ai_core.OPCIONES_OBJETIVO[0] = opciones
    file_paths = expandir_rutas(inputs, recursive)
    if not file_paths:
        fail("No se encontraron archivos .gift o .xml para procesar.")

    if mode == "classify" and revisar:
        _revisar_clasificacion(file_paths, umbral_revision, tags, referencias)
        return

    if mode == "classify" and calibrar is not None:
        from voight.core.cache import Cache
        from voight.core.clasificacion import CONTEXTO, ClienteJev, describir_calibracion, leer_referencias
        from voight.core.clasificacion import calibrar as calibrar_jev

        try:
            cliente = ClienteJev(cache=Cache("jev", activa=not sin_cache))
        except ValueError as e:
            fail(str(e))
        referencias = leer_referencias(calibrar)
        if not referencias:
            fail(f"{calibrar} no tiene filas con un nivel de Bloom válido.")
        click.echo(describir_calibracion(calibrar_jev(referencias, cliente, contexto or CONTEXTO, concurrencia)))
        return

    if mode == "classify":
        from voight.core.clasificacion import CONTEXTO, ClienteJev, run_clasificacion

        cliente = None
        if not dry_run:
            try:
                from voight.core.cache import Cache

                cliente = ClienteJev(cache=Cache("jev", activa=not sin_cache))
            except ValueError as e:
                fail(str(e))
        output_dir = None
        if not in_place and not dry_run:
            output_dir = Path(output) if output else Path("output_classify")
            output_dir.mkdir(parents=True, exist_ok=True)
        run_clasificacion(
            file_paths, output_dir, in_place=in_place, suffix=suffix, contexto=contexto or CONTEXTO,
            concurrencia=concurrencia, reclasificar=reclasificar, tags=tags, dry_run=dry_run, cliente=cliente,
        )
        return

    client = None
    if not dry_run:
        try:
            client = cargar_cliente(proveedor)
        except Exception as e:
            fail(str(e))

    output_dir = None
    if not in_place and not dry_run:
        output_dir = Path(output) if output else Path(f"output_{mode}")
        output_dir.mkdir(parents=True, exist_ok=True)

    run_global_ai_processing(
        client=client,
        model_id=active_model,
        file_paths=file_paths,
        output_dir=output_dir,
        mode=mode,
        custom_prompt=custom_prompt,
        batch_size=batch_size,
        in_place=in_place,
        suffix=suffix,
        dry_run=dry_run,
        usar_cache=not sin_cache,
        precio_entrada=precio_entrada,
        precio_salida=precio_salida,
    )


def _revisar_clasificacion(rutas: List[Path], umbral: float, tags: bool, referencias: Optional[Path]) -> None:
    import contextlib
    import io

    from voight.core.lector import leer_archivos, unidades_de
    from voight.core.clasificacion import para_revisar

    try:
        from voight.tui.clasificacion import ClasificacionApp
    except ImportError:
        fail('La interfaz de terminal requiere el extra opcional \'tui\': '
             'uv tool install "voight[tui] @ git+https://github.com/INGCOM-UNRN/voight"')
    with contextlib.redirect_stdout(io.StringIO()):
        archivos = leer_archivos(rutas)
    unidades = para_revisar(unidades_de(archivos), umbral, todas=umbral >= 1.0)
    if not unidades:
        click.echo(f"No hay preguntas clasificadas con confianza menor que {umbral:g} (sin contar las corregidas a mano).")
        return
    resultado = ClasificacionApp(archivos, unidades, tags, referencias).run()
    if not resultado:
        click.echo("No se guardó nada.")
        return
    click.echo(f"✓ {resultado['correcciones']} correcciones guardadas en {len(resultado['archivos'])} archivos.")
    if referencias is not None:
        click.echo(f"  {resultado['referencias']} filas en {referencias} (usalas con --calibrar).")
