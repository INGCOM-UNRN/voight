from pathlib import Path
from typing import List, Optional

import click
import typer

from voight.core.validator import AnalizadorBanco

import contextlib
import io

from voight.commands.common import LLM_OPTION, emitir_json

analyze_app = typer.Typer(help="Análisis y estadísticas de preguntas.")


@analyze_app.callback()
def analyze(llm: bool = LLM_OPTION):
    """Análisis y estadísticas de preguntas."""


@analyze_app.command(name="stats")
def stats(
    paths: Optional[List[str]] = typer.Argument(None, exists=True),
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Buscar recursivamente"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Archivo de salida para el informe"),
    output_json: bool = typer.Option(False, "--json", help="Emite las estadísticas como JSON versionado"),
):
    """Genera estadísticas de un repositorio de preguntas (GIFT y Moodle XML).

    Sale con código 1 si algún archivo no se puede interpretar.
    """
    if not paths:
        paths = ['.']
        
    analyzer = AnalizadorBanco(recursive=recursive)
    with contextlib.redirect_stdout(io.StringIO()) if output_json else contextlib.nullcontext():
        for p in paths:
            path_obj = Path(p)
            if path_obj.is_dir():
                analyzer.scan_directory(str(path_obj))
            else:
                analyzer.analyze_file(path_obj)

        analyzer.find_duplicates()
    if output_json:
        emitir_json("analyze stats", analyzer.to_json())
    else:
        report = analyzer.generate_report(output)
        if not output:
            click.echo(report)
    if analyzer.stats.invalid_files:
        raise typer.Exit(code=1)

@analyze_app.command(name="similar")
def similar(
    paths: Optional[List[str]] = typer.Argument(None, exists=True),
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Buscar recursivamente"),
    similarity: float = typer.Option(0.85, "-s", "--similarity", help="Threshold de similitud"),
    output_json: bool = typer.Option(False, "--json", help="Emite los pares similares como JSON versionado"),
):
    """Encuentra preguntas similares o duplicadas en un repositorio (GIFT y Moodle XML, también entre formatos).

    Sale con código 1 si encuentra pares por encima del umbral.
    """
    if not paths:
        paths = ['.']
        
    analyzer = AnalizadorBanco(similarity_threshold=similarity, recursive=recursive)
    with contextlib.redirect_stdout(io.StringIO()) if output_json else contextlib.nullcontext():
        for p in paths:
            path_obj = Path(p)
            if path_obj.is_dir():
                analyzer.scan_directory(str(path_obj))
            else:
                analyzer.analyze_file(path_obj)

        analyzer.find_duplicates()

    if output_json:
        emitir_json("analyze similar", {"umbral": similarity, "pares": analyzer.to_json()["duplicates"]})
        if analyzer.duplicates:
            raise typer.Exit(code=1)
        return

    if analyzer.duplicates:
        click.echo(f"Se encontraron {len(analyzer.duplicates)} pares de preguntas similares:")
        for dup in analyzer.duplicates:
            q1 = analyzer.all_questions[dup["index1"]]
            q2 = analyzer.all_questions[dup["index2"]]
            click.echo(f"- Similitud {dup['similarity']:.3f}:")
            click.echo(f"  A: {q1['filepath']} - {q1['title']}")
            click.echo(f"  B: {q2['filepath']} - {q2['title']}")
        raise typer.Exit(code=1)
    click.echo("No se encontraron duplicados significativos.")
