"""Formato del código de las preguntas con clang-format (C y Java) o con gaff (C).

Cada bloque ``` se restaura a ASCII, se formatea y se vuelve a escribir con la
convención que tenía: si estaba protegido (fullwidth, con o
sin marcas · y ↵) se vuelve a proteger igual; en GIFT sin proteger se escapa lo que
GIFT interpretaría. Un bloque que el formateador no puede formatear queda como estaba.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Collection, List, Optional

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


def formatear_bloques(
    texto: str,
    contexto: str,
    formatear_bloque: Callable[[str, str], Optional[str]],
    lenguajes: Collection[str] = tuple(_EXTENSION),
) -> tuple:
    """Formatea los bloques ``` de los lenguajes indicados. (texto, bloques cambiados).

    `formatear_bloque(codigo_ascii, lenguaje)` devuelve el código formateado o None si no
    pudo; el bloque se vuelve a proteger con la convención que tenía (fullwidth y marcas).
    """
    cambios = 0

    def bloque(m: re.Match) -> str:
        nonlocal cambios
        etiqueta, codigo = m.group(1).strip().lower(), m.group(2)
        lenguaje = etiqueta if etiqueta in _EXTENSION else (detectar_lenguaje(codigo) if not etiqueta else None)
        if lenguaje is None or lenguaje not in lenguajes:
            return m.group(0)
        fullwidth, marcas = usa_convencion(m.group(0), contexto)
        plano = _ESCAPE_GIFT.sub(r"\1", codigo) if contexto == "gift" else codigo
        plano = transformar_fragmento(plano, contexto="xml", fullwidth=False)
        formateado = formatear_bloque(plano, lenguaje)
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


def formatear_texto(texto: str, contexto: str, comando: List[str], estilo: str = ESTILO) -> tuple:
    """Formatea los bloques de C/Java del texto con clang-format. (texto, bloques cambiados)."""
    return formatear_bloques(texto, contexto, lambda codigo, lenguaje: formatear(codigo, lenguaje, comando, estilo))


def formatear_archivo(contenido: str, formato: str, comando: List[str], estilo: str = ESTILO) -> tuple:
    if formato == "xml":
        return transformar_textos_xml(contenido, lambda t: formatear_texto(t, "xml", comando, estilo))
    return formatear_texto(contenido, "gift" if formato == "gift" else "xml", comando, estilo)


# ---------------------------------------------------------------------------
# gaff: el estilo de la cátedra (Allman, 4 espacios, espaciado de las reglas 0x00XXh)
# ---------------------------------------------------------------------------

# 0x2003h agrega esqueletos Doxygen «[completar: …]»: en una pregunta no corresponden.
_GAFF_EXCLUIDAS = "0x2003h"


def comando_gaff() -> Optional[List[str]]:
    return ["gaff"] if shutil.which("gaff") else None


def formatear_con_gaff(codigo: str, comando: List[str]) -> Optional[str]:
    """`gaff fix` sobre el código (como pregunta.c), respetando los comentarios (--idkfa)."""
    with tempfile.TemporaryDirectory() as directorio:
        ruta = Path(directorio) / "pregunta.c"
        ruta.write_text(codigo, encoding="utf-8")
        try:
            r = subprocess.run([*comando, "fix", str(ruta), "-e", _GAFF_EXCLUIDAS, "--idkfa"],
                               capture_output=True, text=True, timeout=120)
        except (subprocess.TimeoutExpired, OSError):
            return None
        if r.returncode != 0:
            return None
        return ruta.read_text(encoding="utf-8")


def formatear_archivo_gaff(contenido: str, formato: str, comando: List[str]) -> tuple:
    """Formatea con gaff los bloques ``` de C de un GIFT o Moodle XML. (contenido, bloques cambiados)."""
    def con_gaff(texto: str, contexto: str) -> tuple:
        return formatear_bloques(texto, contexto, lambda codigo, _lenguaje: formatear_con_gaff(codigo, comando),
                                 lenguajes=("c", "h"))

    if formato == "xml":
        return transformar_textos_xml(contenido, lambda t: con_gaff(t, "xml"))
    return con_gaff(contenido, "gift" if formato == "gift" else "xml")
