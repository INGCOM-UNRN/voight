from pathlib import Path
from typing import List, Optional

import click
import typer

import contextlib
import io

from voight.core.splitter import split_file
from voight.commands.common import LLM_OPTION, emitir_json, fail


def split(
    paths: Optional[List[Path]] = typer.Argument(None, exists=True),
    llm: bool = LLM_OPTION,
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Procesar recursivamente."),
    output_dir: Optional[Path] = typer.Option(
        None, "-o", "--output-dir",
        help="Exportar a un árbol de carpetas por categoría en este directorio (en lugar de dividir en el lugar)."),
    remove: bool = typer.Option(False, "--remove", help="Borrar el archivo original después de dividirlo."),
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="No crear ni borrar archivos; sólo contar."),
    output_json: bool = typer.Option(False, "--json", help="Emite el resultado como JSON versionado."),
):
    """Divide archivos GIFT o Moodle XML con múltiples preguntas en archivos individuales.

    Sin -o, cada pregunta queda al lado del original. Con -o DIR, el banco se exporta a
    un árbol `DIR/<categoría>/<pregunta>.<ext>` (es la operación inversa a `unify`).
    """
    if not paths:
        paths = ['.']
    if output_dir is not None:
        _exportar(paths, output_dir, recursive, remove, dry_run, output_json)
        return

    files = []
    for p in paths:
        path = Path(p)
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            for extension in ("gift", "xml"):
                pattern = f"**/*.{extension}" if recursive else f"*.{extension}"
                files.extend(list(path.glob(pattern)))

    if not files:
        click.echo("No se encontraron archivos GIFT ni XML.")
        return

    total_new_files = 0
    total_split_files = 0
    
    for f in sorted(files):
        try:
            count = split_file(f, simular=dry_run)
            if count > 0:
                click.echo(f"{'[SIMULACIÓN] ' if dry_run else '✓ '}{f}: dividido en {count} archivos")
                total_new_files += count
                total_split_files += 1
                if remove and not dry_run:
                    f.unlink()
        except Exception as e:
            click.echo(f"Error procesando {f}: {e}", err=True)

    if output_json:
        emitir_json("split", {"archivos": total_split_files, "preguntas": total_new_files, "simulacion": dry_run})
        return
    click.echo(f"\nResumen: {total_split_files} archivos divididos, {total_new_files} nuevos archivos creados.")


def _exportar(paths, output_dir: Path, recursive: bool, remove: bool, dry_run: bool, output_json: bool) -> None:
    """Cada banco a un árbol por categoría en `output_dir` (antes `tree export`)."""
    from voight.core.banco import expandir_rutas
    from voight.core.tree import exportar

    bancos = expandir_rutas(paths, recursive)
    if not bancos:
        fail("No se encontraron archivos GIFT ni XML.")
    if dry_run:
        click.echo(f"[SIMULACIÓN] {len(bancos)} bancos se exportarían a {output_dir}")
        return
    total = 0
    for banco in bancos:
        with contextlib.redirect_stdout(io.StringIO()) if output_json else contextlib.nullcontext():
            cantidad = exportar(banco, output_dir)
        if cantidad < 0:
            fail(f"La exportación de {banco} falló.")
        total += cantidad
        if remove:
            banco.unlink()
    if output_json:
        emitir_json("split", {"preguntas": total, "directorio": str(output_dir)})
        return
    click.echo(f"\nÁrbol generado en: {output_dir}")
