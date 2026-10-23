"""
Módulo de auditoría de salud, higiene y estandarización para bancos Moodle (GIFT / XML).

Las auditorías de preguntas trabajan sobre el modelo unificado (el mismo para GIFT y
Moodle XML), así que un banco da el mismo diagnóstico en cualquiera de los dos formatos.

Incluye:
- Porcentajes de las opciones: suma de 100 %, al menos una respuesta de 100 % y
  fracciones que Moodle acepta al importar (las que no, hacen que se descarte la pregunta)
- Retroalimentación: general y por opción (cobertura y preguntas sin feedback)
- Cantidad de opciones: distribución, preguntas con pocas opciones y opciones repetidas
- Longitud relativa de las respuestas: la correcta notablemente más larga (o más corta)
  que los distractores es una pista para el estudiante
- Código: secciones sin proteger para GIFT, marcas no canónicas, líneas en blanco
- Enlaces inseguros o locales y etiquetas HTML obsoletas (con limpieza opcional)
- Optimizador de nombres con taxonomía y tema ([P1][Tema][B2])
- Conversor de codificación Windows-1252 a UTF-8 limpio
- Generador de reportes de salud en Markdown
"""
from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Dict, Iterable, List, Optional

from voight.core.banco import formato_de
from voight.core.codigo import diagnosticar_codigo, transformar_textos_xml
from voight.core.metadatos import NIVELES_BLOOM, codigo_bloom
from voight.core.moodle_xml import parse_xml
from voight.core.parser import parse_gift

# Fracciones que Moodle acepta al importar (question_bank::fraction_options_full);
# cualquier otra hace que la importación descarte la pregunta ("invalidgrade").
FRACCIONES_MOODLE = (
    100, 90, 83.33333, 80, 75, 70, 66.66667, 60, 50, 40, 33.33333, 30, 25, 20,
    16.66667, 14.28571, 12.5, 11.11111, 10, 5, 0,
)
_TOLERANCIA_FRACCION = 0.001  # en puntos porcentuales (Moodle: 1e-5 sobre la fracción)

MIN_OPCIONES = 3
MIN_PARES_MATCHING = 3
UMBRAL_LONGITUD = 1.5

_SIN_RESPUESTAS = ("Category", "Description", "Cloze")


# ---------------------------------------------------------------------------
# Utilidades sobre el modelo
# ---------------------------------------------------------------------------

def _texto(ft: Any) -> str:
    if isinstance(ft, dict):
        return ft.get("text") or ""
    return ft or ""


def _plano(texto: str) -> str:
    """Texto visible: sin etiquetas HTML ni backticks, con espacios colapsados."""
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    texto = texto.replace("`", "")
    return re.sub(r"\s+", " ", texto).strip()


def _fraccion(opcion: dict) -> float:
    if opcion.get("weight") is not None:
        return float(opcion["weight"])
    return 100.0 if opcion.get("is_correct") else 0.0


def _ref(pregunta: dict) -> Dict[str, str]:
    titulo = pregunta.get("title") or _plano(_texto(pregunta.get("stem")))[:60] or "<sin título>"
    ref = {"titulo": titulo}
    if pregunta.get("filepath"):
        ref["archivo"] = pregunta["filepath"]
    return ref


def _evaluables(preguntas: Iterable[dict]) -> List[dict]:
    return [p for p in preguntas if p.get("type") not in _SIN_RESPUESTAS]


def _fraccion_valida(valor: float) -> bool:
    return any(abs(abs(valor) - f) <= _TOLERANCIA_FRACCION for f in FRACCIONES_MOODLE)


# ---------------------------------------------------------------------------
# Auditorías sobre preguntas del modelo unificado (GIFT o XML)
# ---------------------------------------------------------------------------

def auditar_porcentajes(preguntas: Iterable[dict]) -> Dict[str, Any]:
    """Claves de corrección: suma de porcentajes, respuesta de 100 % y fracciones válidas.

    - Opción múltiple con una respuesta de 100 %: respuesta única (las demás pueden dar
      crédito parcial). Sin ninguna de 100 %: respuesta múltiple, y los porcentajes
      positivos deben sumar 100.
    - Respuesta corta y numérica: alguna respuesta tiene que valer 100 %.
    - Toda fracción debe estar entre las que Moodle acepta al importar.
    """
    inconsistentes, sin_correcta, invalidas = [], [], []
    revisadas = 0
    for p in preguntas:
        if p.get("type") not in ("MC", "Short", "Numerical"):
            continue
        opciones = p.get("choices", [])
        if not opciones:
            continue
        revisadas += 1
        fracciones = [_fraccion(o) for o in opciones]
        positivas = [f for f in fracciones if f > 0]
        suma = sum(positivas)
        hay_100 = any(abs(f - 100.0) < 0.01 for f in fracciones)

        if not positivas:
            sin_correcta.append(_ref(p))
        elif p.get("type") == "MC" and not hay_100 and abs(suma - 100.0) > 0.1:
            inconsistentes.append({**_ref(p), "suma_positivos": round(suma, 5), "porcentajes": fracciones})
        elif p.get("type") != "MC" and not hay_100:
            inconsistentes.append({**_ref(p), "suma_positivos": round(suma, 5), "porcentajes": fracciones,
                                   "motivo": "ninguna respuesta vale 100 %"})

        fuera = [f for f in fracciones if not _fraccion_valida(f)]
        if fuera:
            invalidas.append({**_ref(p), "fracciones": fuera})

    return {
        "ok": not (inconsistentes or sin_correcta or invalidas),
        "total_preguntas": revisadas,
        "preguntas_inconsistentes": inconsistentes,
        "preguntas_sin_correcta": sin_correcta,
        "fracciones_invalidas": invalidas,
    }


def auditar_feedback(preguntas: Iterable[dict]) -> Dict[str, Any]:
    """Cobertura de retroalimentación general y por opción."""
    evaluables = _evaluables(preguntas)
    sin_feedback, parcial = [], []
    con_global = opciones_total = opciones_con = 0

    for p in evaluables:
        tiene_global = bool(_texto(p.get("globalFeedback")).strip())
        con_global += tiene_global
        if p.get("type") == "TF":
            retros = [p.get("trueFeedback"), p.get("falseFeedback")]
        elif p.get("type") in ("MC", "Short", "Numerical"):
            retros = [o.get("feedback") for o in p.get("choices", [])]
        else:
            retros = []
        con = sum(1 for r in retros if _texto(r).strip())
        opciones_total += len(retros)
        opciones_con += con
        if not tiene_global and not con:
            sin_feedback.append(_ref(p))
        elif retros and con < len(retros):
            parcial.append({**_ref(p), "opciones_sin_feedback": len(retros) - con, "opciones": len(retros)})

    total = len(evaluables)
    return {
        "total_preguntas": total,
        "con_feedback_global": con_global,
        "sin_feedback_count": len(sin_feedback),
        "preguntas_sin_feedback": sin_feedback,
        "preguntas_feedback_parcial": parcial,
        "opciones_total": opciones_total,
        "opciones_con_feedback": opciones_con,
        "porcentaje_cobertura": round(((total - len(sin_feedback)) / total * 100) if total else 100.0, 1),
        "porcentaje_feedback_global": round((con_global / total * 100) if total else 100.0, 1),
        "porcentaje_opciones_con_feedback": round(
            (opciones_con / opciones_total * 100) if opciones_total else 100.0, 1),
    }


def auditar_opciones(preguntas: Iterable[dict], min_opciones: int = MIN_OPCIONES) -> Dict[str, Any]:
    """Cantidad de opciones por pregunta y opciones repetidas."""
    distribucion: Counter = Counter()
    pocas, repetidas = [], []
    for p in preguntas:
        tipo = p.get("type")
        if tipo == "MC":
            textos = [_plano(_texto(o.get("text"))).lower() for o in p.get("choices", [])]
            distribucion[len(textos)] += 1
            if len(textos) < min_opciones:
                pocas.append({**_ref(p), "opciones": len(textos), "tipo": tipo})
        elif tipo == "Matching":
            pares = p.get("matchPairs", [])
            if len(pares) < MIN_PARES_MATCHING:
                pocas.append({**_ref(p), "opciones": len(pares), "tipo": tipo})
            continue
        elif tipo == "Short":
            textos = [_plano(_texto(o.get("text"))).lower() for o in p.get("choices", [])]
        else:
            continue
        dup = sorted(t for t, n in Counter(t for t in textos if t).items() if n > 1)
        if dup:
            repetidas.append({**_ref(p), "repetidas": dup})

    total_mc = sum(distribucion.values())
    return {
        "minimo": min_opciones,
        "distribucion_mc": {str(k): v for k, v in sorted(distribucion.items())},
        "promedio_mc": round(sum(k * v for k, v in distribucion.items()) / total_mc, 2) if total_mc else 0,
        "preguntas_pocas_opciones": pocas,
        "preguntas_opciones_repetidas": repetidas,
    }


def auditar_longitudes(preguntas: Iterable[dict], umbral: float = UMBRAL_LONGITUD) -> Dict[str, Any]:
    """Longitud relativa de las respuestas en opción múltiple.

    Compara el largo medio de las respuestas correctas con el de los distractores:
    si la razón es >= `umbral` (o <= 1/umbral) la longitud delata la respuesta. A
    nivel banco, compara cuántas veces la correcta es la opción más larga con lo que
    se esperaría por azar (1/n por pregunta): un exceso indica un sesgo sistemático.
    """
    mas_larga, mas_corta = [], []
    revisadas = unica_mas_larga = 0
    esperado = 0.0
    for p in preguntas:
        if p.get("type") != "MC":
            continue
        opciones = [(len(_plano(_texto(o.get("text")))), _fraccion(o)) for o in p.get("choices", [])]
        correctas = [n for n, f in opciones if f > 0]
        distractores = [n for n, f in opciones if f <= 0]
        if not correctas or not distractores:
            continue
        revisadas += 1
        largo_c, largo_d = mean(correctas), mean(distractores)
        if largo_c and largo_d:
            razon = largo_c / largo_d
            item = {**_ref(p), "razon": round(razon, 2), "largo_correcta": round(largo_c, 1),
                    "largo_distractores": round(largo_d, 1)}
            if razon >= umbral:
                mas_larga.append(item)
            elif razon <= 1 / umbral:
                mas_corta.append(item)
        if len(correctas) == 1:
            esperado += 1 / len(opciones)
            if correctas[0] > max(distractores):
                unica_mas_larga += 1

    return {
        "umbral": umbral,
        "preguntas_revisadas": revisadas,
        "preguntas_correcta_mas_larga": mas_larga,
        "preguntas_correcta_mas_corta": mas_corta,
        "correcta_es_la_mas_larga": unica_mas_larga,
        "correcta_es_la_mas_larga_esperado": round(esperado, 1),
    }


def _backticks_desbalanceados(texto: str) -> bool:
    """Un ``` o un ` sin cerrar: el código se come el resto del texto (y en GIFT la
    transformación a fullwidth no puede saber dónde termina)."""
    from voight.core.codigo import backticks_sin_cerrar

    return backticks_sin_cerrar(texto)


_OPCION_PROBLEMATICA = re.compile(
    r"\b(todas las (anteriores|opciones( anteriores)?)|ninguna de las (anteriores|opciones)|ambas( son correctas)?"
    r"|las dos anteriores|[a-e] y [a-e]|all of the above|none of the above)\b", re.I)
_NEGACION = re.compile(
    r"\b(excepto|salvo|incorrect[ao]s?|fals[ao]s?|no\s+(?:es|son|corresponde|pertenece|representa|debe|puede|se))\b",
    re.I)
_RESALTADO = re.compile(r"\*\*[^*]+\*\*|__[^_]+__|<(strong|b|em|u)>.*?</\1>", re.I | re.S)


def _sin_resaltar(enunciado: str) -> List[str]:
    """Negaciones del enunciado escritas en minúscula y fuera de un resaltado."""
    resaltados = [m.span() for m in _RESALTADO.finditer(enunciado)]
    hallazgos = []
    for m in _NEGACION.finditer(enunciado):
        dentro = any(a <= m.start() and m.end() <= b for a, b in resaltados)
        palabra = m.group(0).split()[0]  # "NO es": lo resaltado es la negación
        if not dentro and palabra != palabra.upper():
            hallazgos.append(m.group(0))
    return hallazgos


def auditar_redaccion(preguntas: Iterable[dict]) -> Dict[str, Any]:
    """Señales de redacción de opción múltiple: posición de la correcta, opciones del tipo
    "todas las anteriores", negaciones sin resaltar y distractores mucho más cortos."""
    posiciones: Counter = Counter()
    esperado_primera = 0.0
    revisadas = sin_mezclar = 0
    problematicas, negativas, debiles = [], [], []
    for p in preguntas:
        if p.get("type") not in ("MC", "Short"):
            continue
        opciones = p.get("choices", [])
        textos = [_plano(_texto(o.get("text"))) for o in opciones]
        if p.get("type") == "MC" and opciones:
            revisadas += 1
            if str((p.get("moodle") or {}).get("shuffleanswers", "")).lower() in ("0", "false"):
                sin_mezclar += 1
            correctas = [i for i, o in enumerate(opciones) if _fraccion(o) >= 99.99]
            if len(correctas) == 1:
                posiciones[correctas[0] + 1] += 1
                esperado_primera += 1 / len(opciones)
            raras = sorted({m.group(0).lower() for t in textos for m in [_OPCION_PROBLEMATICA.search(t)] if m})
            if raras:
                problematicas.append({**_ref(p), "opciones": raras})
            largos = [(len(t), _fraccion(o)) for t, o in zip(textos, opciones, strict=False)]
            correcta = max((n for n, f in largos if f > 0), default=0)
            cortos = [n for n, f in largos if f <= 0 and correcta >= 20 and n < 0.25 * correcta]
            if cortos:
                debiles.append({**_ref(p), "distractores": len(cortos), "largo_correcta": correcta})
        negaciones = _sin_resaltar(_texto(p.get("stem")))
        if negaciones:
            negativas.append({**_ref(p), "negaciones": sorted(set(n.lower() for n in negaciones))})
    return {
        "preguntas_revisadas": revisadas,
        "posicion_correcta": {str(k): v for k, v in sorted(posiciones.items())},
        "correcta_primera": posiciones.get(1, 0),
        "correcta_primera_esperado": round(esperado_primera, 1),
        "sin_mezclar_opciones": sin_mezclar,
        "preguntas_opciones_problematicas": problematicas,
        "preguntas_negacion_sin_resaltar": negativas,
        "preguntas_distractores_debiles": debiles,
    }


CAMPOS_CONSISTENTES = ("penalty", "defaultgrade", "answernumbering", "shuffleanswers")


def auditar_moodle(preguntas: Iterable[dict]) -> Dict[str, Any]:
    """Campos de Moodle (sólo XML) que toman valores distintos dentro de una misma categoría
    y tipo de pregunta: penalización, puntaje, numeración y mezcla de opciones."""
    grupos: Dict[tuple, Dict[str, Counter]] = {}
    revisadas = 0
    for p in preguntas:
        datos = p.get("moodle") or {}
        if not datos:
            continue
        revisadas += 1
        clave = (p.get("categoria") or "(sin categoría)", p.get("type"))
        campos = grupos.setdefault(clave, {c: Counter() for c in CAMPOS_CONSISTENTES})
        for campo in CAMPOS_CONSISTENTES:
            if campo in datos:
                valor = datos[campo]
                try:
                    valor = f"{float(valor):g}"
                except ValueError:
                    valor = valor.strip().lower()
                campos[campo][valor] += 1
    inconsistentes = [
        {"categoria": cat, "tipo": tipo, "campo": campo, "valores": dict(cuenta.most_common())}
        for (cat, tipo), campos in sorted(grupos.items())
        for campo, cuenta in campos.items() if len(cuenta) > 1
    ]
    return {"preguntas_revisadas": revisadas, "inconsistencias": inconsistentes}


def auditar_estructura(preguntas: Iterable[dict]) -> Dict[str, Any]:
    """Preguntas sin título, sin enunciado o incompletas (respuesta corta o numérica sin
    respuestas, emparejamiento con menos de 2 pares, que Moodle no importa), código sin
    cerrar y conteo por tipo."""
    por_tipo: Counter = Counter()
    sin_titulo, sin_enunciado, sin_cerrar = [], [], []
    sin_respuestas, pocos_pares = [], []
    for p in preguntas:
        tipo = p.get("type")
        if tipo == "Category":
            continue
        por_tipo[tipo] += 1
        if not p.get("title"):
            sin_titulo.append(_ref(p))
        if not _plano(_texto(p.get("stem"))):
            sin_enunciado.append(_ref(p))
        if tipo in ("Short", "Numerical") and not p.get("choices"):
            sin_respuestas.append(_ref(p))
        if tipo == "Matching" and len(p.get("matchPairs") or []) < 2:
            pocos_pares.append({**_ref(p), "pares": len(p.get("matchPairs") or [])})
        textos = [p.get("stem"), p.get("globalFeedback"), p.get("trueFeedback"), p.get("falseFeedback")]
        for o in p.get("choices", []):
            textos += [o.get("text"), o.get("feedback")]
        abiertos = sum(1 for t in textos if _backticks_desbalanceados(_texto(t)))
        if abiertos:
            sin_cerrar.append({**_ref(p), "textos": abiertos})
    return {
        "total_preguntas": sum(por_tipo.values()),
        "por_tipo": dict(por_tipo.most_common()),
        "preguntas_sin_titulo": sin_titulo,
        "preguntas_sin_enunciado": sin_enunciado,
        "preguntas_codigo_sin_cerrar": sin_cerrar,
        "preguntas_sin_respuestas": sin_respuestas,
        "preguntas_pocos_pares": pocos_pares,
    }


# ---------------------------------------------------------------------------
# Auditorías sobre el texto (enlaces, HTML, código)
# ---------------------------------------------------------------------------

_HTML_OBSOLETO = re.compile(r"<(font|center|marquee)\b|\sstyle\s*=", re.IGNORECASE)


def limpiar_html_y_estilos_obsoletos(texto_html: str) -> str:
    """
    Elimina etiquetas HTML obsoletas (<font>, <center>, <marquee>) y estilos CSS inline contaminantes.
    """
    limpio = texto_html
    limpio = re.sub(r"</?font[^>]*>", "", limpio, flags=re.IGNORECASE)
    limpio = re.sub(r"</?center[^>]*>", "", limpio, flags=re.IGNORECASE)
    limpio = re.sub(r"</?marquee[^>]*>", "", limpio, flags=re.IGNORECASE)
    limpio = re.sub(r'\s*style="[^"]*"', "", limpio, flags=re.IGNORECASE)
    limpio = re.sub(r"\s*color='[^']*'", "", limpio, flags=re.IGNORECASE)
    limpio = re.sub(r"\s*face='[^']*'", "", limpio, flags=re.IGNORECASE)
    return limpio.strip()


def limpiar_html_archivo(contenido: str, formato: str) -> str:
    """Limpia HTML obsoleto: en GIFT sobre todo el texto, en XML dentro de cada <text>."""
    if formato == "xml":
        def limpiar(texto: str):
            limpio = limpiar_html_y_estilos_obsoletos(texto)
            return limpio, int(limpio != texto.strip())
        return transformar_textos_xml(contenido, limpiar)[0]
    return limpiar_html_y_estilos_obsoletos(contenido)


def auditar_enlaces_y_multimedia(texto: str) -> Dict[str, Any]:
    """
    Detecta URLs HTTP no seguras, servidores locales 'localhost' o links caídos/sospechosos.
    """
    urls = re.findall(r'https?://[^\s"\'<>{}|\\^`\]]+', texto)
    sospechosas = []
    for u in urls:
        if "localhost" in u or "127.0.0.1" in u:
            sospechosas.append({"url": u, "motivo": "Apunta a entorno local (localhost)"})
        elif u.startswith("http://"):
            sospechosas.append({"url": u, "motivo": "Protocolo HTTP inseguro (debe ser HTTPS)"})

    return {
        "total_urls": len(urls),
        "urls_sospechosas": sospechosas,
        "todas_validas": len(sospechosas) == 0
    }


def _textos_xml(contenido: str) -> List[str]:
    """Contenido (desescapado) de cada <text> de un XML."""
    textos: List[str] = []

    def juntar(texto: str):
        textos.append(texto)
        return texto, 0

    transformar_textos_xml(contenido, juntar)
    return textos


def auditar_texto(contenido: str, formato: str) -> Dict[str, Any]:
    """Enlaces, HTML obsoleto y código de un archivo (GIFT o XML)."""
    if formato == "xml":
        textos = _textos_xml(contenido)
        codigo = {"secciones": 0, "sin_proteger": 0, "variantes": 0, "lineas_vacias": 0,
                  "comentarios": 0, "sin_lenguaje": 0}
        for t in textos:
            for clave, valor in diagnosticar_codigo(t, "xml").items():
                codigo[clave] += valor
        visible = "\n".join(textos)
    else:
        codigo = diagnosticar_codigo(contenido, "gift")
        visible = contenido
    return {
        "enlaces": auditar_enlaces_y_multimedia(visible),
        "html_obsoleto": len(_HTML_OBSOLETO.findall(visible)),
        "codigo": codigo,
    }


# ---------------------------------------------------------------------------
# Auditoría completa
# ---------------------------------------------------------------------------

def _categoria_legible(ruta: str) -> str:
    ruta = ruta.replace("$course$", "").replace("$cat1$", "").strip().strip("/")
    return ruta or "(raíz)"


def _leer_y_parsear(ruta: Path, formato: str) -> tuple:
    """Lee el archivo una sola vez: el texto (con reemplazos si no es UTF-8 válido, para
    auditarlo igual) y el resultado del parser, que como parse_archivo rechaza lo que no
    es UTF-8. Los finales de línea se normalizan como en read_text."""
    try:
        datos = ruta.read_bytes()
    except OSError as e:
        return "", {"success": False, "error": {"message": f"Error leyendo archivo: {e}"}}
    try:
        texto = datos.decode("utf-8")
        estricto = True
    except UnicodeDecodeError as e:
        texto, estricto, error = datos.decode("utf-8", errors="replace"), False, e
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    if not estricto:
        return texto, {"success": False, "error": {"message": f"Error leyendo archivo: {error}"}}
    try:
        return texto, parse_xml(texto) if formato == "xml" else parse_gift(texto)
    except Exception as e:  # noqa: BLE001 - como parse_archivo: se informa como archivo ilegible
        return texto, {"success": False, "error": {"message": f"Error leyendo archivo: {e}"}}


def _carpeta(ruta: Path, base: Path, padre: Optional[Path] = None) -> str:
    try:
        relativa = (padre or Path(ruta).resolve().parent).relative_to(base)
    except ValueError:
        relativa = Path(ruta).parent
    return str(relativa).replace(os.sep, "/") if str(relativa) != "." else "(raíz)"


ALTOS = ("analizar", "evaluar", "crear")


def auditar_clasificacion(preguntas: Iterable[dict], minimo_categoria: int = 5) -> Dict[str, Any]:
    """Bloom y dificultad (de `metadata`) y matriz categoría × Bloom (blueprint).

    Advierte las categorías con al menos `minimo_categoria` preguntas clasificadas y
    ninguna de nivel alto (analizar, evaluar, crear).
    """
    evaluables = _evaluables(preguntas)
    clasificadas = [p for p in evaluables if (p.get("metadata") or {}).get("bloom")]
    bloom = Counter(p["metadata"]["bloom"] for p in clasificadas)
    matriz: Dict[str, Counter] = {}
    for p in clasificadas:
        matriz.setdefault(p.get("categoria") or "(sin categoría)", Counter())[p["metadata"]["bloom"]] += 1
    enunciado = [p["metadata"]["dificultad_enunciado"] for p in clasificadas if "dificultad_enunciado" in p["metadata"]]
    respuestas = [p["metadata"]["dificultad_respuestas"] for p in clasificadas if "dificultad_respuestas" in p["metadata"]]
    sin_altos = [
        {"categoria": cat, "clasificadas": sum(c.values())}
        for cat, c in sorted(matriz.items())
        if sum(c.values()) >= minimo_categoria and not any(c[n] for n in ALTOS)
    ]
    return {
        "evaluables": len(evaluables),
        "clasificadas": len(clasificadas),
        "bloom": {n: bloom.get(n, 0) for n in NIVELES_BLOOM},
        "dificultad_enunciado_media": round(mean(enunciado), 2) if enunciado else None,
        "dificultad_respuestas_media": round(mean(respuestas), 2) if respuestas else None,
        "blueprint": {cat: {n: c.get(n, 0) for n in NIVELES_BLOOM} for cat, c in sorted(matriz.items())},
        "categorias_sin_niveles_altos": sin_altos,
    }


def auditar_preguntas(
    preguntas: List[dict],
    min_opciones: int = MIN_OPCIONES,
    umbral_longitud: float = UMBRAL_LONGITUD,
) -> Dict[str, Any]:
    """Todas las auditorías de preguntas (formato indistinto)."""
    return {
        "estructura": auditar_estructura(preguntas),
        "porcentajes": auditar_porcentajes(preguntas),
        "retroalimentacion": auditar_feedback(preguntas),
        "opciones": auditar_opciones(preguntas, min_opciones),
        "longitud": auditar_longitudes(preguntas, umbral_longitud),
        "clasificacion": auditar_clasificacion(preguntas),
        "redaccion": auditar_redaccion(preguntas),
        "moodle": auditar_moodle(preguntas),
    }


def auditar_archivos(
    archivos: Iterable[Path],
    min_opciones: int = MIN_OPCIONES,
    umbral_longitud: float = UMBRAL_LONGITUD,
    contenidos: Optional[Dict[Path, str]] = None,
    con_preguntas: bool = False,
    avance: Optional[Callable[[], None]] = None,
) -> Dict[str, Any]:
    """Audita un conjunto de archivos GIFT y/o XML como un único banco.

    Con `con_preguntas`, el resultado lleva también `_preguntas` (las preguntas del modelo
    con archivo, formato y categoría), para exportarlas; no forma parte del JSON.
    """
    preguntas: List[dict] = []
    errores: List[dict] = []
    por_formato: Counter = Counter()
    enlaces: Dict[str, Any] = {"total_urls": 0, "urls_sospechosas": [], "todas_validas": True}
    codigo: Dict[str, Any] = {"secciones": 0, "sin_proteger": 0, "variantes": 0, "lineas_vacias": 0,
              "comentarios": 0, "sin_lenguaje": 0}
    archivos_codigo: List[dict] = []
    html_obsoleto: List[dict] = []
    sin_preguntas: List[str] = []
    archivos = list(archivos)
    # Cada carpeta se resuelve una sola vez (resolve es lo más caro de recorrer el banco).
    padres = {a: Path(a).resolve().parent for a in archivos}
    base = Path(os.path.commonpath([str(p) for p in padres.values()])) if archivos else Path(".")

    for ruta in archivos:
        if avance is not None:
            avance()
        formato = formato_de(ruta) or "gift"
        por_formato[formato] += 1
        if contenidos and ruta in contenidos:
            contenido = contenidos[ruta]
            resultado = parse_xml(contenido) if formato == "xml" else parse_gift(contenido)
        else:
            contenido, resultado = _leer_y_parsear(ruta, formato)
        if not resultado.get("success"):
            errores.append({"archivo": str(ruta), "error": resultado["error"]["message"]})
        else:
            # Categoría: la última $CATEGORY / <question type="category"> del archivo o, en un
            # árbol de una pregunta por archivo, la carpeta relativa a la raíz del banco.
            categoria, carpeta = None, None
            if not any(p.get("type") != "Category" for p in resultado["questions"]):
                sin_preguntas.append(str(ruta))
            for p in resultado["questions"]:
                if p.get("type") == "Category":
                    categoria = _categoria_legible(p.get("title") or "")
                    continue
                if categoria is None and carpeta is None:
                    carpeta = _carpeta(ruta, base, padres.get(ruta))
                preguntas.append({**p, "filepath": str(ruta), "formato": formato,
                                  "categoria": categoria or carpeta})

        texto = auditar_texto(contenido, formato)
        enlaces["total_urls"] += texto["enlaces"]["total_urls"]
        enlaces["urls_sospechosas"].extend(
            {**u, "archivo": str(ruta)} for u in texto["enlaces"]["urls_sospechosas"])
        for clave, valor in texto["codigo"].items():
            codigo[clave] += valor
        if any(texto["codigo"][k] for k in ("sin_proteger", "variantes", "lineas_vacias", "comentarios", "sin_lenguaje")):
            archivos_codigo.append({"archivo": str(ruta), **texto["codigo"]})
        if texto["html_obsoleto"]:
            html_obsoleto.append({"archivo": str(ruta), "ocurrencias": texto["html_obsoleto"]})

    enlaces["todas_validas"] = not enlaces["urls_sospechosas"]
    codigo["archivos"] = archivos_codigo
    formatos = sorted(por_formato)
    resultado = {
        "formato": formatos[0] if len(formatos) == 1 else ("mixto" if formatos else None),
        "archivos": {"total": len(archivos), "por_formato": dict(por_formato), "errores": errores,
                     "sin_preguntas": sin_preguntas},
        **auditar_preguntas(preguntas, min_opciones, umbral_longitud),
        "codigo": codigo,
        "enlaces": enlaces,
        "html_obsoleto": html_obsoleto,
    }
    resultado["resumen"] = resumir_hallazgos(resultado)
    if con_preguntas:
        resultado["_preguntas"] = preguntas
    return resultado


def resumir_hallazgos(resultado: Dict[str, Any]) -> Dict[str, Any]:
    """Separa los hallazgos en errores y advertencias.

    Errores: lo que hace que Moodle no importe la pregunta, la importe partida o la
    califique mal (archivos ilegibles, claves de corrección inválidas, preguntas sin
    enunciado, código que rompe un archivo GIFT). Advertencias: calidad pedagógica e
    higiene (feedback, opciones, longitud, enlaces, HTML, código XML sin proteger).
    """
    est, pct, fb = resultado["estructura"], resultado["porcentajes"], resultado["retroalimentacion"]
    opc, lon, cod = resultado["opciones"], resultado["longitud"], resultado["codigo"]
    codigo_gift = [a for a in cod["archivos"] if formato_de(a["archivo"]) == "gift"]
    codigo_xml = [a for a in cod["archivos"] if formato_de(a["archivo"]) != "gift"]

    def items(*pares):
        return [{"clave": clave, "descripcion": desc, "cantidad": n} for clave, desc, n in pares if n]

    errores = items(
        ("archivos_ilegibles", "archivos que no se pudieron interpretar", len(resultado["archivos"]["errores"])),
        ("fracciones_invalidas", "preguntas con porcentajes que Moodle rechaza al importar", len(pct["fracciones_invalidas"])),
        ("porcentajes_inconsistentes", "preguntas cuyos porcentajes no suman 100 %", len(pct["preguntas_inconsistentes"])),
        ("sin_correcta", "preguntas sin ninguna respuesta con puntaje positivo", len(pct["preguntas_sin_correcta"])),
        ("sin_enunciado", "preguntas sin enunciado (en GIFT, suele ser una línea en blanco antes de `{`)",
         len(est["preguntas_sin_enunciado"])),
        ("sin_respuestas", "preguntas de respuesta corta o numérica sin respuestas",
         len(est.get("preguntas_sin_respuestas", []))),
        ("pocos_pares", "preguntas de emparejamiento con menos de 2 pares", len(est.get("preguntas_pocos_pares", []))),
        ("codigo_gift_sin_proteger", "archivos GIFT con código que GIFT interpreta (sin fullwidth ni escape)",
         sum(1 for a in codigo_gift if a["sin_proteger"])),
        ("codigo_gift_lineas_vacias", "archivos GIFT con líneas en blanco dentro del código (cortan la pregunta)",
         sum(1 for a in codigo_gift if a["lineas_vacias"])),
    )
    advertencias = items(
        ("sin_feedback", "preguntas sin ningún feedback", fb["sin_feedback_count"]),
        ("feedback_parcial", "preguntas con feedback en sólo algunas opciones", len(fb["preguntas_feedback_parcial"])),
        ("pocas_opciones", "preguntas con menos opciones de las recomendadas", len(opc["preguntas_pocas_opciones"])),
        ("opciones_repetidas", "preguntas que repiten una opción", len(opc["preguntas_opciones_repetidas"])),
        ("correcta_mas_larga", "preguntas donde la correcta es notablemente más larga", len(lon["preguntas_correcta_mas_larga"])),
        ("correcta_mas_corta", "preguntas donde la correcta es notablemente más corta", len(lon["preguntas_correcta_mas_corta"])),
        ("codigo_sin_cerrar", "preguntas con un ` o ``` sin cerrar", len(est["preguntas_codigo_sin_cerrar"])),
        ("sin_titulo", "preguntas sin título", len(est["preguntas_sin_titulo"])),
        ("archivos_sin_preguntas", "archivos sin preguntas", len(resultado["archivos"].get("sin_preguntas", []))),
        ("opciones_problematicas", "preguntas con opciones como «todas/ninguna de las anteriores»",
         len(resultado.get("redaccion", {}).get("preguntas_opciones_problematicas", []))),
        ("negacion_sin_resaltar", "enunciados con una negación sin resaltar (excepto, incorrecta, no es…)",
         len(resultado.get("redaccion", {}).get("preguntas_negacion_sin_resaltar", []))),
        ("distractores_debiles", "preguntas con distractores mucho más cortos que la correcta",
         len(resultado.get("redaccion", {}).get("preguntas_distractores_debiles", []))),
        ("metadatos_moodle", "campos de Moodle con valores distintos en una misma categoría (penalización, puntaje…)",
         len(resultado.get("moodle", {}).get("inconsistencias", []))),
        ("sin_niveles_altos", "categorías sin preguntas de B4–B6 (analizar, evaluar, crear)",
         len(resultado.get("clasificacion", {}).get("categorias_sin_niveles_altos", []))),
        ("codigo_xml_sin_proteger", "archivos XML con código sin proteger (se rompería al pasar a GIFT)",
         sum(1 for a in codigo_xml if a["sin_proteger"] or a["lineas_vacias"])),
        ("marcas_no_canonicas", "archivos con marcas no canónicas en el código", sum(1 for a in cod["archivos"] if a["variantes"])),
        ("comentarios_en_codigo", "archivos con líneas // en el código sin proteger (GIFT y Moodle las descartan)",
         sum(1 for a in cod["archivos"] if a.get("comentarios"))),
        ("codigo_sin_lenguaje", "archivos con bloques ``` sin etiqueta de lenguaje",
         sum(1 for a in cod["archivos"] if a.get("sin_lenguaje"))),
        ("enlaces_sospechosos", "enlaces http:// o locales", len(resultado["enlaces"]["urls_sospechosas"])),
        ("html_obsoleto", "archivos con HTML obsoleto", len(resultado["html_obsoleto"])),
    )
    return {
        "ok": not errores,
        "errores": errores,
        "advertencias": advertencias,
        "total_errores": sum(e["cantidad"] for e in errores),
        "total_advertencias": sum(a["cantidad"] for a in advertencias),
    }


# ---------------------------------------------------------------------------
# Exportación por pregunta (CSV)
# ---------------------------------------------------------------------------

COLUMNAS_CSV = (
    "archivo", "formato", "categoria", "titulo", "tipo", "opciones", "correctas", "feedback_general",
    "opciones_con_feedback", "razon_longitud", "correcta_mas_larga", "fraccion_invalida", "sin_correcta",
    "codigo_sin_cerrar", "negacion_sin_resaltar", "opcion_problematica", "distractores_debiles",
    "bloom", "dificultad_enunciado", "dificultad_respuestas",
)


def fila_csv(p: dict) -> Dict[str, Any]:
    """Las señales de una pregunta como una fila plana."""
    opciones = p.get("choices", [])
    fracciones = [_fraccion(o) for o in opciones]
    textos = [_plano(_texto(o.get("text"))) for o in opciones]
    largos = [len(t) for t in textos]
    correctas = [n for n, f in zip(largos, fracciones, strict=False) if f > 0]
    distractores = [n for n, f in zip(largos, fracciones, strict=False) if f <= 0]
    razon = round(mean(correctas) / mean(distractores), 2) if correctas and distractores and mean(distractores) else ""
    retros = [o.get("feedback") for o in opciones] if p.get("type") != "TF" else [p.get("trueFeedback"), p.get("falseFeedback")]
    textos_todos = [p.get("stem"), p.get("globalFeedback")] + [o.get("text") for o in opciones] + retros
    meta = p.get("metadata") or {}
    return {
        "archivo": p.get("filepath", ""),
        "formato": p.get("formato", ""),
        "categoria": p.get("categoria", ""),
        "titulo": p.get("title") or "",
        "tipo": p.get("type", ""),
        "opciones": len(opciones) + len(p.get("matchPairs", [])),
        "correctas": sum(1 for f in fracciones if f > 0),
        "feedback_general": int(bool(_texto(p.get("globalFeedback")).strip())),
        "opciones_con_feedback": sum(1 for r in retros if _texto(r).strip()),
        "razon_longitud": razon,
        "correcta_mas_larga": int(len(correctas) == 1 and bool(distractores) and correctas[0] > max(distractores)),
        "fraccion_invalida": int(any(not _fraccion_valida(f) for f in fracciones)),
        "sin_correcta": int(p.get("type") in ("MC", "Short", "Numerical") and bool(opciones) and not any(f > 0 for f in fracciones)),
        "codigo_sin_cerrar": int(any(_backticks_desbalanceados(_texto(t)) for t in textos_todos)),
        "negacion_sin_resaltar": int(bool(_sin_resaltar(_texto(p.get("stem"))))),
        "opcion_problematica": int(any(_OPCION_PROBLEMATICA.search(t) for t in textos)),
        "distractores_debiles": sum(1 for n in distractores if correctas and max(correctas) >= 20 and n < 0.25 * max(correctas)),
        "bloom": meta.get("bloom", ""),
        "dificultad_enunciado": meta.get("dificultad_enunciado", ""),
        "dificultad_respuestas": meta.get("dificultad_respuestas", ""),
    }


def escribir_csv(preguntas: Iterable[dict], destino: Path) -> int:
    """Escribe una fila por pregunta evaluable. Devuelve cuántas filas escribió."""
    import csv

    filas = [fila_csv(p) for p in _evaluables(preguntas)]
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS_CSV)
        escritor.writeheader()
        escritor.writerows(filas)
    return len(filas)


# ---------------------------------------------------------------------------
# Compatibilidad: auditorías sobre texto GIFT
# ---------------------------------------------------------------------------

def _preguntas_gift(texto_gift: str) -> List[dict]:
    resultado = parse_gift(texto_gift)
    return resultado["questions"] if resultado.get("success") else []


def verificar_porcentajes_opciones(texto_gift: str) -> Dict[str, Any]:
    """
    Verifica las claves de corrección de un texto GIFT (ver `auditar_porcentajes`).
    """
    return auditar_porcentajes(_preguntas_gift(texto_gift))


def auditar_retroalimentaciones(texto_gift: str) -> Dict[str, Any]:
    """
    Detecta preguntas de un texto GIFT sin retroalimentación (ver `auditar_feedback`).
    """
    return auditar_feedback(_preguntas_gift(texto_gift))


def convertir_windows1252_a_utf8(contenido_bytes: bytes) -> str:
    """
    Convierte bytes con codificación Windows-1252 / Latin-1 a string UTF-8 limpio.
    """
    try:
        return contenido_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return contenido_bytes.decode("cp1252", errors="replace")


# ---------------------------------------------------------------------------
# Reporte Markdown
# ---------------------------------------------------------------------------

def _lista(lineas: List[str], items: List[dict], formato_item, max_items: int) -> None:
    mostrados = items if not max_items else items[:max_items]
    for item in mostrados:
        archivo = f" — `{item['archivo']}`" if item.get("archivo") else ""
        lineas.append(f"- {formato_item(item)}{archivo}")
    if len(items) > len(mostrados):
        lineas.append(f"- … y {len(items) - len(mostrados)} más (`--max-items 0` las muestra todas)")
    lineas.append("")


def _pct(parte: int, total: int) -> str:
    return f"{(parte / total * 100):.1f}%" if total else "—"


def generar_reporte_markdown(resultado: Dict[str, Any], nombre: str, max_items: int = 50) -> str:
    """Informe de salud en Markdown a partir del resultado de `auditar_archivos`."""
    est = resultado["estructura"]
    pct = resultado["porcentajes"]
    fb = resultado["retroalimentacion"]
    opc = resultado["opciones"]
    lon = resultado["longitud"]
    cod = resultado["codigo"]
    enl = resultado["enlaces"]
    arch = resultado["archivos"]
    total = est["total_preguntas"]

    lineas = [f"# 🏥 Informe de Salud del Banco de Preguntas: `{nombre}`\n"]

    resumen = resultado.get("resumen") or resumir_hallazgos(resultado)
    lineas.append("## Resultado")
    if resumen["ok"]:
        lineas.append(f"✅ Sin errores · {resumen['total_advertencias']} advertencias\n")
    else:
        lineas.append(f"❌ {resumen['total_errores']} errores · {resumen['total_advertencias']} advertencias\n")
    for etiqueta, grupo in (("Error", resumen["errores"]), ("Advertencia", resumen["advertencias"])):
        lineas.extend(f"- **{etiqueta}:** {h['cantidad']} {h['descripcion']}" for h in grupo)
    if resumen["errores"] or resumen["advertencias"]:
        lineas.append("")

    lineas.append("## Estadísticas Generales")
    formatos = " · ".join(f"{k.upper()}: {v}" for k, v in sorted(arch["por_formato"].items()))
    lineas.append(f"- **Archivos:** {arch['total']} ({formatos})" if formatos else f"- **Archivos:** {arch['total']}")
    lineas.append(f"- **Preguntas:** {total} ({fb['total_preguntas']} con respuestas; "
                  "las descripciones y cloze no se evalúan)")
    if est["por_tipo"]:
        lineas.append("- **Por tipo:** " + ", ".join(f"{t} {n}" for t, n in est["por_tipo"].items()))
    lineas.append(f"- **Cobertura de Feedback:** {_pct(fb['total_preguntas'] - fb['sin_feedback_count'], fb['total_preguntas'])} "
                  f"({fb['sin_feedback_count']} sin explicación)")
    lineas.append(f"- **Opciones con feedback:** {_pct(fb['opciones_con_feedback'], fb['opciones_total'])} "
                  f"({fb['opciones_con_feedback']} de {fb['opciones_total']})")
    lineas.append(f"- **Enlaces Sospechosos / HTTP:** {len(enl['urls_sospechosas'])}\n")
    if arch["errores"]:
        lineas.append(f"> [!CAUTION]\n> {len(arch['errores'])} archivos no se pudieron interpretar.\n")
        _lista(lineas, arch["errores"], lambda e: e["error"], max_items)

    lineas.append("## Calidad y Claves de Corrección")
    if pct["ok"]:
        lineas.append("> [!NOTE]\n> Todas las claves de corrección son consistentes y usan porcentajes que Moodle acepta.\n")
    if pct["preguntas_inconsistentes"]:
        lineas.append(f"> [!WARNING]\n> Se detectaron {len(pct['preguntas_inconsistentes'])} preguntas donde los porcentajes no suman 100%.\n")
        _lista(lineas, pct["preguntas_inconsistentes"],
               lambda i: f"{i['titulo']} (suma {i['suma_positivos']:g}%)", max_items)
    if pct["preguntas_sin_correcta"]:
        lineas.append(f"> [!WARNING]\n> {len(pct['preguntas_sin_correcta'])} preguntas no tienen ninguna respuesta con puntaje positivo.\n")
        _lista(lineas, pct["preguntas_sin_correcta"], lambda i: i["titulo"], max_items)
    if pct["fracciones_invalidas"]:
        lineas.append(f"> [!CAUTION]\n> {len(pct['fracciones_invalidas'])} preguntas usan porcentajes que Moodle "
                      "rechaza al importar (la pregunta se descarta).\n")
        _lista(lineas, pct["fracciones_invalidas"],
               lambda i: f"{i['titulo']} ({', '.join(f'{f:g}%' for f in i['fracciones'])})", max_items)

    lineas.append("## Retroalimentación")
    lineas.append(f"- Con feedback general: {fb['con_feedback_global']} de {fb['total_preguntas']} "
                  f"({_pct(fb['con_feedback_global'], fb['total_preguntas'])})")
    lineas.append(f"- Sin ningún feedback: {fb['sin_feedback_count']}")
    lineas.append(f"- Con feedback en sólo algunas opciones: {len(fb['preguntas_feedback_parcial'])}\n")
    if fb["preguntas_sin_feedback"]:
        lineas.append("### Preguntas sin feedback")
        _lista(lineas, fb["preguntas_sin_feedback"], lambda i: i["titulo"], max_items)
    if fb["preguntas_feedback_parcial"]:
        lineas.append("### Opciones sin feedback")
        _lista(lineas, fb["preguntas_feedback_parcial"],
               lambda i: f"{i['titulo']} ({i['opciones_sin_feedback']} de {i['opciones']})", max_items)

    lineas.append("## Cantidad de Opciones")
    if opc["distribucion_mc"]:
        lineas.append("| Opciones | Preguntas de opción múltiple |\n| :-- | --: |")
        lineas.extend(f"| {k} | {v} |" for k, v in opc["distribucion_mc"].items())
        lineas.append(f"\nPromedio: {opc['promedio_mc']} opciones.\n")
    if opc["preguntas_pocas_opciones"]:
        lineas.append(f"> [!WARNING]\n> {len(opc['preguntas_pocas_opciones'])} preguntas tienen menos opciones "
                      f"de las recomendadas (opción múltiple: {opc['minimo']}, emparejamiento: {MIN_PARES_MATCHING}).\n")
        _lista(lineas, opc["preguntas_pocas_opciones"],
               lambda i: f"{i['titulo']} ({i['tipo']}, {i['opciones']})", max_items)
    if opc["preguntas_opciones_repetidas"]:
        lineas.append(f"> [!WARNING]\n> {len(opc['preguntas_opciones_repetidas'])} preguntas repiten una opción.\n")
        _lista(lineas, opc["preguntas_opciones_repetidas"],
               lambda i: f"{i['titulo']} ({'; '.join(i['repetidas'])[:80]})", max_items)

    lineas.append("## Longitud Relativa de las Respuestas")
    lineas.append(f"- Preguntas de opción múltiple revisadas: {lon['preguntas_revisadas']}")
    lineas.append(f"- La correcta es la opción más larga en {lon['correcta_es_la_mas_larga']} preguntas "
                  f"(por azar se esperarían ≈{lon['correcta_es_la_mas_larga_esperado']:g})")
    lineas.append(f"- Correcta ≥ {lon['umbral']:g}× más larga que los distractores: {len(lon['preguntas_correcta_mas_larga'])}")
    lineas.append(f"- Correcta ≤ 1/{lon['umbral']:g} del largo de los distractores: {len(lon['preguntas_correcta_mas_corta'])}\n")
    if lon["correcta_es_la_mas_larga"] > 1.5 * lon["correcta_es_la_mas_larga_esperado"] + 2:
        lineas.append("> [!WARNING]\n> La respuesta correcta es la más larga mucho más seguido que por azar: "
                      "la longitud funciona como pista.\n")
    for clave, titulo in (("preguntas_correcta_mas_larga", "Correcta notablemente más larga"),
                          ("preguntas_correcta_mas_corta", "Correcta notablemente más corta")):
        if lon[clave]:
            lineas.append(f"### {titulo}")
            _lista(lineas, sorted(lon[clave], key=lambda i: -abs(i["razon"] - 1)),
                   lambda i: f"{i['titulo']} (×{i['razon']:g}: {i['largo_correcta']:g} vs {i['largo_distractores']:g} caracteres)",
                   max_items)

    red = resultado.get("redaccion")
    if red and red["preguntas_revisadas"]:
        lineas.append("## Redacción")
        lineas.append(f"- La correcta es la primera opción en {red['correcta_primera']} preguntas "
                      f"(por azar se esperarían ≈{red['correcta_primera_esperado']:g}); importa si no se mezclan "
                      f"las opciones ({red['sin_mezclar_opciones']} preguntas XML con shuffleanswers en falso) "
                      "o en exámenes impresos")
        if red["posicion_correcta"]:
            lineas.append("- Posición de la correcta: " + ", ".join(f"{k}.ª {v}" for k, v in red["posicion_correcta"].items()))
        lineas.append("")
        for clave, titulo, formato in (
            ("preguntas_opciones_problematicas", "Opciones «todas/ninguna de las anteriores» (se rompen al mezclar)",
             lambda i: f"{i['titulo']} ({', '.join(i['opciones'])})"),
            ("preguntas_negacion_sin_resaltar", "Negaciones sin resaltar en el enunciado",
             lambda i: f"{i['titulo']} ({', '.join(i['negaciones'])})"),
            ("preguntas_distractores_debiles", "Distractores mucho más cortos que la correcta (menos del 25 %)",
             lambda i: f"{i['titulo']} ({i['distractores']} distractores; correcta de {i['largo_correcta']} caracteres)"),
        ):
            if red[clave]:
                lineas.append(f"### {titulo} ({len(red[clave])})")
                _lista(lineas, red[clave], formato, max_items)

    moo = resultado.get("moodle")
    if moo and moo["inconsistencias"]:
        lineas.append("## Metadatos de Moodle")
        lineas.append(f"En {len(moo['inconsistencias'])} casos, preguntas del mismo tipo y categoría tienen valores "
                      "distintos (sólo XML; GIFT no los representa):\n")
        _lista(lineas, moo["inconsistencias"],
               lambda i: f"{i['categoria']} · {i['tipo']} · {i['campo']}: "
                         + ", ".join(f"{v} ({n})" for v, n in i["valores"].items()), max_items)

    cla = resultado.get("clasificacion")
    if cla and cla["clasificadas"]:
        lineas.append("## Clasificación (Bloom y dificultad)")
        lineas.append(f"- Clasificadas: {cla['clasificadas']} de {cla['evaluables']} "
                      f"({_pct(cla['clasificadas'], cla['evaluables'])}); `voight ai --mode classify` clasifica el resto")
        if cla["dificultad_enunciado_media"] is not None:
            lineas.append(f"- Dificultad media (1–5): enunciado {cla['dificultad_enunciado_media']:g}"
                          + (f", respuestas {cla['dificultad_respuestas_media']:g}" if cla["dificultad_respuestas_media"] is not None else ""))
        lineas.append("")
        encabezado = " | ".join(f"{codigo_bloom(n)} {n}" for n in NIVELES_BLOOM)
        lineas.append(f"| Categoría | {encabezado} | Total |")
        lineas.append("| :-- |" + " --: |" * (len(NIVELES_BLOOM) + 1))
        lineas.append("| **Banco** | " + " | ".join(str(cla["bloom"][n]) for n in NIVELES_BLOOM)
                      + f" | {cla['clasificadas']} |")
        filas = sorted(cla["blueprint"].items(), key=lambda kv: -sum(kv[1].values()))
        mostradas = filas if not max_items else filas[:max_items]
        for cat, cuenta in mostradas:
            lineas.append(f"| {cat} | " + " | ".join(str(cuenta[n] or "·") for n in NIVELES_BLOOM)
                          + f" | {sum(cuenta.values())} |")
        if len(filas) > len(mostradas):
            lineas.append(f"| … y {len(filas) - len(mostradas)} categorías más | " + " |" * (len(NIVELES_BLOOM) + 1))
        lineas.append("")
        if cla["categorias_sin_niveles_altos"]:
            lineas.append("> [!TIP]\n> Categorías sin preguntas de analizar, evaluar o crear (B4–B6):\n")
            _lista(lineas, cla["categorias_sin_niveles_altos"],
                   lambda i: f"{i['categoria']} ({i['clasificadas']} clasificadas)", max_items)

    lineas.append("## Código")
    lineas.append(f"- Secciones de código: {cod['secciones']}")
    lineas.append(f"- Sin proteger para GIFT (`{{ }} = ~ # \\` o `//` sin fullwidth ni escape): {cod['sin_proteger']}")
    lineas.append(f"- Con marcas no canónicas (U+2007, NBSP, `;` griego… en lugar de `·` y `；`): {cod['variantes']}")
    lineas.append(f"- Con líneas en blanco sin `↵`: {cod['lineas_vacias']}")
    lineas.append(f"- Con líneas `//` sin proteger (se pierden al importar): {cod.get('comentarios', 0)}")
    lineas.append(f"- Bloques ``` sin etiqueta de lenguaje (`voight fix code-lang` la agrega): {cod.get('sin_lenguaje', 0)}\n")
    if cod["archivos"]:
        lineas.append("> [!TIP]\n> `voight fix format --fullwidth` protege el código y agrega las marcas `·` y `↵`.\n")
        _lista(lineas, cod["archivos"],
               lambda i: f"{i['sin_proteger']} sin proteger, {i['variantes']} con variantes, {i['lineas_vacias']} con líneas en blanco, "
                         f"{i.get('comentarios', 0)} con //, {i.get('sin_lenguaje', 0)} sin lenguaje",
               max_items)

    lineas.append("## Enlaces y HTML")
    lineas.append(f"- URLs: {enl['total_urls']} ({len(enl['urls_sospechosas'])} sospechosas)")
    lineas.append(f"- Archivos con HTML obsoleto (`<font>`, `<center>`, `style=`): {len(resultado['html_obsoleto'])}\n")
    if enl["urls_sospechosas"]:
        _lista(lineas, enl["urls_sospechosas"], lambda u: f"{u['url']} ({u['motivo']})", max_items)
    if resultado["html_obsoleto"]:
        lineas.append("> [!TIP]\n> `voight fix clean-html` elimina esas etiquetas y estilos.\n")

    sin_respuestas, pocos_pares = est.get("preguntas_sin_respuestas", []), est.get("preguntas_pocos_pares", [])
    sin_preguntas = resultado["archivos"].get("sin_preguntas", [])
    if (est["preguntas_sin_titulo"] or est["preguntas_sin_enunciado"] or est["preguntas_codigo_sin_cerrar"]
            or sin_respuestas or pocos_pares or sin_preguntas):
        lineas.append("## Estructura")
        if sin_respuestas:
            lineas.append(f"### Respuesta corta o numérica sin respuestas ({len(sin_respuestas)})")
            _lista(lineas, sin_respuestas, lambda i: i["titulo"], max_items)
        if pocos_pares:
            lineas.append(f"### Emparejamiento con menos de 2 pares ({len(pocos_pares)})")
            _lista(lineas, pocos_pares, lambda i: f"{i['titulo']} ({i['pares']} pares)", max_items)
        if sin_preguntas:
            lineas.append(f"### Archivos sin preguntas ({len(sin_preguntas)})")
            _lista(lineas, [{"archivo": a} for a in sin_preguntas], lambda i: i["archivo"], max_items)
        if est["preguntas_codigo_sin_cerrar"]:
            lineas.append(f"### Código sin cerrar: un ` o ``` sin pareja ({len(est['preguntas_codigo_sin_cerrar'])})")
            _lista(lineas, est["preguntas_codigo_sin_cerrar"],
                   lambda i: f"{i['titulo']} ({i['textos']} textos)", max_items)
        if est["preguntas_sin_titulo"]:
            lineas.append(f"### Sin título ({len(est['preguntas_sin_titulo'])})")
            _lista(lineas, est["preguntas_sin_titulo"], lambda i: i["titulo"], max_items)
        if est["preguntas_sin_enunciado"]:
            lineas.append(f"### Sin enunciado ({len(est['preguntas_sin_enunciado'])})")
            _lista(lineas, est["preguntas_sin_enunciado"], lambda i: i["titulo"], max_items)

    return "\n".join(lineas).rstrip() + "\n"


def generar_reporte_salud_markdown(
    archivo_banco: Path,
    contenido: str,
    es_xml: bool = False
) -> str:
    """
    Genera un informe completo de salud del banco en formato Markdown.
    """
    ruta = Path(archivo_banco)
    formato = "xml" if es_xml else "gift"
    if formato_de(ruta) != formato:
        ruta = ruta.with_suffix(f".{formato}")
    resultado = auditar_archivos([ruta], contenidos={ruta: contenido})
    return generar_reporte_markdown(resultado, Path(archivo_banco).name)
