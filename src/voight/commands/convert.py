import click
import typer
from pathlib import Path
from typing import List, Optional
from voight.core.converter import (
    convert_html_tags_to_markdown,
    html_a_markdown_xml,
    xml_to_gift,
    gift_to_xml,
)

from voight.commands.common import LLM_OPTION, fail

convert_app = typer.Typer(help="Comandos para convertir entre formatos.")


@convert_app.callback()
def convert(llm: bool = LLM_OPTION):
    """Comandos para convertir entre formatos."""


@convert_app.command(name="html-to-md")
def html_to_md(
    paths: Optional[List[str]] = typer.Argument(None, exists=True),
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Procesar recursivamente"),
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="No aplicar cambios"),
):
    """Convierte tags HTML a Markdown en archivos XML o GIFT."""
    if not paths:
        paths = ['.']
    
    files = []
    for p in paths:
        path = Path(p)
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            pattern = "**/*" if recursive else "*"
            files.extend([f for f in path.glob(pattern) if f.suffix in ('.xml', '.gift', '.md')])

    modified_count = 0
    for f in files:
        try:
            content = f.read_text(encoding='utf-8')
            # En XML, campo por campo: sólo los que cambian pasan a format="markdown".
            if f.suffix == '.xml':
                modified, _ = html_a_markdown_xml(content)
            else:
                modified = convert_html_tags_to_markdown(content)
            
            if content != modified:
                if not dry_run:
                    f.write_text(modified, encoding='utf-8')
                click.echo(f"{'[SIMULACIÓN] ' if dry_run else '✓ '}{f}")
                modified_count += 1
        except Exception as e:
            click.echo(f"Error en {f}: {e}", err=True)
    
    click.echo(f"\nFinalizado: {modified_count} archivos modificados.")


def _leer_entrada(path: Path | None) -> str:
    if path is None or str(path) == "-":
        import sys
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


@convert_app.command(name="xml-to-gift")
def xml_to_gift_cmd(
    path: Optional[str] = typer.Argument(None),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Archivo GIFT de salida (por defecto, stdout)."),
):
    """Convierte Moodle XML a GIFT (PATH o stdin; '-' para stdin)."""
    contenido = _leer_entrada(Path(path) if path else None)
    try:
        resultado = xml_to_gift(contenido)
    except Exception as e:
        fail(f"No se pudo convertir el XML: {e}")
    if output:
        Path(output).write_text(resultado, encoding="utf-8")
        click.echo(f"✓ GIFT generado: {output}")
    else:
        click.echo(resultado)


@convert_app.command(name="gift-to-xml")
def gift_to_xml_cmd(
    path: Optional[str] = typer.Argument(None),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Archivo XML de salida (por defecto, stdout)."),
):
    """Convierte GIFT a Moodle XML (PATH o stdin; '-' para stdin)."""
    contenido = _leer_entrada(Path(path) if path else None)
    try:
        resultado = gift_to_xml(contenido)
    except Exception as e:
        fail(f"No se pudo convertir el GIFT: {e}")
    if output:
        Path(output).write_text(resultado, encoding="utf-8")
        click.echo(f"✓ XML generado: {output}")
    else:
        click.echo(resultado)
