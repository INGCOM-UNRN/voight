import click
import typer
from voight.core.config import save_api_key, get_api_key, delete_api_key, save_model, get_model, save_typesafe_key
from voight.core.config import save_anthropic_key, save_moodle_token, save_proveedor
from voight.core.ai import load_config, list_available_models

config_app = typer.Typer(help="Configuración global de las herramientas.")


@config_app.callback()
def config():
    """Configuración global de las herramientas."""


@config_app.command(name="set-key")
def set_key_cmd(api_key: str = typer.Argument(...)):
    """Configura la GEMINI_API_KEY globalmente."""
    try:
        save_api_key(api_key)
        click.echo("✅ API Key guardada correctamente en ~/.voight/.env")
    except Exception as e:
        click.echo(f"❌ Error al guardar la API Key: {e}", err=True)

@config_app.command(name="set-typesafe-key")
def set_typesafe_key_cmd(api_key: str = typer.Argument(...)):
    """Configura la TYPESAFE_API_KEY (Jev) para `ai --mode classify`."""
    try:
        save_typesafe_key(api_key)
        click.echo("✅ TYPESAFE_API_KEY guardada correctamente en ~/.voight/.env")
    except Exception as e:
        click.echo(f"❌ Error al guardar la API Key: {e}", err=True)

@config_app.command(name="set-anthropic-key")
def set_anthropic_key_cmd(api_key: str = typer.Argument(...)):
    """Configura la ANTHROPIC_API_KEY (Claude) para `ai --proveedor claude`."""
    try:
        save_anthropic_key(api_key)
        click.echo("✅ ANTHROPIC_API_KEY guardada correctamente en ~/.voight/.env")
    except Exception as e:
        click.echo(f"❌ Error al guardar la API Key: {e}", err=True)

@config_app.command(name="set-provider")
def set_provider_cmd(proveedor: str = typer.Argument(..., click_type=click.Choice(["gemini", "claude"]))):
    """Configura el proveedor por defecto de `voight ai` (gemini o claude)."""
    save_proveedor(proveedor)
    click.echo(f"✅ Proveedor por defecto: {proveedor}")

@config_app.command(name="set-moodle-token")
def set_moodle_token_cmd(token: str = typer.Argument(...)):
    """Configura el MOODLE_TOKEN del servicio web para `moodle subir`."""
    save_moodle_token(token)
    click.echo("✅ MOODLE_TOKEN guardado correctamente en ~/.voight/.env")

@config_app.command(name="set-model")
def set_model_cmd(model: str = typer.Argument(...)):
    """Configura el modelo de Gemini por defecto."""
    try:
        save_model(model)
        click.echo(f"✅ Modelo por defecto configurado: {model}")
    except Exception as e:
        click.echo(f"❌ Error al guardar el modelo: {e}", err=True)

@config_app.command(name="list-models")
def list_models_cmd():
    """Lista los modelos del proveedor de IA configurado (Gemini por defecto)."""
    try:
        client = load_config()
        models = list_available_models(client)
        if models:
            click.echo(f"Modelos disponibles en {client.config.proveedor}:")
            for m in models:
                click.echo(f" - {m}")
        else:
            click.echo("No se encontraron modelos disponibles.")
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)

@config_app.command(name="show-key")
def show_key_cmd():
    """Muestra la API Key actual (parcialmente oculta)."""
    key = get_api_key()
    if key:
        hidden_key = key[:4] + "*" * (len(key) - 8) + key[-4:]
        click.echo(f"API Key configurada: {hidden_key}")
        click.echo(f"Modelo por defecto: {get_model()}")
    else:
        click.echo("No hay API Key configurada.")

@config_app.command(name="unset-key")
def unset_key_cmd():
    """Elimina la configuración de la API Key."""
    delete_api_key()
    click.echo("✅ Configuración eliminada.")
