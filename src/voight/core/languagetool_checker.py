"""Módulo de verificación y corrección ortográfica en moodle-toolbox — Delegado a myst-tools."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Set, Tuple, Dict, Any

try:
    from myst_tools.languagetool_checker import (
        DEFAULT_LANGUAGETOOL_URL,
        DEFAULT_LANGUAGETOOL_PREMIUM_URL,
        LOCAL_LANGUAGETOOL_URL,
        PALABRAS_IGNORADAS_DEFAULT,
        LanguageToolIssue,
        consultar_languagetool,
        analizar_texto_languagetool,
        aplicar_autofix_archivo,
        generar_reporte_markdown as generar_reporte_markdown_languagetool,
    )
except ImportError as error:  # sin el extra `languagetool` (myst-tools)
    raise ModuleNotFoundError(
        "La revisión con LanguageTool usa myst-tools, que no está instalado. Instalá moodle-toolbox con el "
        "extra languagetool: uv tool install \"questions[languagetool] @ git+https://github.com/INGCOM-UNRN/moodle-toolbox\"",
        name="myst_tools",
    ) from error

# API de myst-tools que este módulo reexporta para el resto del paquete y los tests.
__all__ = [
    "DEFAULT_LANGUAGETOOL_URL", "DEFAULT_LANGUAGETOOL_PREMIUM_URL", "LOCAL_LANGUAGETOOL_URL",
    "PALABRAS_IGNORADAS_DEFAULT", "LanguageToolIssue", "consultar_languagetool", "analizar_texto_languagetool",
    "aplicar_autofix_archivo", "generar_reporte_markdown_languagetool",
]


def enmascarar_gift_xml(contenido: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Enmascara etiquetas XML/HTML, sintaxis GIFT, fórmulas LaTeX y bloques de código."""
    enmascarado = list(contenido)
    mascaras = []

    def _mask_range(start: int, end: int, preserve_newlines: bool = True):
        for i in range(start, end):
            if preserve_newlines and enmascarado[i] == '\n':
                continue
            enmascarado[i] = ' '
        mascaras.append({"start": start, "end": end})

    # 1. Etiquetas XML / HTML <...>
    for m in re.finditer(r'<[^>\n]+>', contenido):
        _mask_range(m.start(), m.end())

    # 2. Bloques CDATA <![CDATA[ ... ]]>
    for m in re.finditer(r'<!\[CDATA\[', contenido):
        _mask_range(m.start(), m.end())
    for m in re.finditer(r'\]\]>', contenido):
        _mask_range(m.start(), m.end())

    # 3. Fórmulas LaTeX \( ... \), \[ ... \], $$ ... $$, $ ... $
    for m in re.finditer(r'\\\(.*?\\\)', contenido, re.DOTALL):
        _mask_range(m.start(), m.end())
    for m in re.finditer(r'\\\[.*?\\\]', contenido, re.DOTALL):
        _mask_range(m.start(), m.end())
    for m in re.finditer(r'\$\$.*?\$\$', contenido, re.DOTALL):
        _mask_range(m.start(), m.end())
    for m in re.finditer(r'\$[^\$\n]+\$', contenido):
        _mask_range(m.start(), m.end())

    # 4. Sintaxis de preguntas GIFT { ... }
    for m in re.finditer(r'\{[^\}]+\}', contenido):
        _mask_range(m.start(), m.end())

    # 5. Títulos GIFT ::Título::
    for m in re.finditer(r'::[^:\n]+::', contenido):
        _mask_range(m.start(), m.end())

    # 6. Código C inline o en bloque
    for m in re.finditer(r'(```|~~~)[^\n]*\n.*?\n\s*\1', contenido, re.DOTALL):
        _mask_range(m.start(), m.end())
    for m in re.finditer(r'`[^`\n]+`', contenido):
        _mask_range(m.start(), m.end())

    return "".join(enmascarado), mascaras


def analizar_archivo_languagetool(
    file_path: Path,
    lang: str = "es-AR",
    server_url: Optional[str] = None,
    username: Optional[str] = None,
    api_key: Optional[str] = None,
    premium: bool = False,
    ignore_words: Optional[Set[str]] = None,
    ignore_rules: Optional[Set[str]] = None,
) -> List[LanguageToolIssue]:
    """Analiza ortografía en bancos de preguntas GIFT o XML enmascarando sintaxis propia."""
    if not file_path.is_file():
        return []

    contenido = file_path.read_text(encoding="utf-8", errors="replace")
    issues = analizar_texto_languagetool(
        contenido,
        file_path=file_path,
        pregunta_id=file_path.stem,
        campo="cuerpo",
        lang=lang,
        server_url=server_url,
        username=username,
        api_key=api_key,
        premium=premium,
        ignore_words=ignore_words,
        ignore_rules=ignore_rules,
        custom_mask_fn=enmascarar_gift_xml,
    )
    for iss in issues:
        iss.pregunta_id = file_path.stem
        iss.campo = "cuerpo"
    return issues


# Alias retrocompatibles
analizar_archivo_banco = analizar_archivo_languagetool
aplicar_autofix_archivo_banco = aplicar_autofix_archivo

