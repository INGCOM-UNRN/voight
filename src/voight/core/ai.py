"""Procesamiento de preguntas con un LLM (Gemini) sobre GIFT y Moodle XML.

El modelo siempre recibe GIFT compacto, el formato más corto para una pregunta y el
que los LLM conocen mejor:

- GIFT: el bloque de la pregunta sin comentarios (`// [tag:…]`, `[id:…]`) ni
  `$CATEGORY`, que se conservan aparte y se vuelven a poner al escribir.
- Moodle XML: la pregunta pasa por el modelo unificado y se serializa a GIFT; la
  respuesta se aplica sobre el `<question>` original, que conserva todo lo que GIFT no
  representa (penalización, numeración, tags, idnumber, formatos…).
- Código: se envía en ASCII normal y sin las marcas `·` y `↵` (los símbolos fullwidth
  ocupan 3 bytes y cortan los tokens; además el modelo razona mejor sobre código
  normal). La respuesta se vuelve a proteger antes de interpretarla y cada archivo
  recupera la convención de su original.

Las preguntas sin equivalente en GIFT (cloze y tipos de plugins) y las categorías no
se envían. Si una respuesta del modelo no es una pregunta GIFT válida (o en `improve`
cambia el tipo), se conserva el original.
"""
from __future__ import annotations

import copy
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

try:
    from google import genai
except ImportError:
    genai = None

from voight.core.cache import Cache
from voight.core.codigo import transformar_codigo
from voight.core.config import get_anthropic_key, get_api_key, get_model
from voight.core.converter import question_to_gift
from voight.core.formatter import format_gift_content
from voight.core.gift_model import Question
from voight.core.parser import GiftParser
from voight.core.tree import serializar_quiz

# El lector vive en core/lector.py; se reexporta por compatibilidad.
from voight.core.lector import (  # noqa: F401
    TIPOS_PROCESABLES, Archivo, Unidad, _compactar, _compactar_pregunta, _forma, leer_archivos,
    split_gift_questions, unidades_de,
)

VARIACIONES = 3


MODELO_CLAUDE = "claude-opus-5"
PROVEEDORES = ("gemini", "claude")


class ClienteClaude:
    """Claude (Anthropic) con la interfaz que usa el procesamiento por lotes:
    `cliente.models.generate_content(model=…, contents=…).text`.

    Usa el SDK oficial con los reintentos propios del SDK (429, 5xx y errores de red) y
    el fallback del servidor ante una negativa por política (`fallbacks="default"`): si
    el modelo declina, la API reintenta en otro modelo dentro de la misma llamada. Si
    aun así la respuesta es una negativa, el lote falla y sus preguntas quedan como
    estaban.
    """

    def __init__(self, cliente=None, max_tokens: int = 16000):
        if cliente is None:
            try:
                import anthropic
            except ImportError:
                raise ImportError(
                    "El paquete 'anthropic' no está instalado: `voight ai --proveedor claude` requiere el extra "
                    'opcional ai. Instalalo con: uv tool install "questions[ai] @ git+https://github.com/INGCOM-UNRN/moodle-toolbox"'
                ) from None
            clave = get_anthropic_key()
            cliente = anthropic.Anthropic(api_key=clave, max_retries=5) if clave else anthropic.Anthropic(max_retries=5)
        self._cliente = cliente
        self.max_tokens = max_tokens
        self.models = self

    def generate_content(self, model: str, contents: str):
        respuesta = self._cliente.beta.messages.create(
            model=model,
            max_tokens=self.max_tokens,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": contents}],
        )
        if respuesta.stop_reason == "refusal":
            categoria = getattr(getattr(respuesta, "stop_details", None), "category", None)
            raise RuntimeError(f"el modelo declinó el lote (categoría: {categoria or 'sin dato'})")
        texto = "".join(b.text for b in respuesta.content if getattr(b, "type", "") == "text")
        return _Respuesta(texto)


@dataclass
class _Respuesta:
    text: str


def cargar_cliente(proveedor: str):
    """El cliente del proveedor pedido (gemini o claude)."""
    if proveedor == "claude":
        return ClienteClaude()
    return load_config()


def modelo_por_defecto(proveedor: str) -> str:
    return MODELO_CLAUDE if proveedor == "claude" else get_model()


def load_config():
    """Load configuration and return GenAI Client."""
    if genai is None:
        raise ImportError(
            "El paquete 'google-genai' no está instalado: `voight ai` requiere el extra opcional 'ai'. "
            'Instalalo con: uv tool install "questions[ai] @ git+https://github.com/INGCOM-UNRN/moodle-toolbox"'
        )
    api_key = get_api_key()
    if not api_key:
        raise ValueError("❌ Error: GEMINI_API_KEY no encontrada. Usa 'voight config set-key <KEY>' para configurarla.")
    return genai.Client(api_key=api_key)


def list_available_models(client) -> List[str]:
    """Lista los modelos generativos disponibles en Gemini."""
    try:
        return [m.name for m in client.models.list() if 'generateContent' in m.supported_methods]
    except Exception as e:
        print(f"❌ Error al listar modelos: {e}")
        return []


# ---------------------------------------------------------------------------
# Prompt y respuesta
# ---------------------------------------------------------------------------

_CONVENCIONES = (
    "Formato: cada pregunta es GIFT de Moodle. El código va siempre entre ``` o `...`, en ASCII normal "
    "y sin escapar (el código fuera de esos delimitadores rompe el GIFT)."
)


def construir_prompt(textos: List[str], mode: str, custom_prompt: Optional[str] = None) -> str:
    if mode == "improve":
        instruccion = (
            "Sos experto en pedagogía y en el formato GIFT de Moodle. Mejorá la claridad, la gramática y la "
            "calidad pedagógica de cada pregunta sin cambiar su tipo ni lo que evalúa."
        )
        if custom_prompt:
            instruccion += f"\nInstrucción adicional: {custom_prompt}"
        salida = "una pregunta por cada una recibida"
    elif mode == "multiply":
        instruccion = (
            f"Sos experto en pedagogía y en el formato GIFT de Moodle. Creá {VARIACIONES} variaciones de cada "
            "pregunta que evalúen el mismo objetivo con otro contexto o distractores."
        )
        if custom_prompt:
            instruccion += f"\nInstrucción adicional: {custom_prompt}"
        salida = f"{VARIACIONES} preguntas por cada una recibida, cada una precedida por su marcador"
    elif mode == "feedback":
        instruccion = (
            "Sos experto en pedagogía y en el formato GIFT de Moodle. Completá SÓLO la retroalimentación que "
            "falta en cada pregunta: a cada opción sin `#` agregale una explicación breve de por qué es correcta "
            "o incorrecta (el error conceptual que revela), y si no tiene retroalimentación general (`####`), "
            "agregala. En verdadero/falso, `{T#para quien responde mal#para quien acierta}`. No cambies el "
            "título, el enunciado, las opciones ni la retroalimentación que ya existe."
        )
        if custom_prompt:
            instruccion += f"\nInstrucción adicional: {custom_prompt}"
        salida = "una pregunta por cada una recibida"
    elif mode == "distractors":
        instruccion = (
            f"Sos experto en pedagogía y en el formato GIFT de Moodle. Agregá a cada pregunta distractores (~) "
            f"plausibles, basados en errores conceptuales comunes del tema, hasta que tenga {OPCIONES_OBJETIVO[0]} "
            "opciones en total. Si la respuesta correcta es mucho más larga que los distractores, los nuevos "
            "deben tener un largo parecido al de la correcta. Cada distractor nuevo puede llevar su "
            "retroalimentación (#). No cambies el enunciado, la respuesta correcta ni los distractores existentes."
        )
        if custom_prompt:
            instruccion += f"\nInstrucción adicional: {custom_prompt}"
        salida = "una pregunta por cada una recibida"
    else:  # transform
        instruccion = (
            "Sos experto en el formato GIFT de Moodle. Transformá cada pregunta según estas instrucciones:\n"
            f"{custom_prompt or 'Mejorá las preguntas manteniendo el formato GIFT.'}"
        )
        salida = "una pregunta por cada una recibida"

    lote = "\n\n".join(f"--- PREGUNTA {i} ---\n{t}" for i, t in enumerate(textos, 1))
    return (
        f"{instruccion}\n{_CONVENCIONES}\n\n"
        f"Devolvé {salida}, en el mismo orden y precedida por la misma línea '--- PREGUNTA n ---' "
        "que la original. Sin explicaciones ni bloques ``` alrededor.\n\n"
        f"{lote}"
    )


_MARCADOR = re.compile(r"^-{3,}\s*PREGUNTA\s+(\d+)\s*-{3,}\s*$", re.MULTILINE | re.IGNORECASE)


def _sin_cerco(texto: str) -> str:
    """Quita un ```gift … ``` que envuelva todo el texto (una pregunta nunca empieza con ```)."""
    texto = texto.strip()
    if texto.startswith("```") and texto.endswith("```") and "\n" in texto:
        return texto.split("\n", 1)[1][:-3].strip()
    return texto


def separar_respuesta(texto: str, cantidad: int) -> Dict[int, List[str]]:
    """Asigna cada pregunta devuelta a su número de pregunta enviada."""
    texto = _sin_cerco(texto)
    marcas = list(_MARCADOR.finditer(texto))
    resultado: Dict[int, List[str]] = {}
    if marcas:
        for actual, siguiente in zip(marcas, marcas[1:] + [None], strict=False):
            numero = int(actual.group(1))
            bloque = _sin_cerco(texto[actual.end():siguiente.start() if siguiente else len(texto)])
            if bloque and 1 <= numero <= cantidad:
                resultado.setdefault(numero, []).append(bloque)
        return resultado
    # Sin marcadores: separadores '---' en su propia línea, en orden.
    bloques = [_sin_cerco(b) for b in re.split(r"^-{3,}\s*$", texto, flags=re.MULTILINE)]
    for i, bloque in enumerate(b for b in bloques if b):
        if i < cantidad:
            resultado[i + 1] = [bloque]
    return resultado


def _interpretar(gift: str) -> Optional[tuple]:
    """(GIFT protegido, Question) si el texto es exactamente una pregunta GIFT válida."""
    # El código de la respuesta viene crudo (así se envió): se protege sin desescapar.
    gift, _ = transformar_codigo(gift, contexto="gift", fullwidth=True, espacios=False, saltos=False, escapes=False)
    preguntas = [q for q in GiftParser()._manual_parse(gift) if q.type != "Category"]
    if len(preguntas) != 1 or preguntas[0].type not in TIPOS_PROCESABLES:
        return None
    return gift, preguntas[0]


def aplicar_respuesta(unidades: List[Unidad], respuesta: Dict[int, List[str]], mode: str) -> int:
    """Valida y asigna lo devuelto a cada unidad. Devuelve cuántas quedaron sin cambios."""
    sin_cambios = 0
    for numero, unidad in enumerate(unidades, 1):
        validas = []
        for bloque in respuesta.get(numero, []):
            interpretado = _interpretar(bloque)
            if interpretado is None:
                print(f"  ⚠️ Pregunta {numero} ({unidad.archivo.name}): la respuesta no es una pregunta GIFT válida.")
                continue
            if mode != "multiply" and interpretado[1].type != unidad.tipo:
                print(f"  ⚠️ Pregunta {numero} ({unidad.archivo.name}): el modelo cambió el tipo "
                      f"{unidad.tipo} → {interpretado[1].type}; se conserva el original.")
                continue
            if mode in ("improve", "feedback") and _forma(interpretado[1]) != unidad.forma:
                # Típico de un = o ~ crudo fuera del código que parte una opción.
                print(f"  ⚠️ Pregunta {numero} ({unidad.archivo.name}): cambió la cantidad de opciones o de "
                      "correctas; se conserva el original.")
                continue
            validas.append(interpretado)
        if mode != "multiply":
            validas = validas[:1]
        if not validas:
            sin_cambios += 1
            continue
        if mode == "distractors":
            completa, agregados = agregar_distractores(unidad.pregunta, validas[0][1], OPCIONES_OBJETIVO[0])
            if not agregados:
                print(f"  ⚠️ Pregunta {numero} ({unidad.archivo.name}): la respuesta no agrega distractores "
                      "nuevos o cambia los existentes; se conserva el original.")
                sin_cambios += 1
                continue
            unidad.parcial = "distractores"
            unidad.procesado = [completa]
            unidad.procesado_gift = [question_to_gift(completa)]
            continue
        if mode == "feedback":
            # Del resultado sólo se toma la retroalimentación que faltaba; lo demás es el original.
            completa, agregadas = completar_feedback(unidad.pregunta, validas[0][1])
            if not agregadas:
                sin_cambios += 1
                continue
            unidad.parcial = "feedback"
            unidad.procesado = [completa]
            unidad.procesado_gift = [question_to_gift(completa)]
            continue
        unidad.procesado_gift = [g for g, _ in validas]
        unidad.procesado = [q for _, q in validas]
    return sin_cambios


OPCIONES_OBJETIVO = [4]  # ai --mode distractors --opciones N (lista para que el prompt la lea)


def _normal_opcion(c) -> str:
    return " ".join(re.sub(r"[`*_]", "", (c.text.text if c.text else "")).lower().split())


def necesita_distractores(q: Question, objetivo: int, umbral_largo: float = 1.5) -> bool:
    """Opción múltiple con menos de `objetivo` opciones o cuya correcta delata por su largo."""
    if q.type != "MC" or not q.choices:
        return False
    if len(q.choices) < objetivo:
        return True
    correctas = [len(_normal_opcion(c)) for c in q.choices if c.is_correct or (c.weight or 0) > 0]
    distractores = [len(_normal_opcion(c)) for c in q.choices if not (c.is_correct or (c.weight or 0) > 0)]
    return bool(correctas and distractores and min(distractores) > 0
                and sum(correctas) / len(correctas) >= umbral_largo * sum(distractores) / len(distractores))


def agregar_distractores(original: Question, nueva: Question, objetivo: int) -> tuple:
    """El original más los distractores nuevos de `nueva` (incorrectos y con texto distinto a
    todas las opciones originales), hasta `objetivo` opciones o dos más que el original.

    Si la respuesta quita o cambia una opción original, o la correcta, no se agrega nada.
    Devuelve (pregunta, cantidad agregada).
    """
    originales = [_normal_opcion(c) for c in original.choices]
    nuevas = [_normal_opcion(c) for c in nueva.choices]
    correctas = {_normal_opcion(c) for c in original.choices if c.is_correct or (c.weight or 0) > 0}
    correctas_nueva = {_normal_opcion(c) for c in nueva.choices if c.is_correct or (c.weight or 0) > 0}
    if not set(originales) <= set(nuevas) or correctas != correctas_nueva:
        return original, 0
    tope = max(objetivo, len(original.choices) + 2) if len(original.choices) >= objetivo else objetivo
    completa = copy.deepcopy(original)
    vistos = set(originales)
    for c, texto in zip(nueva.choices, nuevas, strict=False):
        if len(completa.choices) >= tope:
            break
        if texto and texto not in vistos and not c.is_correct and not (c.weight or 0) > 0:
            completa.choices.append(copy.deepcopy(c))
            vistos.add(texto)
    return completa, len(completa.choices) - len(original.choices)


def _hay(ft) -> bool:
    return ft is not None and bool((ft.text or "").strip())


def falta_feedback(q: Question) -> bool:
    """True si a la pregunta le falta alguna retroalimentación (general o de una opción)."""
    if not _hay(q.global_feedback):
        return True
    if q.type == "TF":
        return not (_hay(q.true_feedback) and _hay(q.false_feedback))
    return any(not _hay(c.feedback) for c in q.choices)


def completar_feedback(original: Question, nueva: Question) -> tuple:
    """El original con la retroalimentación que le faltaba tomada de `nueva`.

    Nunca reemplaza una retroalimentación existente ni toma ningún otro cambio.
    Devuelve (pregunta, cantidad de retroalimentaciones agregadas).
    """
    completa = copy.deepcopy(original)
    agregadas = 0
    if not _hay(completa.global_feedback) and _hay(nueva.global_feedback):
        completa.global_feedback = copy.deepcopy(nueva.global_feedback)
        agregadas += 1
    if completa.type == "TF":
        for campo in ("true_feedback", "false_feedback"):
            if not _hay(getattr(completa, campo)) and _hay(getattr(nueva, campo)):
                setattr(completa, campo, copy.deepcopy(getattr(nueva, campo)))
                agregadas += 1
    for c, n in zip(completa.choices, nueva.choices, strict=False):
        if not _hay(c.feedback) and _hay(n.feedback):
            c.feedback = copy.deepcopy(n.feedback)
            agregadas += 1
    return completa, agregadas


def _clave_cache(model_id: str, mode: str, custom_prompt: Optional[str], unidad: Unidad) -> str:
    extra = OPCIONES_OBJETIVO[0] if mode == "distractors" else None
    return Cache.clave("ai", model_id, mode, custom_prompt or "", extra, unidad.texto)


def process_batch(client, model_id: str, unidades: List[Unidad], mode: str,
                  custom_prompt: Optional[str] = None, cache: Optional[Cache] = None) -> int:
    """Envía un lote al modelo y aplica la respuesta. Devuelve cuántas quedaron sin cambios.

    Con `cache`, las respuestas por pregunta se guardan bajo el hash de lo enviado.
    """
    if not unidades:
        return 0
    prompt = construir_prompt([u.texto for u in unidades], mode, custom_prompt)
    try:
        response = client.models.generate_content(model=model_id, contents=prompt)
    except Exception as e:  # noqa: BLE001
        print(f"❌ Error procesando lote con el modelo: {e}")
        return len(unidades)
    respuesta = separar_respuesta(response.text or "", len(unidades))
    if cache is not None:
        for numero, unidad in enumerate(unidades, 1):
            if respuesta.get(numero):
                cache.guardar(_clave_cache(model_id, mode, custom_prompt, unidad), respuesta[numero])
    return aplicar_respuesta(unidades, respuesta, mode)


def desde_cache(unidades: List[Unidad], model_id: str, mode: str, custom_prompt: Optional[str],
                cache: Cache) -> List[Unidad]:
    """Aplica las respuestas en caché y devuelve las unidades que hay que enviar."""
    pendientes = []
    for unidad in unidades:
        guardada = cache.obtener(_clave_cache(model_id, mode, custom_prompt, unidad))
        if guardada:
            aplicar_respuesta([unidad], {1: guardada}, mode)
        else:
            pendientes.append(unidad)
    return pendientes


# ---------------------------------------------------------------------------
# Escritura: cada formato vuelve a su convención original
# ---------------------------------------------------------------------------

def _gift_final(gift: str, unidad: Unidad) -> str:
    gift, _ = transformar_codigo(gift, contexto="gift", fullwidth=True, espacios=unidad.marcas, saltos=unidad.marcas)
    return format_gift_content(gift).strip()


def _sin_id(lineas: List[str]) -> List[str]:
    """Las variaciones no heredan el [id:…] del original (tiene que ser único)."""
    return [linea for linea in (re.sub(r"\s*\[id:[^\]]*\]", "", ln) for ln in lineas) if linea.strip() not in ("", "//")]


def escribir_gift(archivo: Archivo) -> str:
    bloques = []
    for s in archivo.segmentos:
        if not isinstance(s, Unidad):
            bloques.append(s)
        elif not s.procesado_gift:
            bloques.append(s.original)
        else:
            for i, gift in enumerate(s.procesado_gift):
                prefijo = s.prefijo if i == 0 else _sin_id(s.prefijo)
                bloques.append("\n".join(prefijo + [_gift_final(gift, s)]))
    return "\n\n".join(bloques) + "\n"


def _poner_texto(padre: ET.Element, texto: str) -> None:
    t = padre.find("text")
    if t is None:
        t = ET.SubElement(padre, "text")
    t.text = texto


def _hijo(el: ET.Element, tag: str, formato: Optional[str] = None) -> ET.Element:
    hijo = el.find(tag)
    if hijo is None:
        hijo = ET.SubElement(el, tag, {"format": formato} if formato else {})
    return hijo


def aplicar_a_xml(original: ET.Element, q: Question, unidad: Unidad, variacion: bool = False) -> ET.Element:
    """Copia el <question> original con el contenido de `q` (lo que GIFT no tiene se conserva)."""
    if unidad.fullwidth:
        def adaptar(texto):
            return transformar_codigo(texto or "", contexto="xml", fullwidth=True,
                                      espacios=unidad.marcas, saltos=unidad.marcas)[0]
    else:
        def adaptar(texto):
            return transformar_codigo(texto or "", contexto="xml", fullwidth=False)[0]

    el = copy.deepcopy(original)
    if q.title:
        _poner_texto(_hijo(el, "name"), q.title)
    qt = _hijo(el, "questiontext", "html")
    _poner_texto(qt, adaptar(q.stem.text if q.stem else ""))
    formato = qt.get("format") or "html"
    if q.global_feedback is not None or el.find("generalfeedback") is not None:
        _poner_texto(_hijo(el, "generalfeedback", formato), adaptar(q.global_feedback.text if q.global_feedback else ""))
    idnumber = el.find("idnumber")
    if variacion and idnumber is not None:
        idnumber.text = None

    hijos = list(el)

    def reemplazar(tag: str, nuevos: List[ET.Element]) -> None:
        viejos = el.findall(tag)
        posicion = hijos.index(viejos[0]) if viejos else len(list(el))
        for v in viejos:
            el.remove(v)
        for i, n in enumerate(nuevos):
            el.insert(posicion + i, n)

    def respuesta(i: int, viejas: List[ET.Element]) -> ET.Element:
        if i < len(viejas):
            return copy.deepcopy(viejas[i])
        return copy.deepcopy(viejas[0]) if viejas else ET.Element("answer", {"format": formato})

    if q.type in ("MC", "Short", "Numerical"):
        viejas = el.findall("answer")
        nuevas = []
        for i, c in enumerate(q.choices):
            a = respuesta(i, viejas)
            fraccion = c.weight if c.weight is not None else (100.0 if c.is_correct else 0.0)
            a.set("fraction", f"{fraccion:g}")
            texto = c.text.text if c.text else ""
            if q.type == "Numerical":
                numero, _, tolerancia = texto.partition(":")
                _poner_texto(a, numero.strip())
                tol = a.find("tolerance")
                if tolerancia.strip():
                    (tol if tol is not None else ET.SubElement(a, "tolerance")).text = tolerancia.strip()
                elif tol is not None:
                    a.remove(tol)
            else:
                _poner_texto(a, adaptar(texto))
            _poner_texto(_hijo(a, "feedback", formato), adaptar(c.feedback.text if c.feedback else ""))
            nuevas.append(a)
        reemplazar("answer", nuevas)
        single = el.find("single")
        if q.type == "MC" and single is not None:
            single.text = "true" if any(c.is_correct and c.weight is None for c in q.choices) else "false"
    elif q.type == "TF":
        por_valor = {(a.findtext("text") or "").strip().lower(): a for a in el.findall("answer")}
        nuevas = []
        for valor, retro in (("true", q.true_feedback), ("false", q.false_feedback)):
            a = copy.deepcopy(por_valor[valor]) if valor in por_valor else ET.Element("answer")
            a.set("fraction", "100" if q.is_true == (valor == "true") else "0")
            _poner_texto(a, valor)
            _poner_texto(_hijo(a, "feedback", formato), adaptar(retro.text if retro else ""))
            nuevas.append(a)
        reemplazar("answer", nuevas)
    elif q.type == "Matching":
        viejas = el.findall("subquestion")
        nuevas = []
        for i, par in enumerate(q.match_pairs):
            sq = copy.deepcopy(viejas[i] if i < len(viejas) else viejas[0]) if viejas else ET.Element("subquestion", {"format": formato})
            _poner_texto(sq, adaptar(par.subquestion.text))
            _poner_texto(_hijo(sq, "answer"), adaptar(par.subanswer))
            nuevas.append(sq)
        reemplazar("subquestion", nuevas)
    return el


def escribir_xml(archivo: Archivo) -> str:
    quiz = ET.Element("quiz")
    for s in archivo.segmentos:
        if not isinstance(s, Unidad):
            quiz.append(s)
        elif not s.procesado:
            quiz.append(s.nodo)
        elif s.parcial == "feedback":
            quiz.append(agregar_feedback_xml(s.nodo, s.procesado[0], s))
        elif s.parcial == "distractores":
            quiz.append(agregar_distractores_xml(s.nodo, s.procesado[0], s))
        else:
            for i, q in enumerate(s.procesado):
                quiz.append(aplicar_a_xml(s.nodo, q, s, variacion=i > 0))
    return serializar_quiz(quiz)


def _formato_enunciado(el: ET.Element) -> str:
    enunciado = el.find("questiontext")
    return (enunciado.get("format") if enunciado is not None else None) or "html"


def agregar_distractores_xml(original: ET.Element, q: Question, unidad: Unidad) -> ET.Element:
    """Copia el <question> original y agrega al final las respuestas nuevas (fracción 0)."""
    if unidad.fullwidth:
        def adaptar(texto):
            return transformar_codigo(texto or "", contexto="xml", fullwidth=True,
                                      espacios=unidad.marcas, saltos=unidad.marcas)[0]
    else:
        def adaptar(texto):
            return transformar_codigo(texto or "", contexto="xml", fullwidth=False)[0]

    el = copy.deepcopy(original)
    respuestas = el.findall("answer")
    formato = _formato_enunciado(el)
    plantilla = next((a for a in respuestas if a.get("fraction", "0") in ("0", "0.0")), respuestas[0] if respuestas else None)
    posicion = list(el).index(respuestas[-1]) + 1 if respuestas else len(list(el))
    for i, c in enumerate(q.choices[len(respuestas):]):
        nueva = copy.deepcopy(plantilla) if plantilla is not None else ET.Element("answer", {"format": formato})
        nueva.set("fraction", "0")
        _poner_texto(nueva, adaptar(c.text.text if c.text else ""))
        retro = _hijo(nueva, "feedback", formato)
        _poner_texto(retro, adaptar(c.feedback.text) if _hay(c.feedback) else "")
        el.insert(posicion + i, nueva)
    return el


def agregar_feedback_xml(original: ET.Element, q: Question, unidad: Unidad) -> ET.Element:
    """Copia el <question> original y sólo completa los <feedback> y el <generalfeedback> vacíos."""
    if unidad.fullwidth:
        def adaptar(texto):
            return transformar_codigo(texto or "", contexto="xml", fullwidth=True,
                                      espacios=unidad.marcas, saltos=unidad.marcas)[0]
    else:
        def adaptar(texto):
            return transformar_codigo(texto or "", contexto="xml", fullwidth=False)[0]

    el = copy.deepcopy(original)
    formato = _formato_enunciado(el)

    def completar(padre: ET.Element, tag: str, ft) -> None:
        if not _hay(ft):
            return
        nodo = padre.find(tag)
        if nodo is None:
            nodo = ET.SubElement(padre, tag, {"format": formato})
        if not (nodo.findtext("text") or "").strip():
            _poner_texto(nodo, adaptar(ft.text))

    completar(el, "generalfeedback", q.global_feedback)
    respuestas = el.findall("answer")
    if q.type == "TF":
        por_valor = {(a.findtext("text") or "").strip().lower(): a for a in respuestas}
        if "true" in por_valor:
            completar(por_valor["true"], "feedback", q.true_feedback)
        if "false" in por_valor:
            completar(por_valor["false"], "feedback", q.false_feedback)
    else:
        for a, c in zip(respuestas, q.choices, strict=False):
            completar(a, "feedback", c.feedback)
    return el


def escribir(archivo: Archivo) -> str:
    return escribir_xml(archivo) if archivo.formato == "xml" else escribir_gift(archivo)


# ---------------------------------------------------------------------------
# Proceso global
# ---------------------------------------------------------------------------

CARACTERES_POR_TOKEN = 4  # aproximación usual para texto mayormente ASCII
SALIDA_POR_MODO = {"multiply": VARIACIONES, "feedback": 1.4, "distractors": 1.4}


def estimar_tokens(unidades: List[Unidad], mode: str, custom_prompt: Optional[str], batch_size: int) -> Dict[str, int]:
    """Tokens aproximados de entrada (prompts completos) y de salida (preguntas devueltas)."""
    entrada = salida = 0
    for i in range(0, len(unidades), batch_size):
        lote = unidades[i:i + batch_size]
        entrada += len(construir_prompt([u.texto for u in lote], mode, custom_prompt))
        salida += sum(len(u.texto) for u in lote)
    factor = SALIDA_POR_MODO.get(mode, 1)
    return {"entrada": round(entrada / CARACTERES_POR_TOKEN), "salida": round(salida * factor / CARACTERES_POR_TOKEN)}


def describir_costo(tokens: Dict[str, int], precio_entrada: Optional[float], precio_salida: Optional[float]) -> str:
    texto = f"≈{tokens['entrada']:,} tokens de entrada y ≈{tokens['salida']:,} de salida (aprox. 4 caracteres por token)"
    if precio_entrada is not None or precio_salida is not None:
        costo = tokens["entrada"] * (precio_entrada or 0) / 1e6 + tokens["salida"] * (precio_salida or 0) / 1e6
        texto += f"; costo estimado ≈ USD {costo:,.2f}"
    return texto.replace(",", ".")


def estadisticas(unidades: List[Unidad]) -> Dict[str, int]:
    original = sum(len(u.original) for u in unidades)
    enviado = sum(len(u.texto) for u in unidades)
    return {"preguntas": len(unidades), "caracteres_original": original, "caracteres_enviados": enviado}


def run_global_ai_processing(client, model_id: str, file_paths: List[Path], output_dir: Optional[Path], mode: str,
                             custom_prompt: Optional[str] = None, batch_size: int = 5, in_place: bool = False,
                             suffix: Optional[str] = None, dry_run: bool = False, usar_cache: bool = True,
                             precio_entrada: Optional[float] = None, precio_salida: Optional[float] = None):
    """Procesa todas las preguntas de todos los archivos (GIFT y XML) en lotes globales."""
    print(f"🔍 Escaneando {len(file_paths)} archivos...")
    archivos = leer_archivos(file_paths)
    unidades = unidades_de(archivos)
    if mode == "feedback":
        unidades = [u for u in unidades if u.pregunta is not None and falta_feedback(u.pregunta)]
    elif mode == "distractors":
        unidades = [u for u in unidades if u.pregunta is not None and necesita_distractores(u.pregunta, OPCIONES_OBJETIVO[0])]
    if not unidades:
        print("⚠️ No se encontraron preguntas para procesar.")
        return

    datos = estadisticas(unidades)
    ahorro = 100 - datos["caracteres_enviados"] * 100 // max(datos["caracteres_original"], 1)
    print(f"📏 {datos['preguntas']} preguntas: se envían {datos['caracteres_enviados']} caracteres "
          f"de {datos['caracteres_original']} en los archivos ({ahorro}% menos).")

    lotes = [unidades[i:i + batch_size] for i in range(0, len(unidades), batch_size)]
    if dry_run:
        pendientes_sim = [u for u in unidades
                          if Cache("ai", activa=usar_cache).obtener(_clave_cache(model_id, mode, custom_prompt, u)) is None]
        en_cache = len(unidades) - len(pendientes_sim)
        print(f"💰 {describir_costo(estimar_tokens(pendientes_sim, mode, custom_prompt, batch_size), precio_entrada, precio_salida)}"
              + (f" ({en_cache} preguntas ya están en la caché)" if en_cache else ""))
        print(f"🧪 Simulación: {len(lotes)} lotes; no se llama al modelo. Primer lote:\n")
        print(construir_prompt([u.texto for u in lotes[0]], mode, custom_prompt))
        return

    cache = Cache("ai", activa=usar_cache)
    pendientes = desde_cache(unidades, model_id, mode, custom_prompt, cache)
    if cache.aciertos:
        print(f"♻️  {cache.aciertos} preguntas resueltas desde la caché (sin consultar al modelo).")
    lotes = [pendientes[i:i + batch_size] for i in range(0, len(pendientes), batch_size)]
    if pendientes:
        print(f"💰 {describir_costo(estimar_tokens(pendientes, mode, custom_prompt, batch_size), precio_entrada, precio_salida)}")
    print(f"🚀 Procesando en {len(lotes)} lotes de hasta {batch_size} preguntas...")
    sin_cambios = 0
    for n, lote in enumerate(lotes, 1):
        print(f"  📦 Lote {n}/{len(lotes)} ({len(lote)} preguntas)...")
        sin_cambios += process_batch(client, model_id, lote, mode, custom_prompt, cache)

    print("💾 Guardando resultados...")
    # En el directorio de salida se conserva la estructura relativa: en un banco hay
    # muchos q01.gift en carpetas distintas que, aplanados, se pisarían.
    base = Path(os.path.commonpath([str(a.ruta.parent.resolve()) for a in archivos]))
    for archivo in archivos:
        contenido = escribir(archivo)
        ruta = archivo.ruta
        if in_place:
            destino = ruta.parent / f"{ruta.stem}{suffix}{ruta.suffix}" if suffix else ruta
        else:
            if output_dir is None:
                raise ValueError("Sin --in-place hace falta un directorio de salida.")
            destino = output_dir / ruta.parent.resolve().relative_to(base) / f"{ruta.stem}_{mode}{ruta.suffix}"
            destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(contenido, encoding="utf-8")
        print(f"  ✓ {destino}")

    if sin_cambios:
        print(f"⚠️ {sin_cambios} preguntas quedaron como estaban (respuesta ausente o inválida).")
    print(f"\n✅ Finalizado: {len(archivos)} archivos procesados.")
