import contextlib
import io
from pathlib import Path
from typing import List, Optional

import click
import typer

from voight.core.validator import AnalizadorBanco
from voight.core.banco import parse_archivo

from voight.commands.common import LLM_OPTION, fail


def validate(
    paths: Optional[List[Path]] = typer.Argument(None, exists=True),
    llm: bool = LLM_OPTION,
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Archivo de salida para el informe"),
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Buscar recursivamente"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Información detallada"),
    similarity: float = typer.Option(0.85, "-s", "--similarity", help="Threshold para duplicados"),
    output_json: bool = typer.Option(False, "-j", "--json", help="Salida en JSON"),
    desde: Optional[str] = typer.Option(
        None, "--desde", "--since", help="Sólo los archivos cambiados desde esta revisión git (y los nuevos sin seguimiento)."),
):
    """Valida archivos o directorios de preguntas GIFT y Moodle XML.

    Sale con código 1 si algún archivo no se puede interpretar o se detectan problemas
    (preguntas vacías, sin respuesta correcta, archivos sin preguntas…).
    """
    if not paths:
        paths = ['.']
        
    all_results = []
    analyzer = AnalizadorBanco(
        similarity_threshold=similarity,
        recursive=recursive,
        verbose=verbose
    )
    
    files_to_validate = []
    dirs_to_validate = []
    
    for p in paths:
        path_obj = Path(p)
        if path_obj.is_file():
            files_to_validate.append(path_obj)
        else:
            dirs_to_validate.append(path_obj)
    if desde:
        # Los directorios se expanden y quedan sólo los archivos cambiados.
        from voight.core.banco import expandir_rutas, filtrar_desde

        try:
            files_to_validate = filtrar_desde(
                files_to_validate + expandir_rutas(dirs_to_validate, recursive), desde, paths)
        except ValueError as e:
            fail(str(e))
        dirs_to_validate = []

    # Procesar archivos individuales
    for f in files_to_validate:
        analyzer.analyze_file(f)
        result = parse_archivo(f)
        if output_json:
            all_results.append(result)
        else:
            if result["success"]:
                click.echo(f"✅ Archivo válido: {f}")
                click.echo(f"   Preguntas encontradas: {result['questionCount']}")
            else:
                click.echo(f"❌ Archivo inválido: {f}")
                click.echo(f"   Error: {result['error']['message']}")
                
    # Procesar directorios (con --json, el progreso no ensucia la salida)
    with contextlib.redirect_stdout(io.StringIO()) if output_json else contextlib.nullcontext():
        for d in dirs_to_validate:
            analyzer.scan_directory(str(d))
        
    if not output_json:
        if dirs_to_validate or files_to_validate:
            # find_duplicates is called by scan_directory, but if we only have files, 
            # we need to call it explicitly. scan_directory already calls it.
            # To be safe and avoid missing duplicates between files and dirs:
            analyzer.find_duplicates()
            report = analyzer.generate_report(output)
            if not output:
                click.echo(report)
    else:
        import json
        output_data = {
            "files": all_results,
            "directories": analyzer.to_json() if dirs_to_validate else None
        }
        click.echo(json.dumps(output_data, indent=2, ensure_ascii=False))

    if analyzer.stats.invalid_files or analyzer.issues:
        raise typer.Exit(code=1)
