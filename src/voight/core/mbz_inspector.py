"""Inspección de metadatos MBZ (tar o ZIP), sin extraer ni restaurar archivos."""

from __future__ import annotations

import json
import math
import tarfile
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Iterator

MAX_XML = 64 * 1024 * 1024
MAX_TOTAL_XML = 128 * 1024 * 1024
MAX_ENTRADAS = 100_000


def _nombre(nombre: str) -> str:
    ruta = PurePosixPath(nombre)
    if ruta.is_absolute() or ".." in ruta.parts or "\\" in nombre:
        raise ValueError(f"Ruta inválida dentro del MBZ: {nombre!r}.")
    return ruta.as_posix()


def _necesario(nombre: str) -> bool:
    return (
        nombre == "moodle_backup.xml"
        or nombre.endswith("questions.xml")
        or (nombre.startswith("activities/") and nombre.endswith("/quiz.xml"))
    )


def _leer_xml(nombre: str, stream) -> ET.Element:
    contenido = stream.read(MAX_XML + 1)
    if len(contenido) > MAX_XML:
        raise ValueError(f"{nombre}: XML mayor que 64 MiB.")
    normalizado = contenido.replace(b"\x00", b"").upper()
    if b"<!DOCTYPE" in normalizado or b"<!ENTITY" in normalizado:
        raise ValueError(f"{nombre}: no se admiten DTD ni entidades declaradas.")
    try:
        return ET.fromstring(contenido)
    except ET.ParseError as exc:
        raise ValueError(f"{nombre}: XML inválido: {exc}") from exc


def _xmls(archivo: Path) -> Iterator[tuple[str, ET.Element]]:
    vistos: set[str] = set()
    total = 0
    if zipfile.is_zipfile(archivo):
        with zipfile.ZipFile(archivo) as paquete:
            entradas = paquete.infolist()
            if len(entradas) > MAX_ENTRADAS:
                raise ValueError("El MBZ supera las 100000 entradas.")
            for entrada in entradas:
                nombre = _nombre(entrada.filename)
                if entrada.is_dir():
                    continue
                if nombre in vistos:
                    raise ValueError(f"Entrada duplicada en el MBZ: {nombre}.")
                vistos.add(nombre)
                if not _necesario(nombre):
                    continue
                total += entrada.file_size
                if entrada.file_size > MAX_XML or total > MAX_TOTAL_XML:
                    raise ValueError(
                        "El XML del MBZ supera los límites de inspección (64/128 MiB)."
                    )
                with paquete.open(entrada) as stream:
                    yield nombre, _leer_xml(nombre, stream)
    else:
        with tarfile.open(archivo, "r:*") as paquete_tar:
            for numero, entrada_tar in enumerate(paquete_tar, 1):
                if numero > MAX_ENTRADAS:
                    raise ValueError("El MBZ supera las 100000 entradas.")
                nombre = _nombre(entrada_tar.name)
                if entrada_tar.isdir():
                    continue
                if nombre in vistos:
                    raise ValueError(f"Entrada duplicada en el MBZ: {nombre}.")
                vistos.add(nombre)
                if not _necesario(nombre):
                    continue
                if not entrada_tar.isfile():
                    raise ValueError(f"{nombre}: el XML debe ser un archivo regular.")
                total += entrada_tar.size
                if entrada_tar.size > MAX_XML or total > MAX_TOTAL_XML:
                    raise ValueError(
                        "El XML del MBZ supera los límites de inspección (64/128 MiB)."
                    )
                stream_tar = paquete_tar.extractfile(entrada_tar)
                if stream_tar is None:
                    raise ValueError(f"No se pudo leer {nombre}.")
                with stream_tar:
                    yield nombre, _leer_xml(nombre, stream_tar)


def _entero(texto: str | None, predeterminado: int = 0) -> int:
    try:
        return int(texto or predeterminado)
    except ValueError:
        return predeterminado


def _entero_opcional(texto: str | None) -> int | None:
    try:
        return int(texto) if texto is not None else None
    except ValueError:
        return None


def _nota(texto: str | None) -> float | None:
    try:
        valor = float(texto) if texto is not None else None
        return valor if valor is not None and math.isfinite(valor) else None
    except ValueError:
        return None


def _preguntas_categoria(categoria: ET.Element) -> tuple[list[ET.Element], int]:
    entradas = categoria.findall("question_bank_entries/question_bank_entry")
    if not entradas:
        preguntas = categoria.findall("questions/question")
        return preguntas, len(preguntas)
    preguntas, versiones = [], 0
    for entrada in entradas:
        candidatas = entrada.findall(".//question_versions")
        versiones += len(candidatas)
        candidatas = [v for v in candidatas if v.find("questions/question") is not None]
        if candidatas:
            ultima = max(candidatas, key=lambda v: _entero(v.findtext("version")))
            preguntas.extend(ultima.findall("questions/question"))
    return preguntas, versiones


def inspeccionar_mbz(archivo: str | Path) -> dict:
    archivo = Path(archivo)
    try:
        documentos = dict(_xmls(archivo))
    except (
        OSError,
        tarfile.TarError,
        zipfile.BadZipFile,
        EOFError,
        RuntimeError,
    ) as exc:
        raise ValueError(f"No se pudo leer el MBZ: {exc}") from exc
    manifiesto = documentos.get("moodle_backup.xml")
    if manifiesto is None or manifiesto.tag != "moodle_backup":
        raise ValueError("El archivo no contiene un moodle_backup.xml válido.")
    categorias, cuestionarios, avisos = [], [], []
    tipos: Counter[str] = Counter()
    total_versiones = 0
    for nombre, raiz in documentos.items():
        if not nombre.endswith("questions.xml"):
            continue
        for categoria in raiz.findall(".//question_category"):
            preguntas, versiones = _preguntas_categoria(categoria)
            por_tipo = Counter(q.findtext("qtype", "desconocido") for q in preguntas)
            tipos.update(por_tipo)
            total_versiones += versiones
            categorias.append(
                {
                    "id": categoria.get("id"),
                    "nombre": categoria.findtext("name", ""),
                    "padre": categoria.findtext("parent", "0"),
                    "preguntas": len(preguntas),
                    "versiones": versiones,
                    "tipos": dict(sorted(por_tipo.items())),
                }
            )
    nombres_categorias = {c["id"]: c["nombre"] for c in categorias}
    for nombre, raiz in documentos.items():
        if not nombre.startswith("activities/") or not nombre.endswith("/quiz.xml"):
            continue
        quiz = raiz.find("quiz") if raiz.tag != "quiz" else raiz
        if quiz is None:
            raise ValueError(f"{nombre}: falta el elemento quiz.")
        slots = quiz.findall("question_instances/question_instance")
        cupos: Counter[str] = Counter()
        aleatorios = 0
        for slot in slots:
            referencia = slot.find("question_set_reference")
            if referencia is not None:
                aleatorios += 1
                try:
                    filtro = json.loads(referencia.findtext("filtercondition", "{}"))
                    ids = filtro.get("filter", {}).get("category", {}).get("values", [])
                    if not isinstance(ids, list):
                        raise ValueError("categorías inválidas")
                    cupos[json.dumps(filtro, sort_keys=True)] += 1
                except (ValueError, TypeError, AttributeError):
                    avisos.append(
                        f"{nombre}: filtro de categoría no interpretable en slot "
                        f"{slot.findtext('slot', '?')}."
                    )
            elif slot.findtext("questioncategoryid") not in (None, "", "0", "$@NULL@$"):
                aleatorios += 1
                filtro_legacy = {
                    "filter": {
                        "category": {
                            "values": [slot.findtext("questioncategoryid", "")],
                            "filteroptions": {
                                "includesubcategories": (
                                    slot.findtext("includingsubcategories") == "1"
                                    if slot.findtext("includingsubcategories")
                                    in ("0", "1")
                                    else None
                                )
                            },
                        }
                    }
                }
                cupos[json.dumps(filtro_legacy, sort_keys=True)] += 1
        cuestionarios.append(
            {
                "archivo": nombre,
                "titulo": quiz.findtext("name", ""),
                "slots": len(slots),
                "aleatorios": aleatorios,
                "fijos": len(slots) - aleatorios,
                "tiempo_limite": _entero_opcional(quiz.findtext("timelimit")),
                "intentos": _entero_opcional(quiz.findtext("attempts_number")),
                "calificacion_maxima": _nota(quiz.findtext("grade")),
                "shuffle_respuestas": (
                    quiz.findtext("shuffleanswers") == "1"
                    if quiz.findtext("shuffleanswers") in ("0", "1")
                    else None
                ),
                "cupos": [
                    {
                        "categorias": [
                            {"id": cid, "nombre": nombres_categorias.get(cid)}
                            for cid in sorted(
                                str(valor)
                                for valor in filtro_cupo.get("filter", {})
                                .get("category", {})
                                .get("values", [])
                            )
                        ],
                        "slots": cantidad,
                        "filtro": filtro_cupo,
                    }
                    for serializado, cantidad in sorted(cupos.items())
                    for filtro_cupo in [json.loads(serializado)]
                ],
            }
        )
    if not any(nombre.endswith("questions.xml") for nombre in documentos):
        avisos.append(
            "La copia no incluye un questions.xml; no se puede inventariar el banco."
        )
    if not cuestionarios:
        avisos.append("La copia no incluye actividades de cuestionario.")
    return {
        "archivo": str(archivo),
        "moodle_release": manifiesto.findtext("information/moodle_release"),
        "backup_version": manifiesto.findtext("information/backup_version"),
        "tipo_backup": manifiesto.findtext("information/type"),
        "preguntas": sum(c["preguntas"] for c in categorias),
        "versiones": total_versiones,
        "tipos": dict(sorted(tipos.items())),
        "categorias": categorias,
        "cuestionarios": cuestionarios,
        "avisos": avisos,
    }
