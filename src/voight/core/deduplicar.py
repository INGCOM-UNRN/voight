"""Eliminación de preguntas duplicadas (GIFT y Moodle XML) según un umbral de similitud.

La similitud es la misma de `analyze similar` (TF-IDF + Jaccard sobre título,
enunciado y respuestas). Como se elimina, el criterio es conservador: además del
umbral, dos preguntas tienen que ser del mismo tipo y tener la misma respuesta
correcta (en los bancos hay pares casi idénticos que sólo cambian cuál opción es la
correcta, como recorrido inorden/posorden), y sus enunciados por sí solos también
tienen que superar el umbral (las opciones idénticas dominan la similitud de, por
ejemplo, "complejidad de la inserción en una cola" y "… de la extracción …"). Para no
encadenar parecidos (A≈B y B≈C no implica A≈C), se recorren las preguntas de la más
completa a la menos completa: cada una se conserva salvo que sea similar, por encima
del umbral, a otra ya conservada; en ese caso es su duplicado.

Al eliminar, en GIFT se quita el bloque de la pregunta con sus comentarios (las
líneas `$CATEGORY` se conservan) y en XML el `<question>` con los comentarios que lo
preceden. Un archivo que queda sin preguntas se borra.
"""
from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from voight.core.lector import Archivo, Unidad
from voight.core.codigo import transformar_codigo
from voight.core.gift_model import Question
from voight.core.tree import serializar_quiz
from voight.core.validator import AnalizadorBanco

CRITERIOS = ("completa", "primera")


@dataclass
class Grupo:
    conservada: Unidad
    duplicadas: List[Tuple[Unidad, float]] = field(default_factory=list)


def _texto_completo(q: Question) -> str:
    partes = [q.title or "", q.stem.text if q.stem else ""]
    partes += [c.text.text for c in q.choices if c.text]
    for par in q.match_pairs:
        partes += [par.subquestion.text, par.subanswer or ""]
    return " ".join(partes)


def _normalizar(texto: str) -> str:
    texto = re.sub(r"<[^>]+>", " ", texto or "").lower()
    return " ".join(re.findall(r"[0-9a-záéíóúñü]+", transformar_codigo(texto, fullwidth=False)[0]))


def clave(q: Question):
    """La respuesta correcta, normalizada: dos duplicados tienen que compartirla."""
    if q.type == "TF":
        return q.is_true
    if q.type == "Matching":
        return frozenset((_normalizar(p.subquestion.text), _normalizar(p.subanswer)) for p in q.match_pairs)
    return frozenset(_normalizar(c.text.text) for c in q.choices
                     if c.text and (c.is_correct or (c.weight or 0) > 0))


def completitud(q: Question) -> tuple:
    """Cuanto más alta, más conviene conservar la pregunta: feedback, título, opciones."""
    retros = [c.feedback for c in q.choices] + [q.true_feedback, q.false_feedback]
    return (
        bool(q.global_feedback and q.global_feedback.text),
        sum(1 for r in retros if r is not None and r.text),
        bool(q.title),
        len(q.choices) + len(q.match_pairs),
    )


def agrupar(unidades: List[Unidad], umbral: float, criterio: str = "completa") -> List[Grupo]:
    """Grupos de duplicados: una pregunta conservada y las que se eliminan por ser similares a ella."""
    analizador = AnalizadorBanco(similarity_threshold=umbral)
    analizador.all_questions = [{"full_text": _texto_completo(u.pregunta)} for u in unidades]
    analizador.find_duplicates()

    enunciados = [frozenset(analizador._tokenize(analizador._clean_text(u.pregunta.stem.text if u.pregunta.stem else "")))
                  for u in unidades]
    vecinos: Dict[int, Dict[int, float]] = defaultdict(dict)
    for d in analizador.duplicates:
        i, j = d["index1"], d["index2"]
        a, b = unidades[i].pregunta, unidades[j].pregunta
        if (a.type == b.type and clave(a) == clave(b)
                and analizador._jaccard_similarity(enunciados[i], enunciados[j]) >= umbral):
            vecinos[i][j] = vecinos[j][i] = d["similarity"]

    orden = list(range(len(unidades)))  # orden de los archivos: desempata
    if criterio == "completa":
        orden.sort(key=lambda i: completitud(unidades[i].pregunta), reverse=True)

    conservadas: List[int] = []
    grupos: Dict[int, Grupo] = {}
    for i in orden:
        if i not in vecinos:
            continue
        candidatas = [(vecinos[i][k], k) for k in conservadas if k in vecinos[i]]
        if candidatas:
            similitud, k = max(candidatas)
            grupos.setdefault(k, Grupo(unidades[k])).duplicadas.append((unidades[i], similitud))
        else:
            conservadas.append(i)
    return [grupos[k] for k in sorted(grupos)]


def _queda_vacio(segmentos: list) -> bool:
    """True si no queda ninguna pregunta (sólo categorías y comentarios)."""
    for s in segmentos:
        if isinstance(s, Unidad):
            return False
        if isinstance(s, str):
            if any(linea.strip() and not linea.strip().startswith(("//", "$CATEGORY"))
                   for linea in s.splitlines()):
                return False
        elif s.tag is not ET.Comment and not (s.tag == "question" and s.get("type") == "category"):
            return False
    return True


def sin_eliminadas(archivo: Archivo, eliminadas: set) -> list:
    segmentos = []
    for s in archivo.segmentos:
        if isinstance(s, Unidad) and id(s) in eliminadas:
            if archivo.formato == "gift":
                categorias = [linea for linea in s.prefijo if linea.strip().startswith("$CATEGORY")]
                if categorias:
                    segmentos.append("\n".join(categorias))
            else:
                while segmentos and getattr(segmentos[-1], "tag", None) is ET.Comment:
                    segmentos.pop()  # los comentarios de la pregunta (`<!-- question: … -->`)
            continue
        segmentos.append(s)
    return segmentos


def escribir(archivo: Archivo, segmentos: list) -> str:
    if archivo.formato == "gift":
        return "\n\n".join(s.original if isinstance(s, Unidad) else s for s in segmentos) + "\n"
    quiz = ET.Element("quiz")
    for s in segmentos:
        quiz.append(s.nodo if isinstance(s, Unidad) else s)
    return serializar_quiz(quiz)


def aplicar(archivos: List[Archivo], grupos: List[Grupo], respaldo: Optional[Path] = None) -> Dict[str, Any]:
    """Elimina las duplicadas de los archivos. Devuelve los archivos modificados y borrados.

    Con `respaldo` (un directorio de respaldos), antes de tocar nada copia el contenido
    original de cada archivo afectado a un subdirectorio nuevo, para `restaurar` después;
    el resultado lleva entonces `respaldo` con la ruta de ese subdirectorio.
    """
    eliminadas = {id(u) for g in grupos for u, _ in g.duplicadas}
    afectados = [a for a in archivos if any(isinstance(s, Unidad) and id(s) in eliminadas for s in a.segmentos)]
    nuevos = {}
    for archivo in afectados:
        segmentos = sin_eliminadas(archivo, eliminadas)
        nuevos[id(archivo)] = None if _queda_vacio(segmentos) else escribir(archivo, segmentos)
    destino = _respaldar(afectados, nuevos, respaldo) if respaldo is not None and afectados else None

    modificados, borrados = [], []
    for archivo in afectados:
        contenido = nuevos[id(archivo)]
        if contenido is None:
            archivo.ruta.unlink()
            borrados.append(archivo.ruta)
        else:
            archivo.ruta.write_text(contenido, encoding="utf-8")
            modificados.append(archivo.ruta)
    return {"modificados": modificados, "borrados": borrados, **({"respaldo": destino} if destino else {})}


MANIFIESTO = "manifiesto.json"


def _huella(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _respaldar(afectados: List[Archivo], nuevos: dict, raiz: Path) -> Path:
    """Copia los originales a raiz/<fecha>/ con un manifiesto: ruta absoluta, copia,
    acción y la huella de lo que dedup dejó (para no pisar cambios posteriores)."""
    fecha = datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = raiz / fecha
    n = 1
    while destino.exists():
        n += 1
        destino = raiz / f"{fecha}-{n}"
    (destino / "archivos").mkdir(parents=True)
    entradas = []
    for i, archivo in enumerate(afectados, 1):
        original = archivo.ruta.read_bytes()
        copia = Path("archivos") / f"{i:04d}-{archivo.ruta.name}"
        (destino / copia).write_bytes(original)
        contenido = nuevos[id(archivo)]
        entradas.append({
            "ruta": str(archivo.ruta.resolve()),
            "copia": copia.as_posix(),
            "accion": "borrado" if contenido is None else "modificado",
            "huella_original": _huella(original),
            "huella_despues": None if contenido is None else _huella(contenido.encode("utf-8")),
        })
    manifiesto = {"fecha": datetime.now().isoformat(timespec="seconds"), "archivos": entradas}
    (destino / MANIFIESTO).write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino


def respaldos(raiz: Path) -> List[Path]:
    """Los respaldos de `raiz`, del más viejo al más nuevo."""
    if not raiz.is_dir():
        return []
    return sorted(d for d in raiz.iterdir() if (d / MANIFIESTO).is_file())


def restaurar(respaldo: Path, forzar: bool = False) -> Dict[str, List[str]]:
    """Devuelve los archivos de un respaldo a su contenido original.

    No pisa un archivo que cambió después de dedup (salvo `forzar`): lo informa en
    `cambiados`. Los que ya tienen el contenido original van a `sin_cambios`.
    """
    manifiesto = json.loads((respaldo / MANIFIESTO).read_text(encoding="utf-8"))
    resultado: Dict[str, List[str]] = {"restaurados": [], "sin_cambios": [], "cambiados": []}
    for entrada in manifiesto["archivos"]:
        ruta = Path(entrada["ruta"])
        actual = ruta.read_bytes() if ruta.exists() else None
        if actual is not None and _huella(actual) == entrada["huella_original"]:
            resultado["sin_cambios"].append(str(ruta))
            continue
        esperado = entrada["huella_despues"]
        tocado = (actual is not None) if esperado is None else (actual is None or _huella(actual) != esperado)
        if tocado and not forzar:
            resultado["cambiados"].append(str(ruta))
            continue
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes((respaldo / entrada["copia"]).read_bytes())
        resultado["restaurados"].append(str(ruta))
    return resultado


def plan(archivos: List[Archivo], grupos: List[Grupo]) -> Dict[str, List[Path]]:
    """Qué archivos se modificarían y cuáles se borrarían, sin tocarlos."""
    eliminadas = {id(u) for g in grupos for u, _ in g.duplicadas}
    modificar: List[Path] = []
    borrar: List[Path] = []
    for archivo in archivos:
        if any(isinstance(s, Unidad) and id(s) in eliminadas for s in archivo.segmentos):
            (borrar if _queda_vacio(sin_eliminadas(archivo, eliminadas)) else modificar).append(archivo.ruta)
    return {"modificados": modificar, "borrados": borrar}


def a_json(grupos: List[Grupo]) -> List[dict]:
    def ref(u: Unidad) -> dict:
        return {"archivo": str(u.archivo), "titulo": u.pregunta.title, "tipo": u.pregunta.type}

    return [
        {"conserva": ref(g.conservada),
         "elimina": [{**ref(u), "similitud": round(s, 4)} for u, s in g.duplicadas]}
        for g in grupos
    ]



def registrar(grupos: List[Grupo], cambios: Dict[str, List[Path]], log: Path, umbral: float) -> int:
    """Agrega al log una línea por pregunta eliminada, con las rutas completas (las categorías
    se infieren de ellas). Formato TSV: fecha, acción, archivo eliminado, archivo conservado,
    similitud, umbral, tipo y título. Devuelve cuántas líneas escribió."""
    borrados = {r.resolve() for r in cambios["borrados"]}
    fecha = datetime.now().isoformat(timespec="seconds")
    lineas = []
    for g in grupos:
        for u, similitud in g.duplicadas:
            ruta = u.archivo.resolve()
            accion = "archivo-borrado" if ruta in borrados else "pregunta-quitada"
            titulo = (u.pregunta.title or "").replace("\t", " ").replace("\n", " ")
            lineas.append("\t".join([fecha, accion, str(ruta), str(g.conservada.archivo.resolve()),
                                     f"{similitud:.4f}", f"{umbral:g}", u.pregunta.type, titulo]))
    if lineas:
        nuevo = not log.exists()
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            if nuevo:
                f.write("fecha\taccion\teliminado\tconservado\tsimilitud\tumbral\ttipo\ttitulo\n")
            f.write("\n".join(lineas) + "\n")
    return len(lineas)


# ---------------------------------------------------------------------------
# Revisión manual (la usa la TUI; no depende de la interfaz)
# ---------------------------------------------------------------------------

class Revision:
    """Decisiones sobre los grupos: cuál se conserva y cuáles se eliminan.

    Empieza con la propuesta automática (se conserva la más completa y se eliminan las
    demás). En cada grupo siempre queda al menos una pregunta: la principal no se puede
    eliminar; para eliminarla hay que elegir otra como principal.
    """

    def __init__(self, grupos: List[Grupo]):
        self.miembros: List[List[Unidad]] = [[g.conservada] + [u for u, _ in g.duplicadas] for g in grupos]
        self.similitud: Dict[int, float] = {id(g.conservada): 1.0 for g in grupos}
        for g in grupos:
            self.similitud.update({id(u): s for u, s in g.duplicadas})
        self.principal: List[Unidad] = [g.conservada for g in grupos]
        self.eliminar: Dict[int, bool] = {id(u): True for g in grupos for u, _ in g.duplicadas}

    def __len__(self) -> int:
        return len(self.miembros)

    def se_elimina(self, u: Unidad) -> bool:
        return self.eliminar.get(id(u), False)

    def alternar(self, grupo: int, u: Unidad) -> None:
        if u is not self.principal[grupo]:
            self.eliminar[id(u)] = not self.se_elimina(u)

    def hacer_principal(self, grupo: int, u: Unidad) -> None:
        """Conservar `u` en lugar de la principal actual, que pasa a eliminarse."""
        anterior = self.principal[grupo]
        if u is anterior:
            return
        self.principal[grupo] = u
        self.eliminar[id(u)] = False
        self.eliminar[id(anterior)] = True

    def conservar_todas(self, grupo: int) -> None:
        for u in self.miembros[grupo]:
            self.eliminar[id(u)] = False

    def a_eliminar(self, grupo: Optional[int] = None) -> int:
        grupos = range(len(self)) if grupo is None else [grupo]
        return sum(1 for g in grupos for u in self.miembros[g] if self.se_elimina(u))

    def grupos(self) -> List[Grupo]:
        """Los grupos tal como quedaron decididos, para `aplicar` y `registrar`."""
        resultado = []
        for g, miembros in enumerate(self.miembros):
            eliminadas = [(u, self.similitud[id(u)]) for u in miembros if self.se_elimina(u)]
            if eliminadas:
                resultado.append(Grupo(self.principal[g], eliminadas))
        return resultado


# ---------------------------------------------------------------------------
# Confirmación con Jev (TypeSafe): el juicio que la similitud léxica no hace
# ---------------------------------------------------------------------------

PREGUNTA_MISMA = {
    "type": "noul",
    "instructions": "¿`pregunta_a` y `pregunta_b` evalúan exactamente lo mismo, de modo que en un banco de "
                    "preguntas una de las dos sobra? Dos preguntas casi iguales que piden cosas distintas "
                    "(otra operación, otro concepto, otra respuesta correcta) NO son la misma.",
    "criteria": {
        "true": "Piden lo mismo con otras palabras o con cambios menores: tienen la misma respuesta y evalúan "
                "el mismo conocimiento.",
        "false": "Difieren en lo que preguntan (una palabra clave, la operación, el concepto o la respuesta "
                 "correcta), aunque compartan casi todo el texto o las opciones.",
    },
}


def confirmar_con_jev(grupos: List[Grupo], cliente, minimo: float = 0.5, concurrencia: int = 4,
                      exactas: float = 0.999) -> Tuple[List[Grupo], List[dict]]:
    """Deja en cada grupo sólo los duplicados que Jev confirma (probabilidad ≥ `minimo`).

    Los pares prácticamente idénticos (similitud ≥ `exactas`) no se consultan. Devuelve los
    grupos filtrados y los pares descartados con su probabilidad.
    """
    from concurrent.futures import ThreadPoolExecutor

    from voight.core.clasificacion import estado

    pares = [(g, u, s) for g in grupos for u, s in g.duplicadas if s < exactas]

    def consultar(par):
        g, u, _ = par
        datos = cliente.consultar(
            {"pregunta_a": estado(g.conservada.pregunta), "pregunta_b": estado(u.pregunta)},
            {"misma": PREGUNTA_MISMA},
        )
        return datos["answers"]["misma"]["noul"]

    with ThreadPoolExecutor(max_workers=max(1, concurrencia)) as ejecutor:
        probabilidades = list(ejecutor.map(consultar, pares))

    rechazadas = {id(u): p for (_, u, _), p in zip(pares, probabilidades) if p < minimo}
    descartados = [
        {"conserva": str(g.conservada.archivo), "descartado": str(u.archivo), "similitud": round(s, 4),
         "probabilidad": round(rechazadas[id(u)], 3)}
        for g, u, s in pares if id(u) in rechazadas
    ]
    filtrados = []
    for g in grupos:
        duplicadas = [(u, s) for u, s in g.duplicadas if id(u) not in rechazadas]
        if duplicadas:
            filtrados.append(Grupo(g.conservada, duplicadas))
    return filtrados, descartados
