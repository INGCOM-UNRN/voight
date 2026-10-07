import click
import typer
from pathlib import Path
from typing import Optional

from voight.commands.common import LLM_OPTION, emitir_json, fail


def synth(
    plantilla: str = typer.Argument(""),
    llm: bool = LLM_OPTION,
    cantidad: int = typer.Option(5, "-n", "--cantidad", "--count", show_default=True,
                                  help="Cantidad de preguntas a sintetizar."),
    semilla: int = typer.Option(42, "-s", "--semilla", "--seed", show_default=True,
                                 help="Semilla pseudo-aleatoria (salida reproducible)."),
    archivo_salida: Optional[Path] = typer.Option(
        None, "-o", "--output",
        help="Archivo destino: .gift o .xml según la extensión."),
    listar: bool = typer.Option(False, "--listar", "--list", help="Lista las plantillas disponibles y sale."),
    output_json: bool = typer.Option(False, "--json", help="Emite el resultado como JSON versionado."),
):
    """daedalus en belmont: sintetiza preguntas de C verificadas con GCC.

    PLANTILLA es una de las generadoras incorporadas (ver --listar). Cada
    pregunta se crea con parámetros aleatorios, se compila y ejecuta de verdad
    para fijar la salida correcta, y se acompaña de distractores verosímiles.
    """
    from voight.core.synth import (
        exportar_gift,
        exportar_xml,
        plantillas_disponibles,
        sintetizar,
    )

    if listar or not plantilla:
        if not listar and not archivo_salida:
            fail("Indicá la plantilla. Ver opciones con --listar.")
        if output_json:
            emitir_json("synth", {"plantillas": dict(sorted(plantillas_disponibles().items()))})
            return
        click.echo("Plantillas disponibles del sintetizador daedalus:")
        for nombre, descripcion in sorted(plantillas_disponibles().items()):
            click.echo(f"  - {nombre}: {descripcion}")
        return

    if not archivo_salida:
        fail("Falta -o/--output con la ruta del banco a generar.")

    try:
        snippets = sintetizar(plantilla, cantidad=cantidad, semilla=semilla)
    except KeyError as e:
        fail(str(e))
    except RuntimeError as e:
        fail(f"{e}")

    extension = archivo_salida.suffix.lower()
    if extension == ".gift":
        contenido = exportar_gift(snippets)
    elif extension == ".xml":
        contenido = exportar_xml(snippets)
    else:
        fail("La extensión de salida debe ser .gift o .xml")

    archivo_salida.parent.mkdir(parents=True, exist_ok=True)
    archivo_salida.write_text(contenido, encoding="utf-8")
    if output_json:
        emitir_json("synth", {"plantilla": plantilla, "cantidad": len(snippets),
                              "semilla": semilla, "salida": str(archivo_salida)})
        return
    click.echo(f"✓ {len(snippets)} preguntas de C sintetizadas y verificadas con gcc "
               f"→ {archivo_salida}")
