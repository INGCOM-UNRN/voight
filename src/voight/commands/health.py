"""Comando de auditoría de salud e higiene de bancos Moodle (GIFT y XML)."""

from pathlib import Path
from typing import List, Optional

import click
import typer

from voight.commands.common import con_configuracion, emitir_json, fail

from voight.core.banco import expandir_rutas, filtrar_desde, formato_de
from voight.core.moodle_health import (
    MIN_OPCIONES,
    UMBRAL_LONGITUD,
    auditar_archivos,
    escribir_csv,
    generar_reporte_markdown,
    limpiar_html_archivo,
)


def health_cmd(
    ctx: typer.Context,
    rutas: List[Path] = typer.Argument(..., exists=True, help="Archivos .gift/.xml o directorios."),
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Buscar recursivamente en los directorios."),
    output_md: Optional[Path] = typer.Option(
        None, "--md", help="Exportar reporte en Markdown."
    ),
    clean_html: bool = typer.Option(
        False, "--clean-html", help="Limpiar etiquetas HTML obsoletas y estilos inline (GIFT y XML)."
    ),
    min_opciones: int = typer.Option(
        MIN_OPCIONES, "--min-opciones", "--min-options", help="Mínimo de opciones esperado en opción múltiple."
    ),
    umbral_longitud: float = typer.Option(
        UMBRAL_LONGITUD, "--umbral-longitud", "--length-threshold",
        help="Razón de largo correcta/distractores a partir de la cual se advierte.",
    ),
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="Con --clean-html: mostrar qué se limpiaría sin escribir."),
    max_items: int = typer.Option(50, "--max-items", help="Máximo de preguntas listadas por sección (0: todas)."),
    estricto: bool = typer.Option(False, "--estricto", "--strict", help="Salir con código 1 también ante advertencias."),
    output_csv: Optional[Path] = typer.Option(
        None, "--csv", help="Exportar una fila por pregunta con todas las señales (para planillas)."),
    desde: Optional[str] = typer.Option(
        None, "--desde", "--since", help="Sólo los archivos cambiados desde esta revisión git (y los nuevos sin seguimiento)."),
    tui: bool = typer.Option(False, "--tui", help="Recorrer los hallazgos y aplicar los arreglos en una interfaz de terminal (extra 'tui')."),
    output_json: bool = typer.Option(False, "--json", help="Emite el diagnóstico como JSON versionado."),
):
    """Audita la salud del banco: claves de corrección, feedback, cantidad y longitud de opciones, código y enlaces.

    Sale con código 1 si hay errores (lo que Moodle no importaría o importaría mal);
    con --estricto, también si hay advertencias.
    """
    opciones = con_configuracion(ctx, rutas, "health", {
        "min_opciones": min_opciones, "umbral_longitud": umbral_longitud, "max_items": max_items})
    min_opciones, umbral_longitud, max_items = (
        opciones["min_opciones"], opciones["umbral_longitud"], opciones["max_items"])
    archivos = expandir_rutas(rutas, recursive)
    archivos = [a for a in archivos if formato_de(a)]
    if desde:
        try:
            archivos = filtrar_desde(archivos, desde, rutas)
        except ValueError as e:
            fail(str(e))
        if not archivos:
            click.echo(f"No hay archivos de preguntas cambiados desde {desde}.")
            return
    if not archivos:
        sugerencia = ""
        if not recursive and any(r.is_dir() and expandir_rutas([r], True) for r in rutas):
            sugerencia = " Hay preguntas en subdirectorios: usá -r para recorrerlos."
        fail(f"No se encontraron archivos de preguntas (.gift / .xml).{sugerencia}")

    if clean_html:
        for archivo in archivos:
            contenido = archivo.read_text(encoding="utf-8", errors="replace")
            limpio = limpiar_html_archivo(contenido, formato_de(archivo))
            if limpio != contenido:
                if not dry_run:
                    archivo.write_text(limpio, encoding="utf-8")
                if not output_json:
                    click.echo(f"{'[SIMULACIÓN] ' if dry_run else '✓ '}HTML obsoleto y estilos inline: {archivo}")

    if tui:
        try:
            from voight.tui.health import HealthApp
        except ImportError:
            fail('La interfaz de terminal requiere el extra opcional \'tui\': '
                 'uv tool install "voight[tui] @ git+https://github.com/INGCOM-UNRN/voight"')

        def auditar():
            vigentes = [a for a in archivos if a.exists()]
            return auditar_archivos(vigentes, min_opciones=min_opciones, umbral_longitud=umbral_longitud)

        arreglados = HealthApp(auditar).run() or {}
        total = sum(len(v) for v in arreglados.values())
        click.echo(f"{total} archivos arreglados." if total else "No se arregló nada.")
        for clave, rutas in arreglados.items():
            for ruta in rutas:
                click.echo(f"  ✓ {clave}: {ruta}")
        return

    from voight.core.progreso import barra

    with barra(len(archivos), "Auditando") as avance:
        resultado = auditar_archivos(archivos, min_opciones=min_opciones, umbral_longitud=umbral_longitud,
                                     con_preguntas=output_csv is not None, avance=avance)
    if output_csv is not None:
        filas = escribir_csv(resultado.pop("_preguntas"), output_csv)
        if not output_json:
            click.echo(f"✓ {filas} preguntas exportadas a {output_csv}")

    if output_json:
        if output_md:
            # Con --json y --md juntos se escriben ambos (p. ej. la acción de GitHub).
            nombre_md = rutas[0].name if len(rutas) == 1 else f"{len(archivos)} archivos"
            output_md.parent.mkdir(parents=True, exist_ok=True)
            output_md.write_text(generar_reporte_markdown(resultado, nombre_md, max_items=max_items), encoding="utf-8")
        datos = {}
        if len(rutas) == 1 and rutas[0].is_file():
            datos["archivo"] = str(rutas[0])
        datos.update(resultado)
        datos["ok"] = resultado["resumen"]["ok"]
        emitir_json("health", datos)
        _salir(resultado, estricto)
        return

    nombre = rutas[0].name if len(rutas) == 1 else f"{len(archivos)} archivos"
    reporte = generar_reporte_markdown(resultado, nombre, max_items=max_items)

    if output_md:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(reporte, encoding="utf-8")
        click.echo(f"✓ Reporte Markdown exportado en: {output_md}")
        resumen = resultado["resumen"]
        click.echo(f"{'✅' if resumen['ok'] else '❌'} {resumen['total_errores']} errores · "
                   f"{resumen['total_advertencias']} advertencias")
    else:
        click.echo(reporte)
    _salir(resultado, estricto)


def _salir(resultado: dict, estricto: bool) -> None:
    resumen = resultado["resumen"]
    if not resumen["ok"] or (estricto and resumen["advertencias"]):
        raise typer.Exit(code=1)
