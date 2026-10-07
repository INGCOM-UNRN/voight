"""Formato del código de las preguntas con clang-format (C y Java).

Cada bloque ``` de C o Java se restaura a ASCII, se formatea con clang-format y se
vuelve a escribir con la convención que tenía: si estaba protegido (fullwidth, con o
sin marcas · y ↵) se vuelve a proteger igual; en GIFT sin proteger se escapa lo que
GIFT interpretaría. Un bloque que clang-format no puede formatear queda como estaba.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from typing import List, Optional

from voight.core.codigo import (
    _ESCAPE_GIFT, _escapar_gift, _proteger_lineas_vacias, detectar_lenguaje, transformar_fragmento,
    transformar_textos_xml, usa_convencion,
)

# Regla 0x0005h de la cátedra: cuatro espacios por nivel.
ESTILO = "{BasedOnStyle: LLVM, IndentWidth: 4, ColumnLimit: 100, AllowShortFunctionsOnASingleLine: None}"
_FENCE = re.compile(r"```([^\n`]*)\n(.*?)```", re.S)
_EXTENSION = {"c": "c", "h": "c", "java": "java", "cpp": "cpp", "c++": "cpp"}


def comando_clang_format() -> Optional[List[str]]:
    """clang-format instalado o, si no, el paquete de PyPI vía uvx."""
    if shutil.which("clang-format"):
        return ["clang-format"]
    if shutil.which("uvx"):
        return ["uvx", "clang-format"]
    return None


def formatear(codigo: str, lenguaje: str, comando: List[str], estilo: str = ESTILO) -> Optional[str]:
    try:
        r = subprocess.run([*comando, f"--style={estilo}", f"--assume-filename=pregunta.{_EXTENSION[lenguaje]}"],
                           input=codigo, capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError):
        return None
    return r.stdout if r.returncode == 0 else None


def formatear_texto(texto: str, contexto: str, comando: List[str], estilo: str = ESTILO) -> tuple:
    """Formatea los bloques de C/Java del texto. (texto, bloques cambiados)."""
    cambios = 0

    def bloque(m: re.Match) -> str:
        nonlocal cambios
        etiqueta, codigo = m.group(1).strip().lower(), m.group(2)
        lenguaje = etiqueta if etiqueta in _EXTENSION else (detectar_lenguaje(codigo) if not etiqueta else None)
        if lenguaje not in _EXTENSION:
            return m.group(0)
        fullwidth, marcas = usa_convencion(m.group(0), contexto)
        plano = _ESCAPE_GIFT.sub(r"\1", codigo) if contexto == "gift" else codigo
        plano = transformar_fragmento(plano, contexto="xml", fullwidth=False)
        formateado = formatear(plano, lenguaje, comando, estilo)
        if formateado is None:
            return m.group(0)
        formateado = formateado.rstrip("\n") + "\n"
        if fullwidth:
            nuevo = transformar_fragmento(formateado, contexto=contexto, fullwidth=True, espacios=marcas, saltos=marcas,
                                          bloque=True)
        elif contexto == "gift":
            nuevo = _proteger_lineas_vacias(_escapar_gift(formateado))
        else:
            nuevo = formateado
        if nuevo == codigo:
            return m.group(0)
        cambios += 1
        return f"```{m.group(1)}\n{nuevo}```"

    return _FENCE.sub(bloque, texto), cambios


def formatear_archivo(contenido: str, formato: str, comando: List[str], estilo: str = ESTILO) -> tuple:
    if formato == "xml":
        return transformar_textos_xml(contenido, lambda t: formatear_texto(t, "xml", comando, estilo))
    return formatear_texto(contenido, "gift" if formato == "gift" else "xml", comando, estilo)
