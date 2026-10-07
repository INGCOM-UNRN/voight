"""Clasificación de preguntas con Jev (TypeSafe System One): Bloom y dificultad.

Por pregunta se hacen tres juicios en una sola solicitud (corren en paralelo):

- `bloom`: Choice entre los seis niveles de la taxonomía revisada (B1–B6).
- `enunciado`: Score de 5 niveles, cuán difícil es entender y resolver lo que pide.
- `respuestas`: Score de 5 niveles, cuán difícil es distinguir la correcta de los
  distractores (sólo opción múltiple y emparejamiento).

El estado es JSON con el contexto del curso, el tipo, el enunciado y las opciones
(con la correcta marcada); el código va en ASCII y la retroalimentación no se envía
(revela la respuesta). El resultado se escribe como un comentario por pregunta —en
GIFT una línea `// [bloom:…] …`, en XML un `<!-- … -->` antes del `<question>`— que se
reemplaza al reclasificar; con `tags` también como tags de Moodle.

API: https://docs.typesafe.ai/api.md (la clave TYPESAFE_API_KEY se busca en el entorno,
`.env.local`, `~/.env` y `~/.questions/.env`).
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional

from voight.core.lector import Archivo, Unidad, _compactar, leer_archivos, unidades_de
from voight.core.cache import Cache
from voight.core.gift_model import Question
from voight.core.tree import serializar_quiz

API_URL = "https://api.typesafe.ai/v1/systemone"
MODELO = "jev-latest"
CONTEXTO = "Curso universitario de programación (primer y segundo año), con preguntas de C y Java."
MAX_ENUNCIADO = 6000
MARCA = "[clasificacion:"

BLOOM = {
    "recordar": "Recuperar de memoria un dato, una definición, una regla de sintaxis o un nombre, sin "
                "interpretarlo (p. ej. qué palabra clave declara una constante).",
    "comprender": "Explicar o reconocer el significado de un concepto, de un mensaje o de un fragmento de "
                  "código; parafrasear, clasificar o dar un ejemplo, sin ejecutarlo con datos nuevos.",
    "aplicar": "Usar un procedimiento o una regla en un caso concreto: trazar la ejecución de un código, "
               "calcular su salida o elegir la construcción correcta para una tarea dada.",
    "analizar": "Descomponer y relacionar partes: encontrar el error en un programa, distinguir causas y "
                "efectos, comparar alternativas por su estructura o su comportamiento.",
    "evaluar": "Juzgar con criterios: decidir qué solución es mejor, más segura o más adecuada entre "
               "alternativas válidas y por qué.",
    "crear": "Producir algo nuevo: diseñar o completar un algoritmo, una función o una estructura que "
             "resuelva un problema original.",
}
CODIGO_BLOOM = {nivel: f"B{i}" for i, nivel in enumerate(BLOOM, 1)}

NIVELES_ENUNCIADO = [
    "Se responde con una lectura directa: pregunta breve, sin código o con código trivial y vocabulario conocido.",
    "Requiere un solo paso de razonamiento o un concepto básico; si hay código, es corto y lineal.",
    "Requiere combinar dos o tres conceptos o seguir código con una estructura de control o un caso particular.",
    "Requiere seguir varias interacciones (bucles anidados, punteros, llamadas, estado que cambia) o notar un "
    "detalle sutil del enunciado.",
    "Requiere dominio profundo: casos borde, comportamiento indefinido, muchos conceptos que interactúan o "
    "código extenso y engañoso.",
]
NIVELES_RESPUESTAS = [
    "La correcta es obvia: los distractores son absurdos, de otro tema o se descartan sin pensar.",
    "Casi todos los distractores se descartan con facilidad; queda a lo sumo una alternativa plausible.",
    "Los distractores son plausibles, pero el concepto evaluado alcanza para distinguir la correcta.",
    "Varios distractores representan errores comunes y se parecen a la correcta; hace falta precisión.",
    "Las opciones difieren en detalles finos; sólo un dominio sólido permite distinguir la correcta.",
]

_TIPOS = {
    "MC": "opción múltiple", "TF": "verdadero/falso", "Short": "respuesta corta",
    "Numerical": "numérica", "Matching": "emparejamiento", "Essay": "ensayo", "Description": "descripción",
}
CON_OPCIONES = ("MC", "Matching")


# ---------------------------------------------------------------------------
# Cliente HTTP (sin dependencias)
# ---------------------------------------------------------------------------

def resolver_clave() -> Optional[str]:
    if os.environ.get("TYPESAFE_API_KEY"):
        return os.environ["TYPESAFE_API_KEY"].strip()
    for archivo in (Path.cwd() / ".env.local", Path.home() / ".env", Path.home() / ".questions" / ".env"):
        if archivo.exists():
            m = re.search(r"^\s*(?:export\s+)?TYPESAFE_API_KEY\s*=\s*['\"]?([^'\"\r\n]+)",
                          archivo.read_text(encoding="utf-8", errors="replace"), re.MULTILINE)
            if m:
                return m.group(1).strip()
    return None


class ClienteJev:
    """POST /v1/systemone con reintentos ante 429/529/5xx y errores de red."""

    def __init__(self, clave: Optional[str] = None, modelo: str = MODELO, reintentos: int = 5, espera: float = 1.0,
                 cache: Optional[Cache] = None):
        self.cache = cache
        self.clave = clave or resolver_clave()
        if not self.clave:
            raise ValueError("No se encontró TYPESAFE_API_KEY (entorno, .env.local, ~/.env o ~/.questions/.env). "
                             "Configurala con `voight config set-typesafe-key <KEY>`.")
        self.modelo = modelo
        self.reintentos = reintentos
        self.espera = espera

    def consultar(self, state, questions: dict) -> dict:
        clave_cache = Cache.clave("jev", self.modelo, state, questions)
        if self.cache is not None:
            guardada = self.cache.obtener(clave_cache)
            if guardada is not None:
                return guardada
        respuesta = self._consultar(state, questions)
        if self.cache is not None:
            self.cache.guardar(clave_cache, respuesta)
        return respuesta

    def _consultar(self, state, questions: dict) -> dict:
        cuerpo = json.dumps({"state": state, "model": self.modelo, "questions": questions}).encode("utf-8")
        for intento in range(self.reintentos):
            pedido = urllib.request.Request(API_URL, data=cuerpo, method="POST", headers={
                "Authorization": f"Bearer {self.clave}", "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(pedido, timeout=60) as respuesta:
                    return json.loads(respuesta.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                detalle = e.read().decode("utf-8", errors="replace")[:300]
                if e.code not in (429, 500, 502, 503, 504, 529) or intento == self.reintentos - 1:
                    raise RuntimeError(f"TypeSafe respondió {e.code}: {detalle}") from None
            except (urllib.error.URLError, TimeoutError) as e:
                if intento == self.reintentos - 1:
                    raise RuntimeError(f"No se pudo contactar a TypeSafe: {e}") from None
            time.sleep(self.espera * 2 ** intento)
        raise RuntimeError("TypeSafe no respondió")


# ---------------------------------------------------------------------------
# Estado y preguntas para Jev
# ---------------------------------------------------------------------------

def _t(ft) -> str:
    return _compactar(ft.text, "xml") if ft is not None and ft.text else ""


def estado(q: Question, contexto: str = CONTEXTO) -> dict:
    """La pregunta como JSON con nombres claros; sin feedback (revelaría la respuesta)."""
    enunciado = _t(q.stem)
    if len(enunciado) > MAX_ENUNCIADO:
        enunciado = enunciado[:MAX_ENUNCIADO] + "\n[…enunciado recortado…]"
    datos: Dict[str, Any] = {"contexto": contexto, "tipo": _TIPOS.get(q.type, q.type), "enunciado": enunciado}
    if q.title:
        datos["titulo"] = q.title
    if q.type == "MC":
        datos["opciones"] = [
            {"texto": _t(c.text), "correcta": bool(c.is_correct or (c.weight or 0) > 0),
             **({"porcentaje": c.weight} if c.weight is not None else {})}
            for c in q.choices
        ]
    elif q.type in ("Short", "Numerical"):
        datos["respuestas_aceptadas"] = [_t(c.text) for c in q.choices if c.is_correct or (c.weight or 0) > 0]
    elif q.type == "TF":
        datos["respuesta_correcta"] = "verdadero" if q.is_true else "falso"
    elif q.type == "Matching":
        datos["pares"] = [{"elemento": _t(p.subquestion), "corresponde_a": _compactar(p.subanswer or "", "xml")}
                          for p in q.match_pairs]
    return datos


def preguntas_jev(q: Question) -> dict:
    preguntas = {
        "bloom": {
            "type": "choice",
            "instructions": "¿Qué proceso cognitivo de la taxonomía de Bloom revisada exige principalmente "
                            "responder esta pregunta (`enunciado`, y `opciones` o `pares` si los hay) a un "
                            "estudiante del curso descrito en `contexto`?",
            "criteria": BLOOM,
        },
        "enunciado": {
            "type": "score",
            "instructions": "Para un estudiante del curso descrito en `contexto`, ¿cuán difícil es entender el "
                            "`enunciado` y resolver lo que pide, antes de mirar las opciones?",
            "criteria": NIVELES_ENUNCIADO,
        },
    }
    if q.type in CON_OPCIONES:
        preguntas["respuestas"] = {
            "type": "score",
            "instructions": "Sabiendo cuál es la respuesta correcta (`opciones[].correcta` o `pares`), ¿cuán "
                            "difícil es para un estudiante del curso descrito en `contexto` distinguirla de las "
                            "demás opciones?",
            "criteria": NIVELES_RESPUESTAS,
        }
    return preguntas


# ---------------------------------------------------------------------------
# Resultado y metadatos
# ---------------------------------------------------------------------------

@dataclass
class Clasificacion:
    bloom: str
    bloom_confianza: float
    enunciado: float            # escala 1–5
    enunciado_confianza: float
    respuestas: Optional[float] = None
    respuestas_confianza: Optional[float] = None
    modelo: str = MODELO

    @classmethod
    def desde_respuesta(cls, datos: dict) -> "Clasificacion":
        r = datos["answers"]
        resp = r.get("respuestas")
        return cls(
            bloom=r["bloom"]["choice"],
            bloom_confianza=round(r["bloom"].get("confidence", 0.0), 2),
            enunciado=round(r["enunciado"]["score"] + 1, 1),
            enunciado_confianza=round(r["enunciado"].get("confidence", 0.0), 2),
            respuestas=round(resp["score"] + 1, 1) if resp else None,
            respuestas_confianza=round(resp.get("confidence", 0.0), 2) if resp else None,
            modelo=datos.get("model", MODELO),
        )

    def comentario(self, tags: bool = False) -> str:
        partes = [f"[bloom:{CODIGO_BLOOM.get(self.bloom, 'B?')}-{self.bloom}]",
                  f"[dificultad-enunciado:{self.enunciado:g}/5]"]
        confianzas = [self.bloom_confianza, self.enunciado_confianza]
        if self.respuestas is not None:
            partes.append(f"[dificultad-respuestas:{self.respuestas:g}/5]")
            confianzas.append(self.respuestas_confianza or 0.0)
        partes.append(f"{MARCA}{self.modelo} confianza={','.join(f'{c:g}' for c in confianzas)}]")
        if tags:
            partes += [f"[tag:{t}]" for t in self.tags()]
        return " ".join(partes)

    def tags(self) -> List[str]:
        tags = [f"bloom:{self.bloom}", f"dificultad-enunciado:{round(self.enunciado)}"]
        if self.respuestas is not None:
            tags.append(f"dificultad-respuestas:{round(self.respuestas)}")
        return tags


def _es_tag_de_clasificacion(texto: str) -> bool:
    return texto.startswith(("bloom:", "dificultad-enunciado:", "dificultad-respuestas:"))


MANUAL = "manual"
UMBRAL_REVISION = 0.6


def es_manual(unidad: Unidad) -> bool:
    """Si la clasificación vigente la corrigió una persona (no se pisa al reclasificar)."""
    return (getattr(unidad.pregunta, "metadata", None) or {}).get("clasificador") == MANUAL


def confianza_minima(unidad: Unidad) -> Optional[float]:
    confianzas = (getattr(unidad.pregunta, "metadata", None) or {}).get("confianza") or []
    return min(confianzas) if confianzas else None


def para_revisar(unidades: List[Unidad], umbral: float = UMBRAL_REVISION, todas: bool = False) -> List[Unidad]:
    """Preguntas clasificadas por el modelo con alguna confianza menor que `umbral` (o todas
    las clasificadas, con `todas`), de la menos a la más confiable. Las ya corregidas a mano
    no se vuelven a pedir."""
    clasificadas = [u for u in unidades if u.pregunta is not None
                    and (getattr(u.pregunta, "metadata", None) or {}).get("bloom") and not es_manual(u)]
    if not todas:
        clasificadas = [u for u in clasificadas if (confianza_minima(u) or 0.0) < umbral]
    return sorted(clasificadas, key=lambda u: (confianza_minima(u) is None, confianza_minima(u) or 0.0))


def corregida(unidad: Unidad, bloom: str, enunciado: Optional[float] = None,
              respuestas: Optional[float] = None) -> Clasificacion:
    """La clasificación corregida a mano: el nivel elegido y, si no se cambian, las
    dificultades que ya tenía; confianza 1 y clasificador `manual`."""
    if bloom not in BLOOM:
        raise ValueError(f"Nivel de Bloom desconocido: {bloom!r}")
    meta = getattr(unidad.pregunta, "metadata", None) or {}
    enunciado = enunciado if enunciado is not None else meta.get("dificultad_enunciado", 3.0)
    respuestas = respuestas if respuestas is not None else meta.get("dificultad_respuestas")
    return Clasificacion(bloom=bloom, bloom_confianza=1.0, enunciado=float(enunciado), enunciado_confianza=1.0,
                         respuestas=None if respuestas is None else float(respuestas),
                         respuestas_confianza=None if respuestas is None else 1.0, modelo=MANUAL)


def guardar_correcciones(archivos: List[Archivo], correcciones: Dict[int, Clasificacion], tags: bool = False,
                         referencias: Optional[Path] = None, unidades: Optional[List[Unidad]] = None) -> Dict:
    """Escribe las clasificaciones corregidas (por id de la unidad) en sus archivos y, con
    `referencias`, las agrega al CSV de calibración. Devuelve los archivos escritos y las filas."""
    escritos = []
    for archivo in archivos:
        propias = {i: c for i, c in correcciones.items()
                   if any(isinstance(s, Unidad) and id(s) == i for s in archivo.segmentos)}
        if propias:
            archivo.ruta.write_text(escribir(archivo, propias, tags), encoding="utf-8")
            escritos.append(archivo.ruta)
    filas = 0
    if referencias is not None:
        por_id = {id(u): u for u in (unidades or [s for a in archivos for s in a.segmentos if isinstance(s, Unidad)])}
        for i, c in correcciones.items():
            u = por_id.get(i)
            if u is None:
                continue
            agregar_referencia(referencias, u.archivo, (u.pregunta.title or "").strip(), c.bloom, c.enunciado, c.respuestas)
            filas += 1
    return {"archivos": escritos, "referencias": filas}


def ya_clasificada(unidad: Unidad, comentario_previo: Optional[ET.Element]) -> bool:
    if unidad.formato == "gift":
        return any(MARCA in linea for linea in unidad.prefijo)
    return comentario_previo is not None and MARCA in (comentario_previo.text or "")


def _bloque_gift(unidad: Unidad, c: Clasificacion, tags: bool) -> str:
    prefijo = [linea for linea in unidad.prefijo if MARCA not in linea]
    # El título y el resto de la pregunta quedan como estaban.
    cuerpo = unidad.original.splitlines()[len(unidad.prefijo):]
    return "\n".join(prefijo + [f"// {c.comentario(tags)}"] + cuerpo)


def _pregunta_xml(elemento: ET.Element, c: Clasificacion, tags: bool) -> ET.Element:
    if not tags:
        return elemento
    nodo = elemento.find("tags")
    if nodo is None:
        nodo = ET.SubElement(elemento, "tags")
    for tag in list(nodo.findall("tag")):
        if _es_tag_de_clasificacion((tag.findtext("text") or "").strip()):
            nodo.remove(tag)
    for texto in c.tags():
        ET.SubElement(ET.SubElement(nodo, "tag"), "text").text = texto
    return elemento


def escribir(archivo: Archivo, resultados: Dict[int, Clasificacion], tags: bool) -> str:
    if archivo.formato == "gift":
        bloques = []
        for s in archivo.segmentos:
            if isinstance(s, Unidad) and id(s) in resultados:
                bloques.append(_bloque_gift(s, resultados[id(s)], tags))
            else:
                bloques.append(s.original if isinstance(s, Unidad) else s)
        return "\n\n".join(bloques) + "\n"

    quiz = ET.Element("quiz")
    segmentos = archivo.segmentos
    for i, s in enumerate(segmentos):
        siguiente = segmentos[i + 1] if i + 1 < len(segmentos) else None
        es_comentario = getattr(s, "tag", None) is ET.Comment
        if es_comentario and isinstance(siguiente, Unidad) and id(siguiente) in resultados and MARCA in (s.text or ""):
            continue  # la clasificación anterior se reemplaza
        if isinstance(s, Unidad):
            if id(s) in resultados:
                c = resultados[id(s)]
                quiz.append(ET.Comment(f" {c.comentario()} "))
                quiz.append(_pregunta_xml(s.nodo, c, tags))
            else:
                quiz.append(s.nodo)
        else:
            quiz.append(s)
    return serializar_quiz(quiz)


# ---------------------------------------------------------------------------
# Proceso
# ---------------------------------------------------------------------------

def _pendientes(archivos: List[Archivo], reclasificar: bool) -> List[Unidad]:
    pendientes = []
    for archivo in archivos:
        anterior = None
        for s in archivo.segmentos:
            if isinstance(s, Unidad) and s.pregunta is not None:
                # Las correcciones manuales se respetan también al reclasificar.
                if (reclasificar and not es_manual(s)) or not ya_clasificada(s, anterior):
                    pendientes.append(s)
            anterior = s if getattr(s, "tag", None) is ET.Comment else None
    return pendientes


def resumen(resultados: List[Clasificacion]) -> Dict:
    bloom = Counter(c.bloom for c in resultados)
    con_respuestas = [c.respuestas for c in resultados if c.respuestas is not None]
    return {
        "clasificadas": len(resultados),
        "bloom": {nivel: bloom.get(nivel, 0) for nivel in BLOOM},
        "dificultad_enunciado_media": round(mean(c.enunciado for c in resultados), 2) if resultados else None,
        "dificultad_respuestas_media": round(mean(con_respuestas), 2) if con_respuestas else None,
        "baja_confianza": sum(1 for c in resultados if min(c.bloom_confianza, c.enunciado_confianza) < 0.5),
    }


def run_clasificacion(file_paths: List[Path], output_dir: Optional[Path], in_place: bool = False,
                      suffix: Optional[str] = None, contexto: str = CONTEXTO, concurrencia: int = 4,
                      reclasificar: bool = False, tags: bool = False, dry_run: bool = False,
                      cliente: Optional[ClienteJev] = None) -> Optional[Dict]:
    print(f"🔍 Escaneando {len(file_paths)} archivos...")
    archivos = leer_archivos(file_paths)
    total = len(unidades_de(archivos))
    pendientes = _pendientes(archivos, reclasificar)
    print(f"🏷️  {len(pendientes)} preguntas para clasificar ({total - len(pendientes)} ya clasificadas o sin tipo evaluable).")
    if not pendientes:
        return None
    if dry_run:
        q = pendientes[0].pregunta
        entrada = sum(len(json.dumps({"state": estado(u.pregunta, contexto), "questions": preguntas_jev(u.pregunta)},
                                     ensure_ascii=False)) for u in pendientes) // 4
        print(f"💰 ≈{entrada:,} tokens de entrada y ≈{25 * len(pendientes):,} de salida (aprox.)".replace(",", "."))
        print(f"🧪 Simulación: {len(pendientes)} solicitudes a {MODELO}; no se llama a la API. Primera solicitud:\n")
        print(json.dumps({"state": estado(q, contexto), "questions": preguntas_jev(q)}, ensure_ascii=False, indent=2))
        return None

    cliente = cliente or ClienteJev()
    resultados: Dict[int, Clasificacion] = {}
    uso = {"input_tokens": 0, "output_tokens": 0}
    errores = 0

    def clasificar(unidad: Unidad):
        datos = cliente.consultar(estado(unidad.pregunta, contexto), preguntas_jev(unidad.pregunta))
        return unidad, datos

    print(f"🚀 Clasificando con {MODELO} ({concurrencia} solicitudes en paralelo)...")
    from voight.core.progreso import barra

    with ThreadPoolExecutor(max_workers=max(1, concurrencia)) as ejecutor, \
            barra(len(pendientes), "Clasificando") as avance:
        futuros = [ejecutor.submit(clasificar, u) for u in pendientes]
        for n, futuro in enumerate(futuros, 1):
            avance()
            try:
                unidad, datos = futuro.result()
                resultados[id(unidad)] = Clasificacion.desde_respuesta(datos)
                for clave in uso:
                    uso[clave] += (datos.get("usage") or {}).get(clave, 0)
            except Exception as e:  # noqa: BLE001 - una falla no detiene el resto
                errores += 1
                print(f"  ⚠️ {pendientes[n - 1].archivo.name}: {e}")
            if not avance.activa and (n % 50 == 0 or n == len(futuros)):
                print(f"  {n}/{len(futuros)}")

    print("💾 Guardando resultados...")
    base = Path(os.path.commonpath([str(a.ruta.parent.resolve()) for a in archivos]))
    for archivo in archivos:
        if not any(id(s) in resultados for s in archivo.segmentos if isinstance(s, Unidad)):
            continue
        ruta = archivo.ruta
        if in_place:
            destino = ruta.parent / f"{ruta.stem}{suffix}{ruta.suffix}" if suffix else ruta
        else:
            if output_dir is None:
                raise ValueError("Sin --in-place hace falta un directorio de salida.")
            destino = output_dir / ruta.parent.resolve().relative_to(base) / f"{ruta.stem}_classify{ruta.suffix}"
            destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(escribir(archivo, resultados, tags), encoding="utf-8")

    datos = resumen(list(resultados.values()))
    datos.update({"errores": errores, "uso": uso})
    print("\n📊 Bloom: " + ", ".join(f"{CODIGO_BLOOM[k]} {k} {v}" for k, v in datos["bloom"].items()))
    print(f"   Dificultad media (1–5): enunciado {datos['dificultad_enunciado_media']}, "
          f"respuestas {datos['dificultad_respuestas_media']}; baja confianza: {datos['baja_confianza']}")
    print(f"   Tokens: {uso['input_tokens']} de entrada, {uso['output_tokens']} de salida"
          + (f"; {errores} preguntas con error" if errores else ""))
    return datos


# ---------------------------------------------------------------------------
# Calibración: comparar con una clasificación de referencia (docente)
# ---------------------------------------------------------------------------

COLUMNAS_REFERENCIA = ("archivo", "titulo", "bloom", "dificultad_enunciado", "dificultad_respuestas")


def leer_referencias(ruta: Path) -> List[dict]:
    """Filas de un CSV archivo,titulo,bloom[,dificultad_enunciado,dificultad_respuestas]."""
    import csv

    with Path(ruta).open(encoding="utf-8", newline="") as f:
        filas = []
        for fila in csv.DictReader(f):
            bloom = (fila.get("bloom") or "").strip().lower()
            bloom = re.sub(r"^b\d-", "", bloom)
            if bloom not in BLOOM:
                continue
            filas.append({**fila, "bloom": bloom})
        return filas


def agregar_referencia(ruta: Path, archivo: Path, titulo: str, bloom: str,
                       dificultad_enunciado=None, dificultad_respuestas=None) -> None:
    """Agrega (o reemplaza) la clasificación de referencia de una pregunta en el CSV."""
    import csv

    ruta = Path(ruta)
    filas = []
    if ruta.exists():
        with ruta.open(encoding="utf-8", newline="") as f:
            filas = [r for r in csv.DictReader(f)
                     if not (Path(r.get("archivo", "")).resolve() == Path(archivo).resolve() and r.get("titulo", "") == titulo)]
    filas.append({"archivo": str(Path(archivo).resolve()), "titulo": titulo, "bloom": bloom,
                  "dificultad_enunciado": "" if dificultad_enunciado is None else dificultad_enunciado,
                  "dificultad_respuestas": "" if dificultad_respuestas is None else dificultad_respuestas})
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS_REFERENCIA)
        escritor.writeheader()
        escritor.writerows({c: r.get(c, "") for c in COLUMNAS_REFERENCIA} for r in filas)


def _buscar(unidades: List[Unidad], referencia: dict) -> Optional[Unidad]:
    ruta = Path(referencia.get("archivo", "")).resolve()
    candidatas = [u for u in unidades if u.archivo.resolve() == ruta]
    titulo = (referencia.get("titulo") or "").strip()
    if titulo:
        candidatas = [u for u in candidatas if (u.pregunta.title or "").strip() == titulo] or candidatas[:0]
    return candidatas[0] if len(candidatas) == 1 else None


def calibrar(referencias: List[dict], cliente: ClienteJev, contexto: str = CONTEXTO, concurrencia: int = 4) -> Dict:
    """Clasifica con Jev las preguntas de referencia (sin escribir nada) y mide la concordancia."""
    rutas = sorted({Path(r["archivo"]) for r in referencias if Path(r.get("archivo", "")).exists()})
    unidades = [u for u in unidades_de(leer_archivos(rutas)) if u.pregunta is not None]
    pares = [(r, u) for r in referencias for u in [_buscar(unidades, r)] if u is not None]

    from voight.core.progreso import barra

    with barra(len(pares), "Calibrando") as avance:
        def clasificar(par):
            r, u = par
            datos = cliente.consultar(estado(u.pregunta, contexto), preguntas_jev(u.pregunta))
            avance()
            return r, Clasificacion.desde_respuesta(datos)

        with ThreadPoolExecutor(max_workers=max(1, concurrencia)) as ejecutor:
            resultados = list(ejecutor.map(clasificar, pares))
    return medir_concordancia(resultados, sin_encontrar=len(referencias) - len(pares))


def medir_concordancia(resultados: List[tuple], sin_encontrar: int = 0) -> Dict:
    """Exacta, ±1 nivel, kappa de Cohen, matriz de confusión y error medio de dificultad."""
    niveles = list(BLOOM)
    n = len(resultados)
    matriz = {a: {b: 0 for b in niveles} for a in niveles}
    exactas = adyacentes = 0
    errores: Dict[str, List[float]] = {"enunciado": [], "respuestas": []}
    for ref, c in resultados:
        matriz[ref["bloom"]][c.bloom] += 1
        distancia = abs(niveles.index(ref["bloom"]) - niveles.index(c.bloom))
        exactas += distancia == 0
        adyacentes += distancia <= 1
        for campo, valor in (("enunciado", c.enunciado), ("respuestas", c.respuestas)):
            esperado = (ref.get(f"dificultad_{campo}") or "").strip()
            if esperado and valor is not None:
                errores[campo].append(abs(float(esperado) - valor))
    acuerdo = exactas / n if n else 0.0
    azar = sum(sum(matriz[a].values()) * sum(matriz[b][a] for b in niveles) for a in niveles) / (n * n) if n else 0.0
    return {
        "preguntas": n,
        "sin_encontrar": sin_encontrar,
        "exacta": round(acuerdo, 3),
        "adyacente": round(adyacentes / n, 3) if n else 0.0,
        "kappa": round((acuerdo - azar) / (1 - azar), 3) if n and azar < 1 else None,
        "matriz": matriz,
        "error_dificultad_enunciado": round(mean(errores["enunciado"]), 2) if errores["enunciado"] else None,
        "error_dificultad_respuestas": round(mean(errores["respuestas"]), 2) if errores["respuestas"] else None,
    }


def describir_calibracion(datos: Dict) -> str:
    lineas = [f"Calibración de {MODELO} contra la referencia: {datos['preguntas']} preguntas"
              + (f" ({datos['sin_encontrar']} filas sin pregunta que coincida)" if datos["sin_encontrar"] else ""),
              f"  Bloom exacto: {datos['exacta']:.0%} · a ±1 nivel: {datos['adyacente']:.0%}"
              + (f" · kappa de Cohen: {datos['kappa']:.2f}" if datos["kappa"] is not None else "")]
    if datos["error_dificultad_enunciado"] is not None:
        lineas.append(f"  Error medio de dificultad (1–5): enunciado {datos['error_dificultad_enunciado']:g}"
                      + (f", respuestas {datos['error_dificultad_respuestas']:g}" if datos["error_dificultad_respuestas"] is not None else ""))
    codigos = [CODIGO_BLOOM[n] for n in BLOOM]
    lineas.append("  Matriz (filas: referencia, columnas: Jev): " + " ".join(f"{c:>3}" for c in codigos))
    for nivel in BLOOM:
        fila = datos["matriz"][nivel]
        if any(fila.values()):
            lineas.append(f"    {CODIGO_BLOOM[nivel]} {nivel:<10} " + " ".join(f"{fila[b] or '·':>3}" for b in BLOOM))
    return "\n".join(lineas)
