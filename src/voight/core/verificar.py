"""Verificación de preguntas de código: compilar y ejecutar el snippet del enunciado.

Para las preguntas del tipo "¿qué imprime este código?", se toma el primer bloque de
código del enunciado (restaurado a ASCII), se completa lo que falta para compilarlo
(`main`, includes o la clase en Java), se compila con `gcc`/`javac`, se ejecuta con
límite de tiempo y se compara la salida con las opciones:

- `coincide`: la salida es la respuesta correcta.
- `coincide_distractor`: la salida es un distractor — la clave está mal.
- `revisar`: la salida no aparece literalmente en ninguna opción (opciones en prosa,
  preguntas inversas "¿qué código imprime X?"); no es un error, hay que mirarla.
- `no_compila` / `error_ejecucion` / `tiempo`: el código no llega a imprimir; si la
  respuesta correcta dice justamente eso ("error de compilación", "comportamiento
  indefinido"), cuenta como `coincide`.

Con `sanitizar`, el C se compila con -fsanitize=address,undefined: un hallazgo del
sanitizador marca la pregunta como `comportamiento_indefinido` si su clave no lo dice.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from voight.core.codigo import transformar_codigo, transformar_fragmento
from voight.core.gift_model import Question

_FENCE = re.compile(r"```([^\n`]*)\n(.*?)```", re.DOTALL)
_PIDE_SALIDA = re.compile(r"imprim|salida|muestra|output|print|resultado|valor final|se ve en (la )?consola", re.I)
_COMPILACION = re.compile(r"no compila|error de compilaci|compile error|no se puede compilar", re.I)
_INDEFINIDO = re.compile(r"indefinid|no definid|indeterminad|undefined|basura|impredecible|depende del compilador", re.I)
_INFINITO = re.compile(r"infinit|nunca termina|no termina|se cuelga|indefinidamente", re.I)
_SOBRE_COMPILAR = re.compile(r"compil|error|v[aá]lid|admite|permite|sintaxis|no se puede", re.I)
_ENTRADA = re.compile(r"\bfopen\b|\bscanf\b|\bgetchar\b|\bfgets\s*\([^)]*stdin|\bScanner\b|System\.in|BufferedReader|\bargv\b|\bargs\[")
_SIN_CONTEXTO = re.compile(r"cannot find symbol|undeclared|no declarad|implicit declaration", re.I)
_COMPILA_BIEN = re.compile(r"no (produce|genera|da|hay|tiene)( un| ning[uú]n)? error(es)? de compilaci|compila (correctamente|sin errores)|no hay error", re.I)
_EJECUCION = re.compile(r"tiempo de ejecuci|segmentation|violaci[oó]n de segmento|se cuelga|excepci[oó]n|exception|crash|aborta", re.I)

INCLUDES_C = ["stdio.h", "stdlib.h", "string.h", "stdbool.h", "math.h", "limits.h", "ctype.h", "stddef.h", "stdint.h"]
TIEMPO_COMPILAR = 30
TIEMPO_EJECUTAR = 3


@dataclass
class Resultado:
    estado: str
    lenguaje: Optional[str] = None
    salida: str = ""
    detalle: str = ""
    coincide_con: Optional[str] = None
    opciones: List[str] = field(default_factory=list)


def _restaurar(texto: str) -> str:
    """A ASCII: las secciones de código del texto y, además, todo el texto como fragmento
    (un bloque ya extraído o una opción corta no tienen delimitadores)."""
    texto = transformar_codigo(texto or "", contexto="xml", fullwidth=False)[0]
    return transformar_fragmento(texto, contexto="xml", fullwidth=False)


_PREFIJO_SALIDA = re.compile(
    r"^(se\s+)?(imprim\w*|muestra\w*|mostrar\w*|la salida (es|ser[áa])|salida|output)\s*:?\s*", re.I)


def _lineas(texto: str) -> str:
    """Salida u opción con su estructura de líneas: \\n literal y ↵ como saltos, sin
    espacios al final de cada línea ni líneas en blanco al final."""
    texto = _restaurar(texto).replace("↵", "\n").replace("\\n", "\n").replace("`", "")
    texto = re.sub(r"<br\s*/?>", "\n", re.sub(r"</?p>", "\n", texto))
    texto = re.sub(r"<[^>]+>", " ", texto)
    return "\n".join(linea.rstrip() for linea in texto.strip("\n").split("\n")).strip()


def normalizar(texto: str) -> str:
    """Para comparar una opción con la salida: sin backticks ni marcas, espacios colapsados."""
    return " ".join(_lineas(texto).split()).strip().strip('"').strip()


def candidatos(opcion: str) -> List[str]:
    """Formas en que una opción puede contener la salida: entera, sin \"Imprimirá:\" y lo citado."""
    base = _lineas(opcion)
    sin_prefijo = _PREFIJO_SALIDA.sub("", base).strip().strip('"').strip()
    formas = [base, sin_prefijo, re.sub(r"\s*\([^()]*\)\s*$", "", sin_prefijo).strip()]
    formas += re.findall(r'"([^"]+)"', base) + re.findall(r"«([^»]+)»", base)
    return [f for f in dict.fromkeys(formas) if f]


def _palabras(texto: str) -> set:
    return set(re.findall(r"[0-9a-záéíóúñü]+(?:\.[0-9]+)?", texto.lower()))


def extraer_codigo(q: Question) -> Optional[tuple]:
    """(lenguaje, código) del primer bloque de código del enunciado, o None."""
    m = _FENCE.search(q.stem.text if q.stem else "")
    if not m:
        return None
    etiqueta = m.group(1).strip().lower()
    codigo = _restaurar(m.group(2)).replace("↵", "")
    if etiqueta in ("c", "h"):
        lenguaje = "c"
    elif etiqueta == "java":
        lenguaje = "java"
    elif re.search(r"System\.out|public\s+class|String\[\]|\bnew\s+\w+\(", codigo):
        lenguaje = "java"
    elif re.search(r"#include|printf\s*\(|\bmalloc\b|\bint\s+main\b|->|\bsizeof\b", codigo) or etiqueta == "":
        lenguaje = "c"
    else:
        return None
    return lenguaje, codigo


def pide_salida(q: Question) -> bool:
    return bool(_PIDE_SALIDA.search(q.stem.text if q.stem else ""))


def preparar_c(codigo: str) -> str:
    includes = "".join(f"#include <{h}>\n" for h in INCLUDES_C if f"<{h}>" not in codigo)
    if re.search(r"\bmain\s*\(", codigo):
        return includes + codigo
    return f"{includes}int main(void) {{\n{codigo}\nreturn 0;\n}}\n"


def preparar_java(codigo: str) -> tuple:
    """(nombre de la clase pública, fuente). Sin clase, el código va dentro de un main."""
    importaciones = "import java.util.*;\nimport java.io.*;\n"
    publica = re.search(r"public\s+(?:final\s+)?class\s+(\w+)", codigo)
    if publica:
        return publica.group(1), importaciones + codigo
    clase = re.search(r"\bclass\s+(\w+)", codigo)
    if clase:
        principal = re.search(r"class\s+(\w+)[^{]*\{[^}]*?static\s+void\s+main", codigo, re.S)
        return (principal or clase).group(1), importaciones + codigo
    return "Main", (f"{importaciones}public class Main {{\n"
                    f"public static void main(String[] args) throws Exception {{\n{codigo}\n}}\n}}\n")


def _ejecutar(comando: list, cwd: Path, tiempo: int) -> subprocess.CompletedProcess:
    return subprocess.run(comando, cwd=cwd, capture_output=True, text=True, timeout=tiempo, errors="replace")


def compilar_y_ejecutar(lenguaje: str, codigo: str, sanitizar: bool = False) -> tuple:
    """(estado, salida, detalle) con estado en ok / no_compila / error_ejecucion / tiempo / ub / sin_compilador."""
    with tempfile.TemporaryDirectory(prefix="voight-verify-") as tmp:
        dir_ = Path(tmp)
        if lenguaje == "c":
            if not shutil.which("gcc"):
                return "sin_compilador", "", "gcc no está instalado"
            (dir_ / "p.c").write_text(preparar_c(codigo), encoding="utf-8")
            banderas = ["-std=gnu11", "-w", "-O0", "-g"] + (["-fsanitize=address,undefined", "-fno-sanitize-recover=all"] if sanitizar else [])
            compilacion = _ejecutar(["gcc", *banderas, "p.c", "-o", "p", "-lm"], dir_, TIEMPO_COMPILAR)
            ejecutable = ["./p"]
        else:
            if not (shutil.which("javac") and shutil.which("java")):
                return "sin_compilador", "", "javac/java no están instalados"
            nombre, fuente = preparar_java(codigo)
            (dir_ / f"{nombre}.java").write_text(fuente, encoding="utf-8")
            compilacion = _ejecutar(["javac", "-nowarn", f"{nombre}.java"], dir_, TIEMPO_COMPILAR)
            ejecutable = ["java", "-Xss8m", nombre]
        if compilacion.returncode != 0:
            errores = [ln for ln in compilacion.stderr.splitlines() if "error" in ln.lower()]
            return "no_compila", "", (errores or compilacion.stderr.strip().splitlines() or [""])[0].strip()
        try:
            corrida = _ejecutar(ejecutable, dir_, TIEMPO_EJECUTAR)
        except subprocess.TimeoutExpired:
            return "tiempo", "", f"no terminó en {TIEMPO_EJECUTAR} s"
        if sanitizar and re.search(r"runtime error|AddressSanitizer|UndefinedBehaviorSanitizer", corrida.stderr):
            linea = next((ln for ln in corrida.stderr.splitlines() if "error" in ln.lower()), "")
            return "ub", corrida.stdout, linea.strip()
        if corrida.returncode != 0:
            return "error_ejecucion", corrida.stdout, (corrida.stderr.strip().splitlines() or [f"código {corrida.returncode}"])[-1]
        return "ok", corrida.stdout, ""


def verificar(q: Question, sanitizar: bool = False, todas: bool = False) -> Optional[Resultado]:
    """Verifica una pregunta de opción múltiple con código. None si no corresponde."""
    if q.type not in ("MC", "Short", "Numerical") or not q.choices:
        return None
    if not todas and not pide_salida(q):
        return None
    extraido = extraer_codigo(q)
    if extraido is None:
        return None
    lenguaje, codigo = extraido
    estado, salida, detalle = compilar_y_ejecutar(lenguaje, codigo, sanitizar)
    correctas = [c for c in q.choices if c.is_correct or (c.weight or 0) > 0]
    textos = [normalizar(c.text.text if c.text else "") for c in q.choices]
    texto_correctas = [normalizar(c.text.text if c.text else "") for c in correctas]
    resultado = Resultado(estado="", lenguaje=lenguaje, salida=salida, detalle=detalle, opciones=textos)

    if estado == "sin_compilador":
        resultado.estado = "sin_compilador"
        return resultado
    enunciado = q.stem.text if q.stem else ""
    if any(_INDEFINIDO.search(t) for t in texto_correctas):
        # La clave dice que el resultado no es determinista: nada que comparar.
        resultado.estado = "coincide"
        return resultado
    especiales = {"no_compila": _COMPILACION, "error_ejecucion": _EJECUCION, "tiempo": _INFINITO, "ub": _INDEFINIDO}
    if estado in especiales:
        if any(especiales[estado].search(t) for t in texto_correctas):
            resultado.estado = "coincide"
        elif estado == "no_compila" and (_SIN_CONTEXTO.search(detalle)
                                         or _SOBRE_COMPILAR.search(enunciado) or any(_SOBRE_COMPILAR.search(t) for t in texto_correctas)):
            resultado.estado, resultado.detalle = "revisar", f"no compila (fragmento o pregunta sobre compilación): {detalle}"
        elif estado in ("error_ejecucion", "tiempo") and _ENTRADA.search(codigo):
            resultado.estado, resultado.detalle = "revisar", f"usa archivos o entrada estándar: {detalle}"
        elif estado == "ub":
            resultado.estado = "comportamiento_indefinido"
        else:
            resultado.estado = estado
        return resultado

    if any(_COMPILA_BIEN.search(t) for t in texto_correctas):
        resultado.estado = "coincide"  # la pregunta es sobre si compila, y compila
        return resultado
    resultado.estado, resultado.coincide_con, resultado.detalle = comparar(salida, q.choices)
    if resultado.estado == "coincide_distractor" and _ENTRADA.search(codigo):
        resultado.estado = "revisar"
        resultado.detalle = "usa archivos o entrada estándar: la salida depende del entorno"
    return resultado



def comparar(salida: str, opciones: list) -> tuple:
    """(estado, opción coincidente, detalle) comparando por niveles: líneas exactas, espacios
    colapsados y, por último, palabras (todas las de la salida están en una sola clase de opciones)."""
    correcta = [c.is_correct or (c.weight or 0) > 0 for c in opciones]
    formas = [candidatos(c.text.text if c.text else "") for c in opciones]
    for nivel, f in (("exacta", _lineas), ("espacios", lambda t: " ".join(_lineas(t).split()))):
        obtenida = f(salida)
        if not obtenida:
            break
        aciertos = [i for i, fs in enumerate(formas) if obtenida in {f(x) for x in fs}]
        if any(correcta[i] for i in aciertos):
            return "coincide", formas[next(i for i in aciertos if correcta[i])][0], nivel
        if aciertos:
            if nivel == "espacios" and "\n" in _lineas(salida):
                # Sólo coincide ignorando los saltos de línea: si la correcta los describe en
                # prosa ("en líneas separadas"), no es evidencia de una clave equivocada.
                return "revisar", formas[aciertos[0]][0], "coincide con un distractor sólo ignorando los saltos de línea"
            return "coincide_distractor", formas[aciertos[0]][0], nivel
    palabras = _palabras(salida)
    if palabras:
        contienen = [i for i, fs in enumerate(formas) if palabras <= _palabras(" ".join(fs))]
        en_correctas = [i for i in contienen if correcta[i]]
        if en_correctas and len(contienen) == len(en_correctas):
            return "coincide", formas[en_correctas[0]][0], "palabras"
    return "revisar", None, "la salida no aparece literalmente en ninguna opción"

PROBLEMAS = ("coincide_distractor", "no_compila", "error_ejecucion", "tiempo", "comportamiento_indefinido")


# ---------------------------------------------------------------------------
# Estilo de la cátedra (reglas 0x00XXh de ripley, opcional)
# ---------------------------------------------------------------------------

INSTALAR_RIPLEY = 'uv pip install "ripley @ git+https://github.com/martinvilu/ripley"'


def verificador_de_estilo():
    """El evaluador de reglas de Programación I de ripley, o None si ripley no está instalado."""
    try:
        from ripley.core.p1_rules import P1RuleChecker
    except ImportError:
        return None
    return P1RuleChecker()


def revisar_estilo(q: Question, verificador) -> Optional[List[dict]]:
    """Reglas de estilo que incumple el código C del enunciado (None si no hay código C)."""
    extraido = extraer_codigo(q)
    if extraido is None or extraido[0] != "c":
        return None
    observaciones = verificador.analyze(extraido[1], "pregunta.c")
    return [{"regla": o.rule_code, "linea": o.line, "severidad": o.severity, "titulo": o.title}
            for o in observaciones]
