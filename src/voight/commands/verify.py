"""Comando para compilar y ejecutar el código de las preguntas y verificar su clave."""

import contextlib
import io
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

import click
import typer

from voight.commands.common import LLM_OPTION, emitir_json, fail
from voight.core.lector import leer_archivos, unidades_de
from voight.core.banco import expandir_rutas, filtrar_desde
from voight.core.verificar import PROBLEMAS, verificar

_ETIQUETAS = {
    "coincide": "✓ coincide con la correcta",
    "coincide_distractor": "✗ la salida es un distractor (¿clave equivocada?)",
    "revisar": "? la salida no aparece literalmente en las opciones (revisar)",
    "no_compila": "✗ no compila",
    "error_ejecucion": "✗ error en ejecución",
    "tiempo": "✗ no termina",
    "comportamiento_indefinido": "✗ comportamiento indefinido que la clave no menciona",
    "sin_compilador": "· sin compilador",
}


def verify(
    paths: Optional[List[Path]] = typer.Argument(None, exists=True, help="Archivos .gift/.xml o directorios."),
    llm: bool = LLM_OPTION,
    recursive: bool = typer.Option(False, "-r", "--recursive", help="Buscar recursivamente."),
    todas: bool = typer.Option(False, "--todas", "--all", help="Verificar toda pregunta con código, no sólo las que piden la salida."),
    sanitizar: bool = typer.Option(
        False, "--sanitizar", "--sanitize", help="C: compilar con -fsanitize=address,undefined para detectar comportamiento indefinido."),
    estilo: bool = typer.Option(
        False, "--estilo", "--style",
        help="Revisar el código C con las reglas de estilo de la cátedra (0x00XXh, requiere ripley). No cambia el código de salida."),
    concurrencia: int = typer.Option(4, "--concurrencia", "--concurrency", help="Compilaciones simultáneas."),
    solo_problemas: bool = typer.Option(False, "--solo-problemas", "--only-problems", help="Listar sólo las preguntas con problemas."),
    desde: Optional[str] = typer.Option(
        None, "--desde", "--since", help="Sólo los archivos cambiados desde esta revisión git (y los nuevos sin seguimiento)."),
    output_json: bool = typer.Option(False, "--json", help="Emite los resultados como JSON versionado."),
):
    """Compila y ejecuta el código de las preguntas de salida y compara con las opciones (gcc, javac).

    Sale con código 1 si la salida de alguna pregunta coincide con un distractor (clave
    equivocada), o si no compila, falla o no termina sin que la clave lo diga. Las que no
    aparecen literalmente en las opciones se listan para revisar, sin fallar.
    """
    archivos_rutas = expandir_rutas(paths or [Path(".")], recursive)
    if desde:
        try:
            archivos_rutas = filtrar_desde(archivos_rutas, desde, paths)
        except ValueError as e:
            fail(str(e))
        if not archivos_rutas:
            click.echo(f"No hay archivos de preguntas cambiados desde {desde}.")
            return
    if not archivos_rutas:
        fail("No se encontraron archivos de preguntas (.gift / .xml).")
    with contextlib.redirect_stdout(io.StringIO()):
        unidades = [u for u in unidades_de(leer_archivos(archivos_rutas)) if u.pregunta is not None]

    verificador = None
    if estilo:
        from voight.core.verificar import INSTALAR_RIPLEY, verificador_de_estilo

        verificador = verificador_de_estilo()
        if verificador is None:
            fail(f"--estilo usa las reglas de ripley, que no está instalado en este entorno: {INSTALAR_RIPLEY}")

    from voight.core.progreso import barra

    with barra(len(unidades), "Compilando y ejecutando") as avance:
        def uno(u):
            r = verificar(u.pregunta, sanitizar=sanitizar, todas=todas)
            avance()
            return u, r

        with ThreadPoolExecutor(max_workers=max(1, concurrencia)) as ejecutor:
            resultados = [(u, r) for u, r in ejecutor.map(uno, unidades) if r is not None]

    estilos = []
    if verificador is not None:
        from voight.core.verificar import revisar_estilo

        for u in unidades:
            observaciones = revisar_estilo(u.pregunta, verificador)
            if observaciones:
                estilos.append((u, observaciones))

    conteo = Counter(r.estado for _, r in resultados)
    problemas = [(u, r) for u, r in resultados if r.estado in PROBLEMAS]

    if output_json:
        emitir_json("verify", {
            "verificadas": len(resultados),
            "por_estado": dict(conteo),
            "resultados": [
                {"archivo": str(u.archivo), "titulo": u.pregunta.title, "lenguaje": r.lenguaje, "estado": r.estado,
                 "salida": r.salida, "detalle": r.detalle, "coincide_con": r.coincide_con}
                for u, r in resultados if not solo_problemas or r.estado in PROBLEMAS
            ],
            **({"estilo": [{"archivo": str(u.archivo), "titulo": u.pregunta.title, "observaciones": obs}
                           for u, obs in estilos]} if verificador is not None else {}),
        })
    else:
        for u, r in resultados:
            if solo_problemas and r.estado not in PROBLEMAS:
                continue
            click.echo(f"{_ETIQUETAS.get(r.estado, r.estado)} · {u.archivo} — {u.pregunta.title or '<sin título>'}")
            if r.estado in PROBLEMAS:
                if r.salida.strip():
                    click.echo(f"      salida: {r.salida.strip()[:120]!r}")
                if r.detalle:
                    click.echo(f"      {r.detalle[:160]}")
        if verificador is not None:
            click.echo(f"\nEstilo (reglas de la cátedra): {len(estilos)} preguntas con observaciones")
            for u, obs in estilos:
                reglas = Counter(o["regla"] for o in obs)
                click.echo(f"  {u.archivo} — {u.pregunta.title or '<sin título>'}: "
                           + ", ".join(f"{r} ×{n}" if n > 1 else r for r, n in sorted(reglas.items())))
        resumen = ", ".join(f"{n} {e}" for e, n in conteo.most_common())
        click.echo(f"\n{len(resultados)} preguntas verificadas: {resumen or 'ninguna con código ejecutable'}.")

    if problemas:
        raise typer.Exit(code=1)
