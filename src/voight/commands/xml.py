import click
import typer
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional
from voight.core.xml_tools import ensure_cdata_in_text_blocks, sanitize_filename, remove_tags_from_xml

from voight.commands.common import LLM_OPTION

xml_app = typer.Typer(help="Herramientas para archivos XML de Moodle.")


@xml_app.callback()
def xml_group(llm: bool = LLM_OPTION):
    """Herramientas para archivos XML de Moodle."""


@xml_app.command()
def cdata(
    paths: Optional[List[str]] = typer.Argument(None, exists=True),
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Procesar recursivamente"),
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="No aplicar cambios"),
):
    """Asegura que los bloques <text> usen CDATA."""
    if not paths:
        paths = ['.']
    
    files = []
    for p in paths:
        path = Path(p)
        if path.is_file() and path.suffix == '.xml':
            files.append(path)
        elif path.is_dir():
            pattern = "**/*.xml" if recursive else "*.xml"
            files.extend(list(path.glob(pattern)))

    for f in files:
        content = f.read_text(encoding='utf-8')
        new_content, count = ensure_cdata_in_text_blocks(content)
        if count > 0:
            if not dry_run:
                f.write_text(new_content, encoding='utf-8')
            click.echo(f"{'[SIMULACIÓN] ' if dry_run else '✓ '}{f}: {count} bloques actualizados")

@xml_app.command()
def clean_tags(
    paths: Optional[List[str]] = typer.Argument(None, exists=True),
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Procesar recursivamente"),
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="No aplicar cambios"),
):
    """Elimina tags de las preguntas XML."""
    if not paths:
        paths = ['.']
    
    files = []
    for p in paths:
        path = Path(p)
        if path.is_file() and path.suffix == '.xml':
            files.append(path)
        elif path.is_dir():
            pattern = "**/*.xml" if recursive else "*.xml"
            files.extend(list(path.glob(pattern)))

    for f in files:
        try:
            tree = ET.parse(f)
            root = tree.getroot()
            count = remove_tags_from_xml(root)
            if count > 0:
                if not dry_run:
                    tree.write(f, encoding='utf-8', xml_declaration=True)
                click.echo(f"{'[SIMULACIÓN] ' if dry_run else '✓ '}{f}: {count} tags eliminados")
        except Exception as e:
            click.echo(f"Error en {f}: {e}", err=True)

@xml_app.command()
def rename(
    paths: Optional[List[str]] = typer.Argument(None, exists=True),
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Procesar recursivamente"),
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="No aplicar cambios"),
):
    """Renombra archivos XML según el nombre de la pregunta."""
    if not paths:
        paths = ['.']
        
    files = []
    for p in paths:
        path = Path(p)
        if path.is_file() and path.suffix == '.xml':
            files.append(path)
        elif path.is_dir():
            pattern = "**/*.xml" if recursive else "*.xml"
            files.extend(list(path.glob(pattern)))

    for f in sorted(files):
        try:
            tree = ET.parse(f)
            root = tree.getroot()
            question = root.find('.//question')
            if question is not None:
                name_elem = question.find('.//name/text')
                if name_elem is not None and name_elem.text:
                    new_name = sanitize_filename(name_elem.text) + ".xml"
                    new_path = f.parent / new_name
                    if f != new_path:
                        if not dry_run:
                            f.rename(new_path)
                        click.echo(f"{'[SIMULACIÓN] ' if dry_run else '✓ '}{f} -> {new_path}")
        except Exception as e:
            click.echo(f"Error en {f}: {e}", err=True)
