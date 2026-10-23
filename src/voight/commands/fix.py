import click
import typer
from pathlib import Path
from typing import List, Optional
from voight.core.banco import expandir_rutas, formato_de, formato_por_contenido
from voight.core.codigo import etiquetar_lenguaje_archivo, transformar_archivo
from voight.core.naming import rename_to_slug, rename_from_title, set_question_title

from voight.commands.common import LLM_OPTION, emitir_json

fix_app = typer.Typer(help="Todo lo que modifica archivos: formato (format), código, nombres, HTML, tags y ortografía (grammar).")


@fix_app.callback()
def fix(llm: bool = LLM_OPTION):
    """Comandos para corregir problemas comunes."""


@fix_app.command(name="slugify")
def slugify_cmd(
    paths: Optional[List[str]] = typer.Argument(None, exists=True),
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Procesar recursivamente"),
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="No aplicar cambios"),
):
    """Slugifica los nombres de los archivos (minúsculas, sin espacios ni acentos)."""
    if not paths:
        paths = ['.']
    
    files = []
    for p in paths:
        path = Path(p)
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            pattern = "**/*" if recursive else "*"
            files.extend([f for f in path.glob(pattern) if f.suffix in ('.gift', '.xml', '.md')])

    modified_count = 0
    for f in sorted(files):
        new_path = rename_to_slug(f, simular=dry_run)
        if new_path:
            click.echo(f"{'[SIMULACIÓN] ' if dry_run else '✓ '}{f} -> {new_path}")
            modified_count += 1
    
    click.echo(f"\nFinalizado: {modified_count} archivos renombrados.")

@fix_app.command(name="name-from-title")
def name_from_title_cmd(
    paths: Optional[List[str]] = typer.Argument(None, exists=True),
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Procesar recursivamente"),
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="No aplicar cambios"),
):
    """Renombra el archivo usando el título interno de la pregunta (slugificado)."""
    if not paths:
        paths = ['.']
    
    files = []
    for p in paths:
        path = Path(p)
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            pattern = "**/*" if recursive else "*"
            files.extend([f for f in path.glob(pattern) if f.suffix in ('.gift', '.xml')])

    modified_count = 0
    for f in sorted(files):
        new_path = rename_from_title(f, simular=dry_run)
        if new_path:
            click.echo(f"{'[SIMULACIÓN] ' if dry_run else '✓ '}{f} -> {new_path}")
            modified_count += 1
    
    click.echo(f"\nFinalizado: {modified_count} archivos renombrados.")

@fix_app.command(name="extension")
def extension_cmd(
    paths: Optional[List[str]] = typer.Argument(None, exists=True),
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Procesar recursivamente"),
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="No aplicar cambios"),
    json_out: bool = typer.Option(False, "--json", help="Salida en JSON."),
):
    """Corrige la extensión según el contenido: .xml con GIFT adentro pasa a .gift y viceversa.

    No pisa archivos existentes: si el destino ya existe, lo informa y sale con código 1.
    Los archivos cuyo contenido no se reconoce como GIFT ni como Moodle XML quedan como están.
    """
    files = expandir_rutas(paths or ['.'], recursive)

    renombrados, conflictos, sin_reconocer = [], [], []
    for f in sorted(files):
        try:
            formato = formato_por_contenido(f.read_text(encoding='utf-8'))
        except UnicodeDecodeError:
            formato = None
        if formato is None:
            sin_reconocer.append(f)
            continue
        if formato == formato_de(f):
            continue
        destino = f.with_suffix(f".{formato}")
        if destino.exists():
            conflictos.append((f, destino))
            continue
        if not dry_run:
            f.rename(destino)
        renombrados.append((f, destino))

    if json_out:
        emitir_json("fix extension", {
            "simulacion": dry_run,
            "renombrados": [{"origen": str(o), "destino": str(d)} for o, d in renombrados],
            "conflictos": [{"origen": str(o), "destino": str(d)} for o, d in conflictos],
            "sin_reconocer": [str(f) for f in sin_reconocer],
        })
    else:
        for origen, destino in renombrados:
            click.echo(f"{'[SIMULACIÓN] ' if dry_run else '✓ '}{origen} -> {destino}")
        for origen, destino in conflictos:
            click.echo(f"✗ {origen}: {destino} ya existe, no se renombra", err=True)
        for f in sin_reconocer:
            click.echo(f"? {f}: el contenido no parece GIFT ni Moodle XML", err=True)
        click.echo(f"\nFinalizado: {len(renombrados)} archivos {'a renombrar' if dry_run else 'renombrados'}.")
    if conflictos:
        raise typer.Exit(code=1)

@fix_app.command(name="title-from-name")
def title_from_name_cmd(
    paths: Optional[List[str]] = typer.Argument(None, exists=True),
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Procesar recursivamente"),
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="No aplicar cambios"),
):
    """Actualiza el título interno de la pregunta usando el nombre del archivo (sanitizado)."""
    if not paths:
        paths = ['.']
    
    files = []
    for p in paths:
        path = Path(p)
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            pattern = "**/*" if recursive else "*"
            files.extend([f for f in path.glob(pattern) if f.suffix in ('.gift', '.xml')])

    modified_count = 0
    for f in sorted(files):
        # Usar el nombre del archivo sin extensión como título
        new_title = f.stem.replace('_', ' ').capitalize()
        if set_question_title(f, new_title, simular=dry_run):
            click.echo(f"{'[SIMULACIÓN] ' if dry_run else '✓ '}{f}: título → '{new_title}'")
            modified_count += 1
    
    click.echo(f"\nFinalizado: {modified_count} títulos actualizados.")

@fix_app.command(name="clean-html")
def clean_html_cmd(
    paths: Optional[List[str]] = typer.Argument(None, exists=True),
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Procesar recursivamente"),
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="No aplicar cambios"),
):
    """Limpia el HTML obsoleto (<font>, <center>, <marquee>) y los estilos inline (GIFT y XML).

    `voight health` informa los archivos que lo tienen.
    """
    from voight.core.moodle_health import limpiar_html_archivo

    files = expandir_rutas(paths or ['.'], recursive)

    modified_count = 0
    for f in sorted(files):
        content = f.read_text(encoding='utf-8', errors='replace')
        new_content = limpiar_html_archivo(content, formato_de(f) or "gift")
        if new_content != content:
            if not dry_run:
                f.write_text(new_content, encoding='utf-8')
            click.echo(f"{'[SIMULACIÓN] ' if dry_run else '✓ '}{f}")
            modified_count += 1

    click.echo(f"\nFinalizado: {modified_count} archivos {'a modificar' if dry_run else 'modificados'}.")

@fix_app.command(name="code-indent")
def code_indent(
    paths: Optional[List[str]] = typer.Argument(None, exists=True),
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Procesar recursivamente"),
    saltos: bool = typer.Option(False, "--saltos", "--newlines", help="Marcar también cada fin de línea con ↵."),
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="No aplicar cambios"),
):
    """Marca la indentación del código con · (un punto por espacio) en GIFT, XML y Markdown."""
    files = expandir_rutas(paths or ['.'], recursive, ('.gift', '.xml', '.md'))

    modified_count = 0
    for f in sorted(files):
        content = f.read_text(encoding='utf-8')
        new_content, count = transformar_archivo(content, formato_de(f) or "md", fullwidth=None, espacios=True, saltos=saltos)
        if count > 0:
            if not dry_run:
                f.write_text(new_content, encoding='utf-8')
            click.echo(f"{'[SIMULACIÓN] ' if dry_run else '✓ '}{f}: {count} secciones de código corregidas")
            modified_count += 1
    
    click.echo(f"\nFinalizado: {modified_count} archivos modificados.")

@fix_app.command(name="code-chars")
def code_chars(
    paths: Optional[List[str]] = typer.Argument(None, exists=True),
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Procesar recursivamente"),
    to_normal: bool = typer.Option(True, "--to-normal", help="Convertir a normal (default)"),
    to_fullwidth: bool = typer.Option(False, "--to-fullwidth", help="Convertir a fullwidth"),
    marcas: bool = typer.Option(
        True, "--marcas/--sin-marcas", "--marks/--no-marks",
        help="Con --to-fullwidth, agregar las marcas · y ↵; con --to-normal, conservar las que hay "
             "(por defecto, sí). --sin-marcas con --to-normal las quita."
    ),
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="No aplicar cambios"),
):
    """Convierte los caracteres del código entre normal y fullwidth (GIFT, XML y Markdown).

    Sólo cambia los símbolos: la indentación con · y los ↵ de `code-indent` se conservan
    al volver a normal (salvo --sin-marcas), así que los dos comandos se combinan.
    """
    if to_fullwidth:
        to_normal = False

    files = expandir_rutas(paths or ['.'], recursive, ('.gift', '.md', '.xml'))

    modified_count = 0
    for f in sorted(files):
        content = f.read_text(encoding='utf-8')
        new_content, count = transformar_archivo(
            content, formato_de(f) or "md", fullwidth=not to_normal, espacios=marcas, saltos=marcas,
            conservar_marcas=marcas,
        )
        if count > 0:
            if not dry_run:
                f.write_text(new_content, encoding='utf-8')
            click.echo(f"{'[SIMULACIÓN] ' if dry_run else '✓ '}{f}: {count} bloques corregidos")
            modified_count += 1
    
    click.echo(f"\nFinalizado: {modified_count} archivos modificados.")

@fix_app.command(name="code-lang")
def code_lang(
    paths: Optional[List[str]] = typer.Argument(None, exists=True),
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Procesar recursivamente"),
    lenguaje: Optional[str] = typer.Option(
        None, "--lenguaje", "--language", help="Lenguaje para los bloques en los que no se puede detectar (c, java, python…)."),
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="No aplicar cambios"),
):
    """Agrega la etiqueta de lenguaje (c, java, python) a los bloques ``` que no la tienen (GIFT, XML y Markdown)."""
    files = expandir_rutas(paths or ['.'], recursive, ('.gift', '.xml', '.md'))

    modified_count = 0
    for f in sorted(files):
        content = f.read_text(encoding='utf-8')
        new_content, count = etiquetar_lenguaje_archivo(content, formato_de(f) or "md", lenguaje)
        if count > 0:
            if not dry_run:
                f.write_text(new_content, encoding='utf-8')
            click.echo(f"{'[SIMULACIÓN] ' if dry_run else '✓ '}{f}: {count} bloques etiquetados")
            modified_count += 1

    click.echo(f"\nFinalizado: {modified_count} archivos {'a modificar' if dry_run else 'modificados'}.")

@fix_app.command(name="code-format")
def code_format(
    paths: Optional[List[str]] = typer.Argument(None, exists=True),
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Procesar recursivamente"),
    estilo: Optional[str] = typer.Option(
        None, "--estilo", "--style",
        help="Estilo de clang-format (por defecto: LLVM con 4 espacios, regla 0x0005h). Un estilo de llaves "
             "(allman, stroustrup, gnu, linux, whitesmiths…) aplica esas llaves sobre el estilo por defecto."),
    dry_run: bool = typer.Option(False, "-n", "--dry-run", help="No aplicar cambios"),
):
    """Formatea el código C y Java de las preguntas con clang-format, conservando la convención de cada archivo."""
    from voight.core.formato_codigo import comando_clang_format, error_de_estilo, formatear_archivo, resolver_estilo

    comando = comando_clang_format()
    if comando is None:
        click.echo("Error: hace falta clang-format (o uvx para usar el paquete de PyPI).", err=True)
        raise typer.Exit(code=1)
    estilo_clang = resolver_estilo(estilo)
    error = error_de_estilo(comando, estilo_clang)
    if error:
        # Sin esto, cada bloque fallaba en silencio y el comando terminaba sin cambiar nada.
        click.echo(f"Error: clang-format no acepta el estilo {estilo_clang!r}: {error}", err=True)
        raise typer.Exit(code=2)
    files = expandir_rutas(paths or ['.'], recursive, ('.gift', '.xml', '.md'))

    modified_count = 0
    for f in sorted(files):
        content = f.read_text(encoding='utf-8')
        new_content, count = formatear_archivo(content, formato_de(f) or "md", comando, estilo_clang)
        if count > 0:
            if not dry_run:
                f.write_text(new_content, encoding='utf-8')
            click.echo(f"{'[SIMULACIÓN] ' if dry_run else '✓ '}{f}: {count} bloques formateados")
            modified_count += 1

    click.echo(f"\nFinalizado: {modified_count} archivos {'a modificar' if dry_run else 'modificados'}.")
