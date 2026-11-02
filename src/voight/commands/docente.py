"""Catálogo, muestra reproducible y revisión de imágenes sobre el lector común."""

from pathlib import Path
from typing import List, Optional

import click
import typer

from voight.commands.common import emitir_json, fail
from voight.core.accessibility import auditar_accesibilidad
from voight.core.catalog import exportar_catalogo_markdown, para_catalogo
from voight.core.lectura import leer_preguntas
from voight.core.simulator import simular_examen_aleatorio


def _leer(rutas, recursivo):
    try:
        return leer_preguntas(rutas, recursivo)
    except (ValueError, OSError) as exc:
        fail(str(exc))


def _salida(
    comando: str,
    preguntas: list[dict],
    titulo: str,
    salida: Optional[Path],
    output_json: bool,
    **extra,
) -> None:
    texto = exportar_catalogo_markdown([para_catalogo(p) for p in preguntas], titulo)
    if salida:
        # Nunca sobrescribir una de las fuentes del propio catálogo.
        if salida.resolve() in {Path(p["archivo"]).resolve() for p in preguntas}:
            fail("La salida no puede sobrescribir un archivo de preguntas de entrada.")
        salida.parent.mkdir(parents=True, exist_ok=True)
        salida.write_text(texto, encoding="utf-8")
    if output_json:
        emitir_json(
            comando,
            {
                "preguntas": preguntas,
                "cantidad": len(preguntas),
                "salida": str(salida) if salida else None,
                **extra,
            },
        )
    elif salida:
        click.echo(f"✓ {len(preguntas)} preguntas exportadas en {salida}")
    else:
        click.echo(texto)


def catalogo(
    rutas: List[Path] = typer.Argument(
        ..., exists=True, help="Bancos GIFT/XML o directorios."
    ),
    salida: Optional[Path] = typer.Option(
        None, "-o", "--output", help="Catálogo Markdown (stdout por defecto)."
    ),
    titulo: str = typer.Option("Catálogo de preguntas", "--titulo"),
    recursivo: bool = typer.Option(True, "-r/--no-recursive"),
    output_json: bool = typer.Option(
        False, "--json", help="Modelo de preguntas con referencias de origen."
    ),
):
    """Exporta un catálogo docente con enunciados, opciones y claves de respuesta."""
    _salida("catalogo", _leer(rutas, recursivo), titulo, salida, output_json)


def muestra(
    rutas: List[Path] = typer.Argument(
        ..., exists=True, help="Bancos GIFT/XML o directorios."
    ),
    cantidad: int = typer.Option(
        10, "-n", "--cantidad", min=1, help="Cantidad exacta, sin reemplazo."
    ),
    semilla: int = typer.Option(
        42, "--semilla", "--seed", help="Misma semilla y banco: misma muestra."
    ),
    salida: Optional[Path] = typer.Option(
        None, "-o", "--output", help="Vista docente Markdown."
    ),
    recursivo: bool = typer.Option(True, "-r/--no-recursive"),
    output_json: bool = typer.Option(
        False, "--json", help="Muestra y semilla como JSON versionado."
    ),
):
    """Selecciona una muestra reproducible para revisión docente (incluye las claves)."""
    banco = _leer(rutas, recursivo)
    if salida and salida.resolve() in {Path(p["archivo"]).resolve() for p in banco}:
        fail("La salida no puede sobrescribir un archivo de preguntas de entrada.")
    # Las categorías y descripciones no son reactivos evaluables.
    evaluables = [p for p in banco if p.get("type") not in ("Description", "Category")]
    try:
        seleccion = simular_examen_aleatorio(evaluables, cantidad, semilla)
    except ValueError as exc:
        fail(str(exc))
    _salida(
        "muestra",
        seleccion,
        f"Muestra docente · semilla {semilla}",
        salida,
        output_json,
        semilla=semilla,
        disponibles=len(evaluables),
    )


def accesibilidad(
    rutas: List[Path] = typer.Argument(
        ..., exists=True, help="Bancos GIFT/XML o directorios."
    ),
    recursivo: bool = typer.Option(True, "-r/--no-recursive"),
    output_json: bool = typer.Option(False, "--json"),
):
    """Revisa texto alternativo de imágenes en enunciados, opciones y retroalimentación."""
    resultado = auditar_accesibilidad(_leer(rutas, recursivo))
    if output_json:
        emitir_json("health accesibilidad", resultado)
    else:
        click.echo(
            f"{resultado['preguntas']} preguntas · {resultado['total_imagenes']} imágenes · "
            f"{resultado['imagenes_sin_alt']} sin texto alternativo"
        )
        for hallazgo in resultado["hallazgos"]:
            click.echo(
                f"  {hallazgo['archivo']} · {hallazgo['titulo']} · {hallazgo['campo']}: "
                f"{hallazgo['imagenes_sin_alt']} imágenes sin alt"
            )
    if not resultado["ok"]:
        raise typer.Exit(code=1)
