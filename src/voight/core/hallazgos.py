"""Los hallazgos de `health` como elementos navegables y los arreglos automáticos disponibles.

`elementos(resultado, clave)` devuelve, para cada clave del resumen (errores y
advertencias), los elementos afectados con su archivo, título y un detalle legible.
`ARREGLOS` dice qué hallazgos tienen un arreglo automático (los mismos que hacen
`fix code-chars --to-fullwidth`, `fix code-lang` y `fix clean-html`) y
`arreglar` lo aplica a un archivo.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from voight.core.banco import formato_de


def _codigo(resultado, condicion) -> List[dict]:
    return [a for a in resultado["codigo"]["archivos"] if condicion(a)]


def _gift(a) -> bool:
    return formato_de(a["archivo"]) == "gift"


_LISTAS: Dict[str, Callable[[dict], List[dict]]] = {
    "archivos_ilegibles": lambda r: r["archivos"]["errores"],
    "fracciones_invalidas": lambda r: r["porcentajes"]["fracciones_invalidas"],
    "porcentajes_inconsistentes": lambda r: r["porcentajes"]["preguntas_inconsistentes"],
    "sin_correcta": lambda r: r["porcentajes"]["preguntas_sin_correcta"],
    "sin_enunciado": lambda r: r["estructura"]["preguntas_sin_enunciado"],
    "sin_respuestas": lambda r: r["estructura"].get("preguntas_sin_respuestas", []),
    "pocos_pares": lambda r: r["estructura"].get("preguntas_pocos_pares", []),
    "archivos_sin_preguntas": lambda r: [{"archivo": a} for a in r["archivos"].get("sin_preguntas", [])],
    "codigo_gift_sin_proteger": lambda r: _codigo(r, lambda a: _gift(a) and a["sin_proteger"]),
    "codigo_gift_lineas_vacias": lambda r: _codigo(r, lambda a: _gift(a) and a["lineas_vacias"]),
    "sin_feedback": lambda r: r["retroalimentacion"]["preguntas_sin_feedback"],
    "feedback_parcial": lambda r: r["retroalimentacion"]["preguntas_feedback_parcial"],
    "pocas_opciones": lambda r: r["opciones"]["preguntas_pocas_opciones"],
    "opciones_repetidas": lambda r: r["opciones"]["preguntas_opciones_repetidas"],
    "correcta_mas_larga": lambda r: r["longitud"]["preguntas_correcta_mas_larga"],
    "correcta_mas_corta": lambda r: r["longitud"]["preguntas_correcta_mas_corta"],
    "codigo_sin_cerrar": lambda r: r["estructura"]["preguntas_codigo_sin_cerrar"],
    "sin_titulo": lambda r: r["estructura"]["preguntas_sin_titulo"],
    "opciones_problematicas": lambda r: r.get("redaccion", {}).get("preguntas_opciones_problematicas", []),
    "negacion_sin_resaltar": lambda r: r.get("redaccion", {}).get("preguntas_negacion_sin_resaltar", []),
    "distractores_debiles": lambda r: r.get("redaccion", {}).get("preguntas_distractores_debiles", []),
    "metadatos_moodle": lambda r: r.get("moodle", {}).get("inconsistencias", []),
    "sin_niveles_altos": lambda r: r.get("clasificacion", {}).get("categorias_sin_niveles_altos", []),
    "codigo_xml_sin_proteger": lambda r: _codigo(r, lambda a: not _gift(a) and (a["sin_proteger"] or a["lineas_vacias"])),
    "marcas_no_canonicas": lambda r: _codigo(r, lambda a: a["variantes"]),
    "comentarios_en_codigo": lambda r: _codigo(r, lambda a: a.get("comentarios")),
    "codigo_sin_lenguaje": lambda r: _codigo(r, lambda a: a.get("sin_lenguaje")),
    "enlaces_sospechosos": lambda r: r["enlaces"]["urls_sospechosas"],
    "html_obsoleto": lambda r: r["html_obsoleto"],
}


def _detalle(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    partes = []
    for clave, valor in item.items():
        if clave in ("archivo", "titulo", "filepath"):
            continue
        partes.append(f"{clave}: {valor}")
    return " · ".join(partes)


def elementos(resultado: Dict[str, Any], clave: str) -> List[Dict[str, Any]]:
    """Elementos afectados por un hallazgo: archivo (o None), título y detalle."""
    lista = _LISTAS.get(clave)
    if lista is None:
        return []
    salida = []
    for item in lista(resultado):
        archivo = item.get("archivo") or item.get("filepath") if isinstance(item, dict) else None
        titulo = item.get("titulo") if isinstance(item, dict) else None
        salida.append({"archivo": archivo, "titulo": titulo, "detalle": _detalle(item)})
    return salida


def hallazgos(resultado: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Errores y advertencias del resumen, con `nivel` ('error' o 'advertencia') y si tienen arreglo."""
    resumen = resultado["resumen"]
    return ([{**h, "nivel": "error", "arreglo": h["clave"] in ARREGLOS} for h in resumen["errores"]]
            + [{**h, "nivel": "advertencia", "arreglo": h["clave"] in ARREGLOS} for h in resumen["advertencias"]])


# --- arreglos automáticos -----------------------------------------------------

def _proteger(contenido: str, formato: str) -> Tuple[str, int]:
    from voight.core.codigo import transformar_archivo

    return transformar_archivo(contenido, formato, fullwidth=True, espacios=True, saltos=True)


def _lenguaje(contenido: str, formato: str) -> Tuple[str, int]:
    from voight.core.codigo import etiquetar_lenguaje_archivo

    return etiquetar_lenguaje_archivo(contenido, formato)


def _html(contenido: str, formato: str) -> Tuple[str, int]:
    from voight.core.moodle_health import limpiar_html_archivo

    limpio = limpiar_html_archivo(contenido, formato)
    return limpio, int(limpio != contenido)


_PROTEGER = ("proteger el código (fullwidth con marcas · y ↵)", _proteger)
ARREGLOS: Dict[str, Tuple[str, Callable[[str, str], Tuple[str, int]]]] = {
    "codigo_gift_sin_proteger": _PROTEGER,
    "codigo_gift_lineas_vacias": _PROTEGER,
    "codigo_xml_sin_proteger": _PROTEGER,
    "comentarios_en_codigo": _PROTEGER,
    "marcas_no_canonicas": _PROTEGER,
    "codigo_sin_lenguaje": ("etiquetar el lenguaje de los bloques ```", _lenguaje),
    "html_obsoleto": ("limpiar el HTML obsoleto y los estilos inline", _html),
}


def arreglar(ruta: Path, clave: str, simular: bool = False) -> int:
    """Aplica a `ruta` el arreglo automático del hallazgo `clave`; devuelve cuántos cambios hizo."""
    if clave not in ARREGLOS:
        raise KeyError(f"El hallazgo {clave!r} no tiene arreglo automático.")
    _, funcion = ARREGLOS[clave]
    ruta = Path(ruta)
    contenido = ruta.read_text(encoding="utf-8")
    nuevo, cambios = funcion(contenido, formato_de(ruta) or "gift")
    if cambios and nuevo != contenido and not simular:
        ruta.write_text(nuevo, encoding="utf-8")
    return cambios if nuevo != contenido else 0


def archivos_de(resultado: Dict[str, Any], clave: str) -> List[Path]:
    """Archivos distintos afectados por un hallazgo, en orden."""
    vistos: Dict[str, None] = {}
    for e in elementos(resultado, clave):
        if e["archivo"]:
            vistos.setdefault(e["archivo"], None)
    return [Path(a) for a in vistos]


def linea_de(texto: str, titulo: Optional[str]) -> int:
    """Línea (0-based) donde aparece el título en el archivo, o 0."""
    if not titulo:
        return 0
    for i, linea in enumerate(texto.splitlines()):
        if titulo in linea:
            return i
    return 0
