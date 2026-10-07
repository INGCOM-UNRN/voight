import json

import click
import typer

from voight.core.llm_instructions import get_instructions


def llm_callback(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.echo(get_instructions(ctx.command.name))
    ctx.exit()


LLM_OPTION = typer.Option(
    False,
    "--llm",
    callback=llm_callback,
    is_eager=True,
    help="Muestra instrucciones para un LLM sobre este comando.",
)


def fail(message: str) -> "typer.Exit":
    """Reemplazo de `click.ClickException` compatible con el fork de click que
    typer usa internamente (`typer._click`): un `click.ClickException` de la
    librería `click` externa no es reconocido por el manejo de excepciones de
    typer y termina propagándose crudo en vez de imprimirse y salir con 1.
    """
    click.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=1)


SCHEMA_VERSION = "1.0.0"


def emitir_json(comando: str, datos: dict) -> None:
    """Imprime `datos` como JSON con envoltorio versionado (`schema_version`, `comando`)."""
    payload = {"schema_version": SCHEMA_VERSION, "herramienta": "voight", "comando": comando}
    payload.update(datos)
    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))


def con_configuracion(ctx, rutas, seccion: str, valores: dict) -> dict:
    """Completa `valores` (parámetro → valor recibido) con el .voight.toml del banco.

    Sólo reemplaza los parámetros que el usuario no pasó (su valor viene del default de
    la opción). Las claves del archivo son los nombres de los parámetros, salvo que se
    pase `{parámetro: (valor, "clave_en_el_archivo")}`.
    """
    from voight.core.configuracion import cargar, valor

    config = cargar(rutas or [])
    resultado = {}
    for parametro, dato in valores.items():
        actual, clave = dato if isinstance(dato, tuple) else (dato, parametro)
        fuente = ctx.get_parameter_source(parametro) if ctx is not None else None
        # Por nombre: typer usa su propia copia de click y su ParameterSource es otra clase.
        por_defecto = fuente is None or getattr(fuente, "name", "") in ("DEFAULT", "DEFAULT_MAP")
        en_archivo = valor(config, seccion, clave)
        if en_archivo is not None and por_defecto:
            resultado[parametro] = en_archivo
        else:
            resultado[parametro] = actual
    return resultado
