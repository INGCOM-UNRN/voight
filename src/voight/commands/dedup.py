"""Comando para eliminar preguntas duplicadas (GIFT y Moodle XML)."""

import contextlib
import io
from pathlib import Path
from typing import List, Optional

import click
import typer

from voight.commands.common import LLM_OPTION, con_configuracion, emitir_json, fail
from voight.core.lector import leer_archivos, unidades_de
from voight.core.banco import archivos_cambiados, expandir_rutas
from voight.core.deduplicar import CRITERIOS, a_json, agrupar, aplicar, plan, registrar, respaldos, restaurar


def dedup(
    ctx: typer.Context,
    paths: Optional[List[Path]] = typer.Argument(None, exists=True, help="Archivos .gift/.xml o directorios."),
    llm: bool = LLM_OPTION,
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Buscar recursivamente."),
    similarity: float = typer.Option(
        0.95, "-s", "--similarity", min=0.0, max=1.0,
        help="Similitud mínima (0–1) para considerar dos preguntas duplicadas.",
    ),
    conservar: str = typer.Option(
        "completa", "--conservar", "--keep", click_type=click.Choice(CRITERIOS),
        help="Cuál se conserva de cada grupo: la más completa (feedback, título, opciones) o la primera.",
    ),
    aplicar_cambios: bool = typer.Option(
        False, "--aplicar", "--apply", help="Eliminar de verdad (sin esta opción sólo se muestra lo que se eliminaría).",
    ),
    log: Path = typer.Option(
        Path("dedup.log"), "--log",
        help="Con --aplicar, log (TSV, se agrega al final) de cada pregunta eliminada con las rutas completas.",
    ),
    confirmar_jev: bool = typer.Option(
        False, "--confirmar-jev", "--confirm-jev",
        help="Confirmar cada par con Jev (TypeSafe): sólo quedan los que evalúan exactamente lo mismo.",
    ),
    desde: Optional[str] = typer.Option(
        None, "--desde", "--since", help="Sólo los archivos cambiados desde esta revisión git (y los nuevos sin seguimiento)."),
    respaldo: Path = typer.Option(
        Path("dedup-respaldos"), "--respaldo", "--backup-dir",
        help="Con --aplicar, directorio donde se guarda una copia completa de cada archivo modificado o borrado.",
    ),
    restaurar_id: Optional[str] = typer.Option(
        None, "--restaurar", "--restore", metavar="RESPALDO",
        help="Deshacer un dedup: 'ultimo' o el nombre de un respaldo de --respaldo (no pisa archivos editados después).",
    ),
    forzar: bool = typer.Option(False, "--forzar", "--force", help="Con --restaurar, pisar también los archivos editados después."),
    tui: bool = typer.Option(
        False, "--tui", help="Revisar los grupos en una interfaz de terminal y decidir cuáles eliminar (extra 'tui').",
    ),
    output_json: bool = typer.Option(False, "--json", help="Emite los grupos de duplicados como JSON versionado."),
):
    """Elimina preguntas duplicadas según un umbral de similitud (GIFT y Moodle XML).

    Sólo compara preguntas del mismo tipo y conserva, de cada grupo, la más completa;
    elimina las que son similares a ella por encima del umbral. Sin --aplicar sólo
    muestra lo que haría. Al aplicar, cada eliminación queda en --log con la ruta
    completa del archivo (de ella se infieren las categorías).
    """
    if restaurar_id:
        _restaurar(respaldo, restaurar_id, forzar, output_json)
        return
    opciones = con_configuracion(ctx, paths, "dedup", {"similarity": (similarity, "umbral"), "conservar": conservar})
    similarity, conservar = float(opciones["similarity"]), opciones["conservar"]
    archivos_rutas = expandir_rutas(paths or [Path(".")], recursive)
    if not archivos_rutas:
        fail("No se encontraron archivos de preguntas (.gift / .xml).")

    with contextlib.redirect_stdout(io.StringIO()):
        archivos = leer_archivos(archivos_rutas)
    unidades = [u for u in unidades_de(archivos) if u.pregunta is not None]
    grupos = agrupar(unidades, similarity, conservar)
    if desde:
        # Se compara contra todo el banco, pero sólo interesan los grupos con algo nuevo.
        try:
            cambiados = archivos_cambiados(desde, paths)
        except ValueError as e:
            fail(str(e))
        grupos = [g for g in grupos
                  if any(u.archivo.resolve() in cambiados for u in [g.conservada] + [d for d, _ in g.duplicadas])]
    descartados = []
    if confirmar_jev and grupos:
        from voight.core.clasificacion import ClienteJev
        from voight.core.deduplicar import confirmar_con_jev

        try:
            from voight.core.cache import Cache

            cliente = ClienteJev(cache=Cache("jev"))
        except ValueError as e:
            fail(str(e))
        grupos, descartados = confirmar_con_jev(grupos, cliente)
        if not output_json:
            for d in descartados:
                click.echo(f"≠ Jev: no son la misma pregunta ({d['probabilidad']:.2f}): {d['descartado']} "
                           f"↔ {d['conserva']}")

    if tui:
        if not grupos:
            click.echo(f"No hay duplicados con similitud ≥ {similarity:g} entre {len(unidades)} preguntas.")
            return
        try:
            from voight.tui.dedup import DedupApp
        except ImportError:
            fail('La interfaz de terminal requiere el extra opcional \'tui\': '
                 'uv tool install "voight[tui] @ git+https://github.com/INGCOM-UNRN/voight"')
        from voight.core.deduplicar import Revision

        resultado = DedupApp(archivos, Revision(grupos), similarity, log, respaldo).run()
        if resultado:
            click.echo(f"Se eliminaron {resultado['eliminadas']} preguntas ({len(resultado['modificados'])} archivos "
                       f"modificados, {len(resultado['borrados'])} borrados). Registro: {log.resolve()}")
            if resultado.get("respaldo"):
                click.echo(f"Respaldo: {resultado['respaldo']} (deshacer: voight dedup --restaurar ultimo)")
        else:
            click.echo("No se eliminó nada.")
        return

    cambios = aplicar(archivos, grupos, respaldo) if aplicar_cambios else plan(archivos, grupos)
    eliminadas = sum(len(g.duplicadas) for g in grupos)
    registradas = registrar(grupos, cambios, log, similarity) if aplicar_cambios else 0

    if output_json:
        emitir_json("dedup", {
            "umbral": similarity,
            "aplicado": aplicar_cambios,
            "preguntas": len(unidades),
            "eliminadas": eliminadas,
            "grupos": a_json(grupos),
            "archivos_modificados": [str(r) for r in cambios["modificados"]],
            "archivos_borrados": [str(r) for r in cambios["borrados"]],
            **({"log": str(log.resolve())} if registradas else {}),
            **({"respaldo": str(cambios["respaldo"])} if cambios.get("respaldo") else {}),
            **({"descartados_jev": descartados} if confirmar_jev else {}),
        })
        return

    if not grupos:
        click.echo(f"No hay duplicados con similitud ≥ {similarity:g} entre {len(unidades)} preguntas.")
        return

    for g in grupos:
        click.echo(f"✓ Se conserva: {g.conservada.archivo} — {g.conservada.pregunta.title or '<sin título>'}")
        for u, s in g.duplicadas:
            click.echo(f"    ✗ {s:.3f}  {u.archivo} — {u.pregunta.title or '<sin título>'}")
    verbo = "Se eliminaron" if aplicar_cambios else "Se eliminarían"
    click.echo(f"\n{verbo} {eliminadas} preguntas duplicadas en {len(grupos)} grupos "
               f"({len(cambios['modificados'])} archivos modificados, {len(cambios['borrados'])} borrados).")
    if not aplicar_cambios:
        click.echo("Simulación: no se modificó nada. Usá --aplicar para eliminarlas.")
    elif registradas:
        click.echo(f"Registro de las eliminaciones: {log.resolve()}")
    if cambios.get("respaldo"):
        click.echo(f"Respaldo de los originales: {cambios['respaldo']} (deshacer: voight dedup --restaurar ultimo)")


def _restaurar(raiz: Path, nombre: str, forzar: bool, output_json: bool) -> None:
    disponibles = respaldos(raiz)
    if not disponibles:
        fail(f"No hay respaldos en {raiz.resolve()}.")
    if nombre in ("ultimo", "último", "latest"):
        elegido = disponibles[-1]
    else:
        elegido = next((d for d in disponibles if d.name == nombre), None)
        if elegido is None:
            fail(f"No existe el respaldo {nombre!r}. Disponibles: {', '.join(d.name for d in disponibles)}")
    resultado = restaurar(elegido, forzar)
    if output_json:
        emitir_json("dedup restaurar", {"respaldo": str(elegido), **resultado})
    else:
        for ruta in resultado["restaurados"]:
            click.echo(f"↺ {ruta}")
        for ruta in resultado["cambiados"]:
            click.echo(f"⚠ {ruta}: cambió después del dedup; no se restauró (usá --forzar para pisarlo).")
        click.echo(f"Restaurados {len(resultado['restaurados'])} archivos desde {elegido}"
                   + (f"; {len(resultado['sin_cambios'])} ya estaban como antes." if resultado["sin_cambios"] else "."))
    if resultado["cambiados"]:
        raise typer.Exit(1)
