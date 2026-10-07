"""Unificación de árboles y colecciones de archivos de preguntas (GIFT y Moodle XML).

Opuesto a split / export: recorre directorios y/o archivos individuales,
agrupa preguntas preservando sus jerarquías de categorías ($CATEGORY en GIFT,
<question type="category"> en XML), y produce un único archivo monolítico unificado.
"""

import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

from voight.core.converter import _cdata_sub
from voight.core.formatter import _bloques_gift
from voight.core.tree import (
    _protect_backslashes_in_code,
    serializar_quiz,
)


def unificar_gift(
    rutas: Sequence[Union[str, Path]],
    archivo_salida: Path,
    recursivo: bool = True,
    eliminar_origen: bool = False,
) -> int:
    """Unifica múltiples archivos y/o directorios GIFT en un único archivo monolítico.

    Preserva la estructura de categorías deducida de los subdirectorios relativos
    y/o las directivas $CATEGORY ya presentes en los archivos.
    """
    archivos_gift: List[Tuple[str, Path]] = []

    for p in rutas:
        path = Path(p)
        if path.is_file() and path.suffix.lower() == ".gift":
            archivos_gift.append(("", path))
        elif path.is_dir():
            pattern = "**/*.gift" if recursivo else "*.gift"
            for f in sorted(path.glob(pattern)):
                if f.is_file() and not f.name.startswith("."):
                    rel = str(f.relative_to(path).parent)
                    rel = "" if rel == "." else rel.replace(os.sep, "/")
                    archivos_gift.append((rel, f))

    if not archivos_gift:
        return 0

    # Si hay un único directorio raíz en la invocación y no se especificó archivo suelto
    lineas_salida: List[str] = []
    current_category: Optional[str] = None
    question_count = 0
    archivos_procesados: List[Path] = []

    for cat_rel, filepath in archivos_gift:
        content = filepath.read_text(encoding="utf-8")
        bloques = [b.strip() for b in _bloques_gift(content) if b.strip()]

        for bloque in bloques:
            cat_match = re.search(r"^\$CATEGORY:\s*(.*)", bloque, flags=re.MULTILINE)
            if cat_match:
                cat_declarada = cat_match.group(1).strip()
                current_category = cat_declarada
                lineas_salida.append(f"\n$CATEGORY: {cat_declarada}\n")
                # Si es un bloque que solo define categoría, continuamos
                if not re.search(r"::.*?::", bloque, re.DOTALL):
                    continue

            # Si el bloque no trajo $CATEGORY explícito, usamos la categoría inferida por la carpeta
            if cat_rel and cat_rel != current_category:
                current_category = cat_rel
                lineas_salida.append(f"\n$CATEGORY: $course$/{cat_rel}\n")

            bloque_protegido = _protect_backslashes_in_code(bloque)
            lineas_salida.append(bloque_protegido.strip() + "\n")
            question_count += 1

        archivos_procesados.append(filepath)

    archivo_salida.parent.mkdir(parents=True, exist_ok=True)
    archivo_salida.write_text("\n".join(lineas_salida).strip() + "\n", encoding="utf-8")

    if eliminar_origen:
        for f in archivos_procesados:
            if f.resolve() != archivo_salida.resolve():
                f.unlink(missing_ok=True)

    return question_count


def unificar_xml(
    rutas: Sequence[Union[str, Path]],
    archivo_salida: Path,
    recursivo: bool = True,
    eliminar_origen: bool = False,
) -> int:
    """Unifica múltiples archivos y/o directorios Moodle XML en un único archivo XML monolítico.

    Preserva las categorías de carpetas y las etiquetas de categoría internas.
    """
    archivos_xml: List[Tuple[str, Path]] = []

    for p in rutas:
        path = Path(p)
        if path.is_file() and path.suffix.lower() == ".xml":
            archivos_xml.append(("", path))
        elif path.is_dir():
            pattern = "**/*.xml" if recursivo else "*.xml"
            for f in sorted(path.glob(pattern)):
                if f.is_file() and not f.name.startswith("."):
                    rel = str(f.relative_to(path).parent)
                    rel = "" if rel == "." else rel.replace(os.sep, "/")
                    archivos_xml.append((rel, f))

    if not archivos_xml:
        return 0

    quiz_root = ET.Element("quiz")
    current_category: Optional[str] = None
    question_count = 0
    archivos_procesados: List[Path] = []

    for cat_rel, filepath in archivos_xml:
        if filepath.resolve() == archivo_salida.resolve():
            continue

        try:
            tree = ET.parse(filepath)
        except (ET.ParseError, UnicodeDecodeError) as e:
            print(f"Error interpretando {filepath}: {e}", file=sys.stderr)
            continue

        for question in tree.getroot().findall("question"):
            qtype = question.get("type")
            if qtype == "category":
                texto = question.find("category/text")
                if texto is not None and texto.text:
                    current_category = texto.text.strip()
                    quiz_root.append(question)
                continue

            if cat_rel and cat_rel != current_category:
                current_category = cat_rel
                cat_q = ET.SubElement(quiz_root, "question", {"type": "category"})
                cat = _cdata_sub(cat_q, "category")
                ruta_cat = f"$course$/{cat_rel}" if cat_rel else "$course$"
                _cdata_sub(cat, "text", ruta_cat)

            quiz_root.append(question)
            question_count += 1

        archivos_procesados.append(filepath)

    xml = serializar_quiz(quiz_root)
    archivo_salida.parent.mkdir(parents=True, exist_ok=True)
    archivo_salida.write_text(xml, encoding="utf-8")

    if eliminar_origen:
        for f in archivos_procesados:
            if f.resolve() != archivo_salida.resolve():
                f.unlink(missing_ok=True)

    return question_count


def unificar(
    rutas: Sequence[Union[str, Path]],
    archivo_salida: Path,
    formato: Optional[str] = None,
    recursivo: bool = True,
    eliminar_origen: bool = False,
) -> int:
    """Unifica árboles o colecciones de preguntas al formato especificado o deducido de la salida."""
    fmt = (formato or (archivo_salida.suffix.lower().lstrip(".") if archivo_salida.suffix else "gift")).lower()
    if fmt == "gift":
        return unificar_gift(rutas, archivo_salida, recursivo=recursivo, eliminar_origen=eliminar_origen)
    elif fmt == "xml":
        return unificar_xml(rutas, archivo_salida, recursivo=recursivo, eliminar_origen=eliminar_origen)
    else:
        raise ValueError(f"Formato no soportado: {fmt}. Debe ser 'gift' o 'xml'.")
