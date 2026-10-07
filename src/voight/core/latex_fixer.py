"""Corrector de fórmulas matemáticas LaTeX mal delimitadas en preguntas Moodle."""

from __future__ import annotations

import re


def corregir_delimitadores_latex(texto: str) -> str:
    """Reemplaza delimitadores inconsistentes (como $$ o \\( \\)) por el formato estándar de Moodle \\( ... \\)."""
    # Corregir fórmulas en bloque $$ ... $$ a formato centrado
    texto_corregido = re.sub(r'\$\$(.+?)\$\$', r'\\[ \1 \\]', texto, flags=re.DOTALL)
    # Corregir fórmulas inline $ ... $ a \( ... \) evitando signos de dólar comunes
    texto_corregido = re.sub(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)', r'\\( \1 \\)', texto_corregido)
    return texto_corregido
