import click
import typer
from pathlib import Path
from typing import Callable, List, Optional
from voight.core.banco import buscar_archivos, expandir_rutas
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


RECURSIVO = typer.Option(
    True, "-r", "--recursive/--no-recursive", help="Recorrer los directorios recursivamente (por defecto, sí).")


@convert_app.command(name="html-to-md")
def html_to_md(
    paths: Optional[List[str]] = typer.Argument(None, exists=True),
    recursive: bool = RECURSIVO,
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="No aplicar cambios"),
):
    """Convierte tags HTML a Markdown en archivos XML o GIFT (los directorios, recursivamente)."""
    files = expandir_rutas(paths or ['.'], recursive, ('.xml', '.gift', '.md'))

    modified_count = 0
    for f in files:
        try:
            content = f.read_text(encoding='utf-8')
            # En XML, campo por campo: sólo los que cambian pasan a format="markdown".
            if f.suffix == '.xml':
                modified, _ = html_a_markdown_xml(content)
            else:
                # La conversión recorta los bordes: un archivo sin HTML queda igual y el
                # salto de línea final se conserva.
                modified = convert_html_tags_to_markdown(content)
                if modified == content.strip():
                    modified = content
                elif content.endswith("\n"):
                    modified += "\n"
            
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


def _convertir(
    paths: Optional[List[str]], output: Optional[str], recursive: bool, forzar: bool, dry_run: bool,
    origen: str, destino: str, funcion: Callable[[str], str], nombre: str,
) -> None:
    """Un archivo (o stdin) va a stdout o a -o; con un directorio o varias rutas, cada
    archivo `origen` se convierte a `destino` al lado del original o, con -o, en ese
    directorio replicando el árbol. No pisa archivos existentes salvo --forzar."""
    rutas = [Path(p) for p in (paths or [])]
    lote = len(rutas) > 1 or any(r.is_dir() for r in rutas)
    if not lote:
        contenido = _leer_entrada(rutas[0] if rutas else None)
        try:
            resultado = funcion(contenido)
        except Exception as e:
            fail(f"No se pudo convertir el {nombre}: {e}")
        if output:
            salida = Path(output)
            if salida.is_dir():
                if not rutas or str(rutas[0]) == "-":
                    fail("Con stdin, -o debe ser un archivo.")
                salida = salida / rutas[0].with_suffix(destino).name
            salida.write_text(resultado, encoding="utf-8")
            click.echo(f"✓ {destino.lstrip('.').upper()} generado: {salida}")
        else:
            click.echo(resultado)
        return

    for r in rutas:
        if not r.exists():
            fail(f"No existe: {r}")
    dir_salida = Path(output) if output else None
    if dir_salida is not None and dir_salida.is_file():
        fail(f"Con un directorio o varias rutas, -o debe ser un directorio ({dir_salida} es un archivo).")

    pares = []  # (fuente, destino)
    for r in rutas:
        if r.is_dir():
            for f in buscar_archivos(r, recursive, (origen,)):
                relativa = f.relative_to(r).with_suffix(destino)
                pares.append((f, dir_salida / relativa if dir_salida else f.with_suffix(destino)))
        else:
            pares.append((r, dir_salida / r.with_suffix(destino).name if dir_salida else r.with_suffix(destino)))

    convertidos, existentes, errores = 0, [], 0
    for fuente, salida in pares:
        if salida.exists() and not forzar:
            existentes.append(salida)
            continue
        try:
            resultado = funcion(fuente.read_text(encoding="utf-8"))
        except Exception as e:
            errores += 1
            click.echo(f"✗ {fuente}: {e}", err=True)
            continue
        if not dry_run:
            salida.parent.mkdir(parents=True, exist_ok=True)
            salida.write_text(resultado, encoding="utf-8")
        click.echo(f"{'[SIMULACIÓN] ' if dry_run else '✓ '}{fuente} -> {salida}")
        convertidos += 1
    for salida in existentes:
        click.echo(f"✗ {salida} ya existe, no se pisa (--forzar lo reemplaza)", err=True)
    click.echo(f"\nFinalizado: {convertidos} archivos {'a convertir' if dry_run else 'convertidos'}"
               f" de {len(pares)}.")
    if existentes or errores:
        raise typer.Exit(code=1)


SALIDA_AYUDA = ("Salida: con un archivo, el archivo {fmt} (por defecto, stdout); con un directorio o varias "
                "rutas, el directorio donde se replica el árbol (por defecto, al lado de cada original).")
FORZAR = typer.Option(False, "--forzar", "--force", help="Reemplazar los archivos de salida que ya existen.")
SIMULAR = typer.Option(False, "-n", "--dry-run", help="Con un directorio, mostrar qué se convertiría sin escribir.")


@convert_app.command(name="xml-to-gift")
def xml_to_gift_cmd(
    paths: Optional[List[str]] = typer.Argument(None, help="Archivos o directorios (sin nada o '-', stdin)."),
    output: Optional[str] = typer.Option(None, "-o", "--output", help=SALIDA_AYUDA.format(fmt="GIFT")),
    recursive: bool = RECURSIVO,
    forzar: bool = FORZAR,
    dry_run: bool = SIMULAR,
):
    """Convierte Moodle XML a GIFT: un archivo, stdin ('-') o directorios (recursivamente)."""
    _convertir(paths, output, recursive, forzar, dry_run, ".xml", ".gift", xml_to_gift, "XML")


@convert_app.command(name="gift-to-xml")
def gift_to_xml_cmd(
    paths: Optional[List[str]] = typer.Argument(None, help="Archivos o directorios (sin nada o '-', stdin)."),
    output: Optional[str] = typer.Option(None, "-o", "--output", help=SALIDA_AYUDA.format(fmt="XML")),
    recursive: bool = RECURSIVO,
    forzar: bool = FORZAR,
    dry_run: bool = SIMULAR,
):
    """Convierte GIFT a Moodle XML: un archivo, stdin ('-') o directorios (recursivamente)."""
    _convertir(paths, output, recursive, forzar, dry_run, ".gift", ".xml", gift_to_xml, "GIFT")
