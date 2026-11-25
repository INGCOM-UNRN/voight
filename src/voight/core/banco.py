"""Acceso uniforme a bancos de preguntas en GIFT y Moodle XML.

Descubre los archivos de un repositorio y los parsea al modelo unificado según su
extensión, para que validate, analyze y health traten ambos formatos por igual.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Optional

from voight.core.moodle_xml import parse_xml_file
from voight.core.parser import parse_gift_file

EXTENSIONES = (".gift", ".xml")


def formato_de(ruta: str | Path) -> str | None:
    """'gift' o 'xml' según la extensión (None si no es un banco)."""
    sufijo = Path(ruta).suffix.lower()
    return {".gift": "gift", ".xml": "xml"}.get(sufijo)


# Moodle XML: declaración y comentarios opcionales, y luego <quiz> o una <question> suelta.
_XML_MOODLE = re.compile(r"\s*(?:<\?xml[^>]*\?>\s*)?(?:<!--.*?-->\s*)*<(?:quiz|question)\b", re.DOTALL)
# GIFT: una categoría, un título ::…:: o un bloque de respuestas {…} (no hace falta el
# parser, que acepta cualquier texto como pregunta de descripción).
_GIFT = re.compile(r"^\s*\$CATEGORY:|^\s*::.*?::|\{[^{}]*\}", re.MULTILINE | re.DOTALL)


def formato_por_contenido(texto: str) -> str | None:
    """'gift' o 'xml' según el contenido, sin mirar la extensión (None si no se reconoce)."""
    texto = texto.lstrip("﻿")
    if _XML_MOODLE.match(texto) or texto.lstrip().startswith("<?xml"):
        return "xml"
    if _GIFT.search(texto):
        return "gift"
    return None


def buscar_archivos(directorio: str | Path, recursivo: bool = True,
                    extensiones: Iterable[str] = EXTENSIONES) -> list[Path]:
    """Archivos de preguntas del directorio, ordenados (se ignoran los ocultos)."""
    from voight.core.configuracion import cargar, ignorado

    directorio = Path(directorio)
    patron = "**/*" if recursivo else "*"
    extensiones = tuple(e.lower() for e in extensiones)
    config = cargar([directorio])  # [general] ignorar del .voight.toml del banco
    return sorted(
        p for p in directorio.glob(patron)
        if p.is_file() and p.suffix.lower() in extensiones
        and not any(parte.startswith(".") for parte in p.relative_to(directorio).parts)
        and not ignorado(p, config)
    )


def expandir_rutas(rutas: Iterable[str | Path], recursivo: bool,
                   extensiones: Iterable[str] = EXTENSIONES) -> list[Path]:
    """Archivos sueltos tal cual y directorios expandidos con `buscar_archivos`."""
    archivos: list[Path] = []
    for ruta in rutas:
        ruta = Path(ruta)
        if ruta.is_dir():
            archivos.extend(buscar_archivos(ruta, recursivo, extensiones))
        elif ruta.is_file():
            archivos.append(ruta)
    return archivos


def parse_archivo(ruta: str | Path) -> dict:
    """Parsea un archivo GIFT o XML; el resultado lleva también `formato`."""
    formato = formato_de(ruta)
    if formato == "xml":
        resultado = parse_xml_file(ruta)
    else:
        resultado = parse_gift_file(str(ruta))
        formato = "gift"
    resultado["formato"] = formato
    return resultado


def _git(cwd: Path, *args: str) -> str:
    import subprocess

    r = subprocess.run(
        ["git", "-c", "core.quotePath=false", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if r.returncode != 0:
        raise ValueError(f"git {' '.join(args)}: {r.stderr.strip() or 'falló'}")
    return r.stdout


def archivos_cambiados(desde: str, rutas: Optional[Iterable[str | Path]] = ()) -> set:
    """Archivos de preguntas cambiados desde la revisión git `desde` (incluye los nuevos
    sin seguimiento), como rutas absolutas. Error si las rutas no están en un repo git."""
    if not desde or not desde.strip():
        raise ValueError("La revisión git `desde` no puede estar vacía.")

    carpetas = [Path(r) for r in (rutas or ())] or [Path.cwd()]
    cambiados: set[Path] = set()
    raices_vistas: set[Path] = set()

    for carpeta in carpetas:
        base = carpeta.resolve()
        base = base if base.is_dir() else base.parent
        raiz = Path(_git(base, "rev-parse", "--show-toplevel").strip()).resolve()
        if raiz in raices_vistas:
            continue
        raices_vistas.add(raiz)

        # Validar revisión antes de invocar diff (evita inyección de flags como `-p`).
        _git(raiz, "rev-parse", "--verify", "--end-of-options", f"{desde}^{{commit}}")
        # -z y core.quotePath=false devuelven rutas UTF-8 sin comillas ni escapes octales.
        salida_diff = _git(
            raiz, "diff", "--name-only", "-z", "--diff-filter=d", "--end-of-options", desde, "--"
        )
        salida_otros = _git(
            raiz, "ls-files", "--others", "--exclude-standard", "--full-name", "-z", "--", "."
        )
        nombres = [n for n in (*salida_diff.split("\x00"), *salida_otros.split("\x00")) if n]
        cambiados.update((raiz / n).resolve() for n in nombres if Path(n).suffix.lower() in EXTENSIONES)

    return cambiados


def filtrar_desde(archivos: Iterable[Path], desde: Optional[str], rutas: Optional[Iterable[str | Path]] = ()) -> list:
    """Los archivos que cambiaron desde `desde` (todos si `desde` es None)."""
    archivos = list(archivos)
    if not desde:
        return archivos
    cambiados = archivos_cambiados(desde, rutas)
    return [a for a in archivos if Path(a).resolve() in cambiados]
