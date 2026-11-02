"""Revisión de texto alternativo en imágenes HTML y Markdown."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any


class _Imagenes(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.alternativos: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "img":
            self.alternativos.append(dict(attrs).get("alt") or "")


def validar_accesibilidad_imagenes(
    contenido_html: str, formato: str = "html"
) -> dict[str, Any]:
    """Cuenta imágenes sin texto alternativo; no certifica accesibilidad integral."""
    contenido = contenido_html
    alternativos: list[str] = []
    if formato == "markdown":
        contenido = re.sub(
            r"(?ms)^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?^[ \t]*\1[^\n]*$", "", contenido
        )
        contenido = re.sub(r"(`+).*?\1", "", contenido, flags=re.DOTALL)
        imagenes = re.compile(r"!\[([^]\n]*)\](?:\([^\n]*?\)|\[[^]\n]*\])")
        alternativos.extend(
            coincidencia.group(1) for coincidencia in imagenes.finditer(contenido)
        )
        contenido = imagenes.sub("", contenido)
    parser = _Imagenes()
    parser.feed(contenido)
    alternativos.extend(parser.alternativos)
    total = len(alternativos)
    faltantes = sum(not texto.strip() for texto in alternativos)
    return {
        "total_imagenes": total,
        "imagenes_sin_alt": faltantes,
        "accesible": faltantes == 0,
        "porcentaje_conformidad": 100.0
        if total == 0
        else round((total - faltantes) / total * 100, 1),
    }


def _textos(valor: Any, ruta: str = ""):
    if isinstance(valor, dict):
        if isinstance(valor.get("text"), str):
            yield ruta, valor["text"], valor.get("format", "html")
        for clave, hijo in valor.items():
            if clave == "subanswer" and isinstance(hijo, str):
                yield f"{ruta}.{clave}", hijo, "html"
            elif clave != "text" or not isinstance(hijo, str):
                yield from _textos(hijo, f"{ruta}.{clave}" if ruta else clave)
    elif isinstance(valor, list):
        for indice, hijo in enumerate(valor):
            yield from _textos(hijo, f"{ruta}.{indice}")


def auditar_accesibilidad(preguntas: list[dict]) -> dict:
    imagenes, faltantes, hallazgos = 0, 0, []
    for pregunta in preguntas:
        # Sólo campos de contenido, evitando volver a contar XML crudo o metadatos.
        campos = {
            clave: pregunta[clave]
            for clave in (
                "stem",
                "choices",
                "globalFeedback",
                "trueFeedback",
                "falseFeedback",
                "matchPairs",
            )
            if clave in pregunta
        }
        for campo, texto, formato in _textos(campos):
            res = validar_accesibilidad_imagenes(texto, formato)
            imagenes += res["total_imagenes"]
            faltantes += res["imagenes_sin_alt"]
            if not res["accesible"]:
                hallazgos.append(
                    {
                        "archivo": pregunta["archivo"],
                        "titulo": pregunta.get("title", ""),
                        "indice": pregunta["indice"],
                        "campo": campo,
                        "imagenes_sin_alt": res["imagenes_sin_alt"],
                    }
                )
    return {
        "ok": faltantes == 0,
        "preguntas": len(preguntas),
        "total_imagenes": imagenes,
        "imagenes_sin_alt": faltantes,
        "hallazgos": hallazgos,
    }
