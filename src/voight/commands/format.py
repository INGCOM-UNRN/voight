import difflib
from pathlib import Path
from typing import List, Optional

import click
import typer

from voight.core.banco import expandir_rutas, filtrar_desde, formato_de
from voight.core.codigo import aislar_guardas_archivo, transformar_archivo
from voight.core.formatter import format_content

from voight.commands.common import LLM_OPTION, con_configuracion, emitir_json, fail


def format_cmd(
    ctx: typer.Context,
    paths: Optional[List[Path]] = typer.Argument(None, exists=True),
    llm: bool = LLM_OPTION,
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Procesar recursivamente"),
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="No aplicar cambios"),
    code: bool = typer.Option(False, "--code", help="Marcar la indentación del código con · (un punto por espacio)"),
    fullwidth: bool = typer.Option(
        False, "--fullwidth",
        help="Proteger el código: símbolos fullwidth y marcas · (indentación) y ↵ (fin de línea)",
    ),
    normal: bool = typer.Option(False, "--normal", help="Restaurar el código a caracteres normales (sin marcas)"),
    marcas: bool = typer.Option(
        True, "--marcas/--sin-marcas", "--marks/--no-marks", help="Con --fullwidth, agregar las marcas · y ↵ (por defecto, sí)."
    ),
    gaff: bool = typer.Option(
        False, "--gaff",
        help="Formatear el código C de los bloques ``` con gaff (estilo de la cátedra): restaura los caracteres "
             "normales, aplica `gaff fix` y vuelve a proteger el código como estaba.",
    ),
    correct_first: bool = typer.Option(
        False, "--correct-first", help="Ordena las opciones de opción múltiple por porcentaje (la correcta primero)."
    ),
    check: bool = typer.Option(
        False, "--check", help="No escribir: salir con código 1 si algún archivo cambiaría (para CI y pre-commit)."
    ),
    diff: bool = typer.Option(False, "--diff", help="No escribir: mostrar los cambios como diff unificado."),
    desde: Optional[str] = typer.Option(
        None, "--desde", "--since", help="Sólo los archivos cambiados desde esta revisión git (y los nuevos sin seguimiento)."),
    output_json: bool = typer.Option(False, "--json", help="Emite el resultado (archivos que cambian y errores) como JSON versionado."),
):
    """Formatea archivos GIFT y Moodle XML y transforma el código (fullwidth, · y ↵).

    Con --check o --diff no escribe nada; --check sale con código 1 si algún archivo
    cambiaría (también si algún archivo no se pudo procesar).
    """
    if fullwidth and normal:
        fail("--fullwidth y --normal son excluyentes.")
    comando_gaff = None
    if gaff:
        from voight.core.formato_codigo import comando_gaff as buscar_gaff

        comando_gaff = buscar_gaff()
        if comando_gaff is None:
            fail("--gaff necesita gaff instalado (uv tool install git+https://github.com/INGCOM-UNRN-P1/gaff).")
    opciones = con_configuracion(ctx, paths, "format", {
        "fullwidth": fullwidth, "marcas": marcas, "correct_first": correct_first})
    # --normal explícito gana sobre fullwidth = true del .questions.toml.
    fullwidth = bool(opciones["fullwidth"]) and not normal
    marcas, correct_first = opciones["marcas"], opciones["correct_first"]
    if not paths:
        paths = [Path('.')]

    transforma_codigo = code or fullwidth or normal
    extensiones = (".gift", ".xml", ".md") if transforma_codigo else (".gift", ".xml")
    files = expandir_rutas(paths, recursive, extensiones)
    if desde:
        try:
            files = filtrar_desde(files, desde, paths)
        except ValueError as e:
            fail(str(e))

    if not files:
        if output_json:
            emitir_json("format", {"modo": _modo(check, diff, dry_run), "archivos": 0, "cambian": [], "errores": []})
        else:
            click.echo("No se encontraron archivos para procesar.")
        return

    modified_count = 0
    errores = 0
    cambian, fallidos = [], []
    # Con --json no se imprime nada más (salvo el diff, que con --json no se emite).
    echo = (lambda *a, **k: None) if output_json else click.echo

    for f in sorted(files):
        try:
            content = f.read_text(encoding='utf-8')
            formato = formato_de(f) or "md"
            modified = content

            # 0. XML: cada guarda ``` sola en su línea, antes de transformar el código (con
            #    texto pegado a la apertura, «```c int x;» se tomaría como etiqueta).
            if formato == "xml":
                modified, _ = aislar_guardas_archivo(modified)

            # 0b. --gaff: el código C de cada bloque se restaura, se formatea con gaff y se
            #     vuelve a proteger con la convención que tenía.
            if comando_gaff and formato in ("gift", "xml"):
                from voight.core.formato_codigo import formatear_archivo_gaff

                modified, _ = formatear_archivo_gaff(modified, formato, comando_gaff)

            # 1. Código: fullwidth/normal y marcas (antes del formato: en GIFT, el código
            #    protegido ya no confunde la detección del bloque de respuestas).
            if fullwidth:
                modified, _ = transformar_archivo(modified, formato, fullwidth=True, espacios=marcas, saltos=marcas)
            elif normal:
                modified, _ = transformar_archivo(modified, formato, fullwidth=False)
            if code:
                modified, _ = transformar_archivo(modified, formato, fullwidth=None, espacios=True, saltos=False)

            # 2. Formato estándar (GIFT y XML)
            if formato in ("gift", "xml"):
                modified = format_content(modified, formato, correct_first=correct_first)

            if content != modified:
                cambian.append(str(f))
                if diff and not output_json:
                    click.echo("".join(difflib.unified_diff(
                        content.splitlines(keepends=True), modified.splitlines(keepends=True),
                        fromfile=f"a/{f}", tofile=f"b/{f}")), nl=False)
                elif check or (diff and output_json):
                    echo(f"[CAMBIARÍA] {f}")
                else:
                    if not dry_run:
                        f.write_text(modified, encoding='utf-8')
                    status = "[SIMULACIÓN]" if dry_run else "[MODIFICADO]"
                    echo(f"{status} {f}")
                modified_count += 1
        except Exception as e:
            errores += 1
            fallidos.append({"archivo": str(f), "error": str(e)})
            echo(f"Error procesando {f}: {e}", err=True)

    if output_json:
        emitir_json("format", {"modo": _modo(check, diff, dry_run), "archivos": len(files),
                               "cambian": cambian, "errores": fallidos})
        if check and (modified_count or errores):
            raise typer.Exit(code=1)
        return
    if diff:
        return
    if check:
        if modified_count or errores:
            click.echo(f"\n{modified_count} de {len(files)} archivos no tienen el formato estándar "
                       "(`voight format` los corrige).", err=True)
            raise typer.Exit(code=1)
        click.echo(f"{len(files)} archivos con el formato estándar.")
        return
    click.echo(f"\nResumen: {len(files)} archivos procesados, {modified_count} modificados.")


def _modo(check: bool, diff: bool, dry_run: bool) -> str:
    if check:
        return "check"
    if diff:
        return "diff"
    return "simulacion" if dry_run else "escritura"
