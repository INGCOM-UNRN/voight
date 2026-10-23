"""`voight config`: las claves y opciones globales, con un solo juego de comandos.

`show` lista todo (valores secretos ocultos, con su origen) y la configuración de IA que
resuelve yutani.ia; `get`, `set` y `unset` trabajan sobre una clave de `CLAVES`.
"""
from typing import Optional

import click
import typer

from voight.commands.common import fail
from voight.core.config import CLAVES, archivo_env, borrar, guardar, leer, ocultar

config_app = typer.Typer(help="Configuración global: claves de los servicios, proveedor y modelo de IA.")

NOMBRES = click.Choice(list(CLAVES))


@config_app.callback()
def config():
    """Configuración global: claves de los servicios, proveedor y modelo de IA.

    Se guarda en ~/.voight/.env; una variable de entorno con el mismo nombre gana. El
    proveedor y el modelo de IA de todo el ecosistema van en ~/.config/p1/ia.toml.
    """


@config_app.command(name="show")
def show_cmd(
    mostrar: bool = typer.Option(False, "--mostrar", "--reveal", help="Mostrar los valores secretos completos."),
):
    """Muestra cada clave (oculta), de dónde sale y la configuración de IA efectiva."""
    from yutani import ia

    from voight.core.ai import configuracion_ia

    click.echo(f"Configuración de voight ({archivo_env()}):")
    ancho = max(len(n) for n in CLAVES)
    for nombre, c in CLAVES.items():
        valor, origen = leer(c.variable)
        if valor is None:
            texto = "—"
        else:
            texto = (ocultar(valor) if c.secreta and not mostrar else valor) + (" (entorno)" if origen == "entorno" else "")
        click.echo(f"  {nombre:<{ancho}}  {texto}")
    try:
        efectiva = configuracion_ia()
    except ia.ErrorIA as e:
        click.echo(f"\nIA: {e}")
        return
    origen = efectiva.origen
    click.echo(f"\nIA de `voight ai` (común: {ia.ruta_configuracion()}):")
    click.echo(f"  proveedor  {efectiva.proveedor} ({origen.get('proveedor', '?')})")
    click.echo(f"  modelo     {efectiva.modelo or '—'} ({origen.get('modelo', '?')})")
    if efectiva.url:
        click.echo(f"  url        {efectiva.url} ({origen.get('url', 'por defecto')})")
    click.echo(f"  clave      {'sí' if efectiva.clave else 'no'}" + (f" ({origen['clave']})" if origen.get("clave") else ""))


@config_app.command(name="get")
def get_cmd(
    nombre: str = typer.Argument(..., click_type=NOMBRES, help="Clave a mostrar."),
    mostrar: bool = typer.Option(False, "--mostrar", "--reveal", help="Mostrar el valor secreto completo."),
):
    """Muestra el valor de una clave (los secretos, ocultos salvo --mostrar)."""
    c = CLAVES[nombre]
    valor, origen = leer(c.variable)
    if valor is None:
        click.echo(f"{nombre} no está configurada ({c.variable}).", err=True)
        raise typer.Exit(code=1)
    click.echo(ocultar(valor) if c.secreta and not mostrar else valor)
    if origen == "entorno":
        click.echo(f"(de la variable de entorno {c.variable})", err=True)


@config_app.command(name="set")
def set_cmd(
    nombre: str = typer.Argument(..., click_type=NOMBRES, help="Clave a guardar."),
    valor: Optional[str] = typer.Argument(
        None, help="Valor; si falta, se pide sin mostrarlo (así una clave no queda en el historial)."),
):
    """Guarda una clave en ~/.voight/.env.

    Claves: gemini-key, anthropic-key, typesafe-key, moodle-token, moodle-url,
    proveedor (google, local, opencode, claude) y modelo.
    """
    c = CLAVES[nombre]
    if valor is None:
        valor = typer.prompt(c.descripcion.capitalize(), hide_input=c.secreta)
    valor = valor.strip()
    if not valor:
        fail(f"El valor de {nombre} está vacío.")
    if nombre == "proveedor":
        from voight.core.ai import PROVEEDORES

        valor = valor.lower()
        if valor not in PROVEEDORES:
            fail(f"{valor!r} no es un proveedor: {', '.join(PROVEEDORES)}.")
    archivo = guardar(c.variable, valor)
    click.echo(f"✓ {nombre} guardada en {archivo}" + ("" if c.secreta else f": {valor}"))


@config_app.command(name="unset")
def unset_cmd(nombre: str = typer.Argument(..., click_type=NOMBRES, help="Clave a quitar.")):
    """Quita una clave de ~/.voight/.env (las demás quedan)."""
    c = CLAVES[nombre]
    if borrar(c.variable):
        click.echo(f"✓ {nombre} quitada de {archivo_env()}")
    else:
        click.echo(f"{nombre} no estaba guardada en {archivo_env()}.")
    if leer(c.variable)[1] == "entorno":
        click.echo(f"Sigue definida en el entorno ({c.variable}).", err=True)


@config_app.command(name="models")
def models_cmd():
    """Lista los modelos del proveedor de IA configurado."""
    from voight.core.ai import list_available_models, load_config

    try:
        client = load_config()
        models = list_available_models(client)
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(code=1) from None
    if models:
        click.echo(f"Modelos disponibles en {client.config.proveedor}:")
        for m in models:
            click.echo(f" - {m}")
    else:
        click.echo("No se encontraron modelos disponibles.")


# ---------------------------------------------------------------------------
# Nombres anteriores: avisan y siguen funcionando
# ---------------------------------------------------------------------------

def _aviso(viejo: str, nuevo: str) -> None:
    click.echo(f"Aviso: `voight config {viejo}` ahora es `voight config {nuevo}`; "
               "el nombre anterior se va a retirar.", err=True)


def _set_anterior(viejo: str, nombre: str):
    def comando(valor: str = typer.Argument(...)):
        _aviso(viejo, f"set {nombre}")
        set_cmd(nombre, valor)
    comando.__doc__ = f"Ahora es `voight config set {nombre}`."
    config_app.command(name=viejo, hidden=True)(comando)


for _viejo, _nombre in (("set-key", "gemini-key"), ("set-anthropic-key", "anthropic-key"),
                        ("set-typesafe-key", "typesafe-key"), ("set-moodle-token", "moodle-token"),
                        ("set-provider", "proveedor"), ("set-model", "modelo")):
    _set_anterior(_viejo, _nombre)


@config_app.command(name="show-key", hidden=True)
def show_key_cmd():
    """Ahora es `voight config show`."""
    _aviso("show-key", "show")
    show_cmd(mostrar=False)


@config_app.command(name="unset-key", hidden=True)
def unset_key_cmd():
    """Ahora es `voight config unset gemini-key` (antes borraba todo ~/.voight/.env)."""
    _aviso("unset-key", "unset gemini-key")
    unset_cmd("gemini-key")


@config_app.command(name="list-models", hidden=True)
def list_models_cmd():
    """Ahora es `voight config models`."""
    _aviso("list-models", "models")
    models_cmd()

