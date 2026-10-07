import json
from pathlib import Path
from typing import List, Optional

import click
import typer

from voight.commands.common import LLM_OPTION, fail


def spellcheck(
    paths: Optional[List[Path]] = typer.Argument(None, exists=True),
    llm: bool = LLM_OPTION,
    server: Optional[str] = typer.Option(None, "-s", "--server", help="URL del servidor LanguageTool (por defecto http://localhost:8081 y API pública)"),
    username: Optional[str] = typer.Option(None, "-u", "--username", help="Usuario / email de LanguageTool Premium"),
    api_key: Optional[str] = typer.Option(None, "-k", "--api-key", help="API Key / Token de LanguageTool Premium"),
    premium: bool = typer.Option(False, "--premium", help="Forzar uso de la API LanguageTool Premium"),
    lang: str = typer.Option("es-AR", "-l", "--lang", help="Código de idioma (default: es-AR)"),
    ignore_rules: Optional[str] = typer.Option(None, "--ignore-rules", help="Reglas a ignorar separadas por comas"),
    ignore_words: Optional[str] = typer.Option(None, "--ignore-words", help="Palabras a ignorar separadas por comas"),
    fix: bool = typer.Option(False, "-f", "--fix", help="Aplica correcciones ortográficas automáticas"),
    output_md: Optional[Path] = typer.Option(None, "--md", "--output-md", help="Genera reporte Markdown"),
    output_json: bool = typer.Option(False, "--json", help="Emite salida estructurada en formato JSON"),
):
    """Verifica y corrige ortografía y gramática en bancos GIFT y XML usando LanguageTool."""
    # Import diferido: sin el extra `languagetool` el resto del CLI funciona (N-MOODLE-01).
    try:
        from voight.core.languagetool_checker import (
            analizar_archivo_banco,
            aplicar_autofix_archivo_banco,
            generar_reporte_markdown_languagetool,
        )
    except ModuleNotFoundError as error:
        fail(str(error))
    if not paths:
        paths = ['.']

    archivos_a_revisar = []
    for p in paths:
        path_obj = Path(p)
        if path_obj.is_file() and path_obj.suffix.lower() in ('.gift', '.xml', '.txt'):
            archivos_a_revisar.append(path_obj)
        elif path_obj.is_dir():
            archivos_a_revisar.extend(sorted(path_obj.glob('**/*.gift')))
            archivos_a_revisar.extend(sorted(path_obj.glob('**/*.xml')))

    if not archivos_a_revisar:
        click.echo("No se encontraron archivos de preguntas (.gift / .xml) para analizar.")
        return

    reglas_ign = set(r.strip() for r in ignore_rules.split(",") if r.strip()) if ignore_rules else None
    palabras_ign = set(w.strip() for w in ignore_words.split(",") if w.strip()) if ignore_words else None

    todos_los_issues = []
    total_arreglos = 0

    for arch in archivos_a_revisar:
        issues = analizar_archivo_banco(
            arch,
            lang=lang,
            server_url=server,
            username=username,
            api_key=api_key,
            premium=premium,
            ignore_words=palabras_ign,
            ignore_rules=reglas_ign,
        )
        if fix and issues:
            total_arreglos += aplicar_autofix_archivo_banco(arch, issues)
        todos_los_issues.extend(issues)

    if output_md:
        md_text = generar_reporte_markdown_languagetool(todos_los_issues)
        out_p = Path(output_md)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(md_text, encoding='utf-8')
        click.echo(f"✓ Reporte Markdown generado en: {out_p}")
        if todos_los_issues:
            raise typer.Exit(1)
        return

    if output_json:
        res = {
            "total_archivos": len(archivos_a_revisar),
            "total_issues": len(todos_los_issues),
            "total_arreglos": total_arreglos,
            "issues": [i.to_dict() for i in todos_los_issues],
        }
        click.echo(json.dumps(res, indent=2, ensure_ascii=False))
        if todos_los_issues:
            raise typer.Exit(1)
        return

    if not todos_los_issues:
        click.echo(f"✅ LanguageTool Passed: {len(archivos_a_revisar)} archivos sin faltas ortográficas.")
        return

    click.echo(f"\n⚠️  Observaciones de LanguageTool ({len(todos_los_issues)} encontradas):")
    for iss in todos_los_issues:
        sug = ", ".join(iss.replacements[:2]) if iss.replacements else "—"
        click.echo(f"  - [{iss.file_path.name}] {iss.line}:{iss.column} | {iss.original_word} ({iss.context}) -> {sug}")

    if fix:
        click.echo(f"\n✓ Se aplicaron {total_arreglos} correcciones en los archivos.")

    raise typer.Exit(1)
