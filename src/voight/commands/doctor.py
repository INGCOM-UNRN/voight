"""Comando doctor para diagnóstico del entorno de voight."""

import json
import shutil
import sys
import click
import typer


def doctor_cmd(
    json_output: bool = typer.Option(
        False, "--json", help="Emitir diagnóstico en formato JSON estructurado."
    ),
):
    """Verifica el estado del entorno de VOIGHT (Python, LanguageTool, gcc y el motor de síntesis)."""
    diagnostico = []

    py_ok = sys.version_info >= (3, 10)
    diagnostico.append({
        "componente": "Python Runtime",
        "estado": "OK" if py_ok else "ERROR",
        "requerido": True,
        "detalle": f"Python {sys.version.split()[0]}",
    })

    lt_path = shutil.which("languagetool") or shutil.which("languagetool-server")
    diagnostico.append({
        "componente": "LanguageTool Local",
        "estado": "OK" if lt_path else "ADVERTENCIA",
        "requerido": False,
        "detalle": lt_path or "No encontrado (se usará API remota si no hay servidor local)",
    })

    # Requisitos de `synth`: compilar y ejecutar los snippets (gcc) y el motor de alucarD.
    gcc_path = shutil.which("gcc")
    diagnostico.append({
        "componente": "Compilador GCC (comando synth)",
        "estado": "OK" if gcc_path else "ADVERTENCIA",
        "requerido": False,
        "detalle": gcc_path or "No encontrado: `synth` compila los snippets para verificar su salida",
    })

    try:
        from voight.core import synth as _synth  # noqa: F401
        motor_ok, motor_detalle = True, "generador_examenes.synthesizer disponible"
    except ImportError:
        motor_ok, motor_detalle = False, "No instalado: `synth` delega en el motor del paquete alucarD"
    diagnostico.append({
        "componente": "Motor de síntesis (alucarD)",
        "estado": "OK" if motor_ok else "ADVERTENCIA",
        "requerido": False,
        "detalle": motor_detalle,
    })

    # Diagramas mermaid incrustados al fusionar Moodle XML (`unify`).
    from voight.core.incrustar import comando_mermaid

    mmdc_path = comando_mermaid()
    diagnostico.append({
        "componente": "mermaid-cli (diagramas en unify)",
        "estado": "OK" if mmdc_path else "ADVERTENCIA",
        "requerido": False,
        "detalle": mmdc_path or "No encontrado: `npm install -g @mermaid-js/mermaid-cli` (o VOIGHT_MMDC)",
    })

    # Proveedor de IA de `voight ai` (opcional): el diagnóstico común de yutani.ia.
    from yutani import ia

    from voight.core.ai import configuracion_ia

    try:
        chequeos_ia = ia.diagnostico(configuracion_ia())
    except ia.ErrorIA as exc:
        chequeos_ia = [ia.Chequeo("ia", False, False, str(exc))]
    for c in chequeos_ia:
        diagnostico.append({
            "componente": f"{c.nombre} (comando ai)",
            "estado": "OK" if c.ok else "ADVERTENCIA",
            "requerido": False,
            "detalle": c.detalle + (f" — {c.sugerencia}" if c.sugerencia else ""),
        })

    todo_ok = py_ok

    if json_output:
        payload = {
            "schema_version": "1.0.0",
            "herramienta": "voight",
            "ok": todo_ok,
            "componentes": diagnostico,
        }
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        sys.exit(0 if todo_ok else 1)

    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()
        tabla = Table(title="🏥 Diagnóstico del Entorno VOIGHT (doctor)", border_style="cyan")
        tabla.add_column("Componente", style="bold white")
        tabla.add_column("Estado", justify="center")
        tabla.add_column("Detalle")

        for c in diagnostico:
            color = "bold green" if c["estado"] == "OK" else ("bold yellow" if c["estado"] == "ADVERTENCIA" else "bold red")
            simbolo = "✓" if c["estado"] == "OK" else ("⚠️" if c["estado"] == "ADVERTENCIA" else "✗")
            tabla.add_row(c["componente"], f"[{color}]{simbolo} {c['estado']}[/{color}]", c["detalle"])

        console.print(tabla)
    except ImportError:
        click.echo("🏥 Diagnóstico del Entorno VOIGHT (doctor)")
        for c in diagnostico:
            click.echo(f" - {c['componente']}: {c['estado']} ({c['detalle']})")

    if not todo_ok:
        sys.exit(1)
