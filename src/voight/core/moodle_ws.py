"""Subida de preguntas a Moodle por servicio web.

Moodle estándar no tiene un servicio web para importar preguntas; esto usa el plugin
local "Question Web Service Import" (local_questions_importer_ws,
https://moodle.org/plugins/local_questions_importer_ws), que expone
`local_questions_importer_ws_import_xml(courseid, draftitemid)`:

1. el Moodle XML se sube al área de borradores del usuario con
   `webservice/upload.php` (estándar de Moodle), que devuelve el `itemid`;
2. se llama a la función del plugin con el curso y ese `itemid`; el plugin crea las
   categorías del XML y guarda las preguntas en el contexto del curso.

El token es el de un usuario con permiso de importar preguntas en el curso, con el
servicio web que incluye esa función habilitado.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Optional

FUNCION = "local_questions_importer_ws_import_xml"


def resolver_token(token: Optional[str] = None) -> Optional[str]:
    if token:
        return token
    from voight.core.config import _leer

    return os.environ.get("MOODLE_TOKEN") or _leer("MOODLE_TOKEN")


def _multipart(campos: dict, archivo: tuple) -> tuple:
    """Cuerpo multipart/form-data con los campos de texto y un archivo (nombre, bytes)."""
    limite = uuid.uuid4().hex
    partes = []
    for nombre, valor in campos.items():
        partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{nombre}"\r\n\r\n{valor}\r\n'.encode())
    nombre_archivo, contenido = archivo
    partes.append(
        f'--{limite}\r\nContent-Disposition: form-data; name="file_1"; filename="{nombre_archivo}"\r\n'
        f"Content-Type: application/xml\r\n\r\n".encode() + contenido + b"\r\n")
    partes.append(f"--{limite}--\r\n".encode())
    return b"".join(partes), f"multipart/form-data; boundary={limite}"


def _pedir(pedido: urllib.request.Request, timeout: int):
    try:
        with urllib.request.urlopen(pedido, timeout=timeout) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Moodle respondió {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"No se pudo contactar a Moodle: {e.reason}") from None
    except ValueError:
        raise RuntimeError("Moodle no devolvió JSON (¿la URL es la del sitio?)") from None
    if isinstance(datos, dict) and ("exception" in datos or "error" in datos):
        mensaje = datos.get("message") or datos.get("error") or datos.get("exception")
        raise RuntimeError(f"Moodle: {mensaje} ({datos.get('errorcode', 'sin código')})")
    return datos


def subir_borrador(url: str, token: str, nombre: str, contenido: bytes, timeout: int = 120) -> int:
    """Sube el archivo al área de borradores del usuario; devuelve el itemid."""
    cuerpo, tipo = _multipart({"token": token, "filearea": "draft", "itemid": "0"}, (nombre, contenido))
    pedido = urllib.request.Request(url.rstrip("/") + "/webservice/upload.php", data=cuerpo,
                                    method="POST", headers={"Content-Type": tipo})
    datos = _pedir(pedido, timeout)
    if not isinstance(datos, list) or not datos or "itemid" not in datos[0]:
        raise RuntimeError(f"Respuesta inesperada de webservice/upload.php: {str(datos)[:200]}")
    return int(datos[0]["itemid"])


def importar(url: str, token: str, curso: int, itemid: int, timeout: int = 600):
    """Llama a la función del plugin; devuelve su respuesta (JSON) tal cual."""
    cuerpo = urllib.parse.urlencode({
        "wstoken": token, "wsfunction": FUNCION, "moodlewsrestformat": "json",
        "courseid": curso, "draftitemid": itemid,
    }).encode()
    pedido = urllib.request.Request(url.rstrip("/") + "/webservice/rest/server.php", data=cuerpo, method="POST",
                                    headers={"Content-Type": "application/x-www-form-urlencoded"})
    return _pedir(pedido, timeout)


def preparar_xml(rutas: list, recursivo: bool = True) -> tuple:
    """(nombre, bytes del Moodle XML, cantidad de archivos) a partir de GIFT/XML sueltos o árboles.

    Un único .xml se sube tal cual; lo demás se unifica (las carpetas se vuelven
    categorías) y, si es GIFT, se convierte.
    """
    import tempfile

    from voight.core.banco import expandir_rutas
    from voight.core.converter import gift_to_xml
    from voight.core.unifier import unificar

    archivos = expandir_rutas(rutas, recursivo)
    if not archivos:
        raise ValueError("No se encontraron archivos de preguntas (.gift / .xml).")
    if len(archivos) == 1 and archivos[0].suffix.lower() == ".xml":
        return archivos[0].name, archivos[0].read_bytes(), 1
    with tempfile.TemporaryDirectory(prefix="questions-subir-") as tmp:
        gifts = [a for a in archivos if a.suffix.lower() == ".gift"]
        xmls = [a for a in archivos if a.suffix.lower() == ".xml"]
        partes = []
        if gifts:
            destino = Path(tmp) / "gift.gift"
            unificar(rutas if not xmls else gifts, destino, formato="gift", recursivo=recursivo)
            partes.append(gift_to_xml(destino.read_text(encoding="utf-8")))
        if xmls:
            destino = Path(tmp) / "xml.xml"
            unificar(rutas if not gifts else xmls, destino, formato="xml", recursivo=recursivo)
            partes.append(destino.read_text(encoding="utf-8"))
    if len(partes) == 1:
        return "preguntas.xml", partes[0].encode("utf-8"), len(archivos)
    # GIFT y XML mezclados: un único <quiz> con las preguntas de ambos.
    import xml.etree.ElementTree as ET

    from voight.core.tree import serializar_quiz

    quiz = ET.Element("quiz")
    for parte in partes:
        quiz.extend(ET.fromstring(parte).findall("question"))
    return "preguntas.xml", serializar_quiz(quiz).encode("utf-8"), len(archivos)
