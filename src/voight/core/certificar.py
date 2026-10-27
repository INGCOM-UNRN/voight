"""Certificación de los snippets C de un banco con daedalus (`voight health validate --compilar`, Ola 14).

`voight verify` compila con `-w` (sin warnings) para comparar la salida con las opciones; acá la
pregunta es otra: si el código que ve el estudiante es C correcto según la cátedra. Cada snippet C
del enunciado se compila con daedalus (los flags de la cátedra: `-std=c11 -Wall -Wextra -pedantic
-Wconversion`…) y además `-O2`, que activa los avisos que dependen del análisis de flujo
(`-Wuninitialized`, `-Wsequence-point`, `-Warray-bounds`, `-Wdiv-by-zero`…), y si el toolchain
trae los sanitizers se ejecuta con `-fsanitize=address,undefined`. Estados:

- `certificada`: sin errores ni warnings, y sin comportamiento indefinido al ejecutarlo.
- `rechazada`: errores léxicos o sintácticos, warnings o comportamiento indefinido.
- `intencional`: tiene problemas, pero la pregunta trata justamente de eso (la clave dice «no
  compila», «comportamiento indefinido», un warning…): no se rechaza.
- `fragmento`: usa identificadores que no declara (un fragmento, no un programa): no se puede
  certificar solo.

Un snippet sin `main` se completa: si declara funciones o tipos va tal cual con un `main` vacío;
si son sentencias, dentro de `main`. Se agregan sólo los headers de lo que usa. Un snippet es una
parte de un programa: no se avisa de lo que no usa (variables, parámetros, funciones que el resto
del programa llamaría; `int x = 5; x++;` es una pregunta, no un descuido), y si todos sus errores
son por cosas declaradas en otra parte (tipos, variables) es un `fragmento`.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from voight.core.codigo import detectar_lenguaje
from voight.core.gift_model import Question
from voight.core.verificar import (
    _FENCE,
    _restaurar,
    _COMPILACION,
    _EJECUCION,
    _ENTRADA,
    _INDEFINIDO,
    _SIN_CONTEXTO,
    INCLUDES_C,
    TIEMPO_EJECUTAR,
)

INSTALAR_DAEDALUS = 'uv tool install "voight[compilar] @ git+https://github.com/INGCOM-UNRN/voight"'
_ADVERTENCIA = re.compile(r"warning|advertencia|aviso del compilador", re.I)
_PREGUNTA_SOBRE_ERRORES = re.compile(
    r"\b(compila|compilar[aá]|error(es)?|warnings?|advertencias?|indefinid\w*|v[aá]lid[oa])\b.*\?", re.I | re.S)
# Una definición de función, un tipo o una macro al comienzo de una línea: el snippet es un archivo
# (va tal cual, con un main vacío), no sentencias sueltas.
_NIVEL_ARCHIVO = re.compile(
    r"^[ \t]*(?:(?!(?:if|while|for|switch|return|else|do|case)\b)[A-Za-z_][\w \t\*]*\b[A-Za-z_]\w*[ \t]*"
    r"\([^;{}]*\)[ \t]*(?:\{|$)|typedef\b|struct[ \t]+\w+[ \t]*\{|enum[ \t]+\w*[ \t]*\{|union[ \t]+\w+[ \t]*\{|"
    r"#[ \t]*define\b)", re.M)
# Un snippet es una parte de un programa: lo que no usa (una variable, un parámetro, una función que
# el resto del programa llamaría) no es un error del código que se muestra.
_SIN_AVISOS_DE_USO = ["-Wno-unused-variable", "-Wno-unused-but-set-variable", "-Wno-unused-parameter",
                      "-Wno-unused-function", "-Wno-unused-label", "-Wno-unused-const-variable"]
# Errores de un fragmento que usa lo que se declara en otra parte (tipos, variables, funciones).
_FALTA_CONTEXTO = re.compile(_SIN_CONTEXTO.pattern + r"|unknown type name|incomplete type|storage size of .* isn't known"
                             r"|has no member named|undefined reference to|before '\.\.\.' token", re.I)
# Un error de sintaxis del propio snippet (no una consecuencia de lo que le falta).
_SINTAXIS = re.compile(r"expected |stray |missing terminating|unterminated|invalid preprocessing", re.I)
# Los headers que se agregan, sólo si el snippet usa algo de ellos (agregarlos todos chocaba con lo
# que el snippet define: `#define true 1`, `static int abs(int)`…).
_USA_HEADER = {
    "stdio.h": r"\b(printf|scanf|puts|putchar|getchar|fgets|fputs|fprintf|sprintf|snprintf|fopen|fclose|fread|"
               r"fwrite|fscanf|fseek|ftell|rewind|perror|FILE|EOF|stdin|stdout|stderr|feof|fflush)\b",
    "stdlib.h": r"\b(malloc|calloc|realloc|free|exit|atoi|atof|atol|strtol|strtod|rand|srand|abs|qsort|bsearch|"
                r"EXIT_SUCCESS|EXIT_FAILURE|system|getenv)\b",
    "string.h": r"\b(str\w+|mem(cpy|move|set|cmp|chr))\s*\(",
    "stdbool.h": r"\b(bool|true|false)\b",
    "math.h": r"\b(sqrt|pow|fabs|floor|ceil|round|sin|cos|tan|log|log10|exp|fmod|M_PI|INFINITY|NAN)\b",
    "limits.h": r"\b(INT|UINT|LONG|ULONG|CHAR|SCHAR|UCHAR|SHRT|USHRT|LLONG|ULLONG)_(MAX|MIN)\b",
    "ctype.h": r"\b(is(digit|alpha|alnum|space|upper|lower|punct|xdigit)|to(upper|lower))\s*\(",
    "stddef.h": r"\b(size_t|ptrdiff_t|offsetof|NULL)\b",
    "stdint.h": r"\bu?int(8|16|32|64|ptr)_t\b|\bINT(8|16|32|64)_(MAX|MIN)\b",
}
_SANITIZERS = ["-fsanitize=address,undefined", "-fno-sanitize-recover=all"]
_HALLAZGO_SANITIZER = re.compile(r"runtime error|AddressSanitizer|UndefinedBehaviorSanitizer|LeakSanitizer")


@dataclass
class Certificacion:
    estado: str  # certificada, rechazada, intencional, fragmento
    motivos: List[str] = field(default_factory=list)
    sin_sanitizers: bool = False  # el toolchain no trae los sanitizers: el UB sólo por los warnings
    ejecutada: bool = False


class SinDaedalus(RuntimeError):
    pass


_SANITIZERS_DISPONIBLES: Optional[bool] = None


def sanitizers_disponibles() -> bool:
    """Si gcc enlaza con -fsanitize=address,undefined (se prueba una vez: sin libasan, cada pregunta
    compilaba dos veces más para enterarse)."""
    global _SANITIZERS_DISPONIBLES
    if _SANITIZERS_DISPONIBLES is None:
        with tempfile.TemporaryDirectory(prefix="voight-san-") as tmp:
            fuente = Path(tmp) / "p.c"
            fuente.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            res = subprocess.run(["gcc", *_SANITIZERS, str(fuente), "-o", str(Path(tmp) / "p")],
                                 capture_output=True, text=True)
            _SANITIZERS_DISPONIBLES = res.returncode == 0
    return _SANITIZERS_DISPONIBLES


def armar_fuente(codigo: str) -> Tuple[str, int, bool]:
    """(fuente completa, líneas agregadas antes del snippet, si el snippet quedó dentro de main)."""
    sin_comentarios = re.sub(r"/\*.*?\*/|//[^\n]*", " ", codigo, flags=re.S)
    definidos = set(re.findall(r"#\s*define\s+(\w+)", codigo))
    includes = [f"#include <{h}>" for h in INCLUDES_C if f"<{h}>" not in codigo
                and re.search(_USA_HEADER[h], sin_comentarios)
                and not (h == "stdbool.h" and definidos & {"bool", "true", "false"})]
    snippet = codigo.rstrip().split("\n")
    if re.search(r"\bmain\s*\(", codigo) or _NIVEL_ARCHIVO.search(codigo):
        cola = [] if re.search(r"\bmain\s*\(", codigo) else ["", "int main(void)", "{", "    return 0;", "}"]
        return "\n".join(includes + snippet + cola) + "\n", len(includes), False
    return "\n".join(includes + ["int main(void)", "{"] + snippet + ["    return 0;", "}"]) + "\n", len(includes) + 2, True


def _compilar(fuente: Path, binario: Path, flags: List[str], sanitizar: bool = False):
    try:
        from daedalus.core.compiler import compilar_archivos
    except ImportError as exc:
        raise SinDaedalus(f"--compilar usa daedalus, que no está instalado en este entorno: {INSTALAR_DAEDALUS}") from exc
    return compilar_archivos([fuente], binario_salida=binario, flags_adicionales=flags,
                             reintentar_sin_sanitizers=sanitizar)


def _textos_correctos(q: Question) -> List[str]:
    return [c.text.text if c.text else "" for c in q.choices if c.is_correct or (c.weight or 0) > 0]


def es_intencional(q: Question) -> bool:
    """La pregunta trata sobre el error: la clave lo menciona o el enunciado pregunta si compila."""
    claves = _textos_correctos(q)
    if any(p.search(t) for t in claves for p in (_COMPILACION, _INDEFINIDO, _EJECUCION, _ADVERTENCIA)):
        return True
    enunciado = re.sub(r"```.*?```", " ", q.stem.text if q.stem else "", flags=re.S)
    return bool(_PREGUNTA_SOBRE_ERRORES.search(enunciado))


def codigo_c(q: Question) -> Optional[Tuple[str, bool]]:
    """(código, es una expresión suelta) del primer bloque C del enunciado, o None.

    Más estricto que `verify`, que toma por C cualquier bloque sin etiqueta: acá, un bloque sin
    etiqueta cuenta sólo si parece C y tiene una sentencia o un bloque (`;` o `{`); prosa, un
    comando de terminal o un nombre no se compilan. Una expresión sola (`exp(1000.0)`) se marca:
    no es un programa que certificar."""
    m = _FENCE.search(q.stem.text if q.stem else "")
    if not m:
        return None
    etiqueta = m.group(1).strip().lower()
    codigo = _restaurar(m.group(2)).replace("↵", "")
    if etiqueta in ("c", "h"):
        return codigo, not re.search(r"[;{}]|^\s*#", codigo, re.M)
    if etiqueta == "" and detectar_lenguaje(codigo) == "c" and re.search(r"[;{]", codigo):
        return codigo, False
    return None


def certificar(q: Question, ejecutar: bool = True, permitir: Sequence[str] = ()) -> Optional[Certificacion]:
    """La certificación del snippet C del enunciado, o None si la pregunta no tiene código C.

    `permitir` son warnings que no rechazan (los nombres de -W, sin el prefijo: `unused-parameter`)."""
    extraido = codigo_c(q)
    if extraido is None:
        return None
    codigo, expresion = extraido
    if expresion:
        return Certificacion(estado="fragmento", motivos=["es una expresión suelta, no un programa: no se certifica"])
    fuente_c, desplazamiento, envuelto = armar_fuente(codigo)
    lineas_snippet = codigo.rstrip().count("\n") + 1
    flags = ["-O2", *_SIN_AVISOS_DE_USO, *(f"-Wno-{w}" for w in permitir)]
    with tempfile.TemporaryDirectory(prefix="voight-certificar-") as tmp:
        fuente = Path(tmp) / "pregunta.c"
        fuente.write_text(fuente_c, encoding="utf-8")
        res = _compilar(fuente, Path(tmp) / "pregunta", flags)
        motivos: List[str] = []
        falta_contexto = sintaxis_propia = False
        for d in res.diagnosticos:
            if d.severidad not in ("error", "warning"):
                continue
            linea = (d.linea - desplazamiento) if d.linea else None
            en_snippet = bool(linea and 1 <= linea <= lineas_snippet)
            donde = f"línea {linea}" if en_snippet else "al completar el programa"
            bandera = f" [{d.flag}]" if d.flag and d.flag not in d.mensaje_original else ""
            motivos.append(f"{donde}: {d.severidad}: {d.mensaje_original}{bandera}")
            if d.severidad != "error":
                continue
            # Un fragmento usa lo que se declara en otra parte, o es una expresión suelta (el error cae
            # en lo que se agregó para completarlo). Lo demás que falle es en cascada, salvo un error de
            # sintaxis en el propio snippet.
            if _FALTA_CONTEXTO.search(d.mensaje_original) or not en_snippet:
                falta_contexto = True
            elif _SINTAXIS.search(d.mensaje_original):
                sintaxis_propia = True
        sin_contexto = not res.exito and falta_contexto and not sintaxis_propia
        if not res.exito and not motivos:
            motivos.append((res.stderr_crudo.strip().splitlines() or ["no compila"])[-1])
            sin_contexto = False
        certificacion = Certificacion(estado="certificada")
        if not motivos and ejecutar and not sanitizers_disponibles():
            certificacion.sin_sanitizers = True
        elif not motivos and ejecutar and not _ENTRADA.search(codigo):
            binario = Path(tmp) / "pregunta_san"
            con_san = _compilar(fuente, binario, flags + _SANITIZERS, sanitizar=True)
            certificacion.sin_sanitizers = con_san.sin_sanitizers
            if con_san.exito and not con_san.sin_sanitizers:
                certificacion.ejecutada = True
                try:
                    corrida = subprocess.run([str(binario)], input="", capture_output=True, text=True,
                                             timeout=TIEMPO_EJECUTAR, errors="replace")
                    hallazgo = next((ln.strip() for ln in corrida.stderr.splitlines()
                                     if _HALLAZGO_SANITIZER.search(ln)), None)
                    if hallazgo:
                        motivos.append(f"comportamiento indefinido al ejecutarlo: {hallazgo}")
                except subprocess.TimeoutExpired:
                    pass  # no terminar no es comportamiento indefinido: lo mira `voight verify`
    certificacion.motivos = motivos
    if motivos:
        if es_intencional(q):
            certificacion.estado = "intencional"
        elif sin_contexto:
            certificacion.estado = "fragmento"
        else:
            certificacion.estado = "rechazada"
    return certificacion


def certificar_banco(archivos: Sequence[Path], ejecutar: bool = True, permitir: Sequence[str] = (),
                     concurrencia: int = 4) -> dict:
    """La certificación de cada pregunta con código C de los archivos, agrupada por estado."""
    import contextlib
    import io
    from concurrent.futures import ThreadPoolExecutor

    from voight.core.lector import leer_archivos, unidades_de

    with contextlib.redirect_stdout(io.StringIO()):
        unidades = [u for u in unidades_de(leer_archivos(list(archivos))) if u.pregunta is not None]
    try:
        import daedalus.core.compiler  # noqa: F401
    except ImportError as exc:
        raise SinDaedalus(f"--compilar usa daedalus, que no está instalado en este entorno: {INSTALAR_DAEDALUS}") from exc
    with ThreadPoolExecutor(max_workers=max(1, concurrencia)) as ejecutor:
        pares = [(u, c) for u, c in zip(unidades, ejecutor.map(
            lambda u: certificar(u.pregunta, ejecutar=ejecutar, permitir=permitir), unidades), strict=True)
                 if c is not None]
    datos: dict = {"con_codigo_c": len(pares), "certificadas": 0, "rechazadas": [], "intencionales": [],
                   "fragmentos": [], "ejecutadas": sum(1 for _, c in pares if c.ejecutada),
                   "sin_sanitizers": any(c.sin_sanitizers for _, c in pares)}
    grupo = {"rechazada": "rechazadas", "intencional": "intencionales", "fragmento": "fragmentos"}
    for u, c in pares:
        if c.estado == "certificada":
            datos["certificadas"] += 1
        else:
            datos[grupo[c.estado]].append({"archivo": str(u.archivo), "titulo": u.pregunta.title or "<sin título>",
                                           "motivos": c.motivos})
    return datos


def seccion_markdown(datos: dict, max_items: int = 50) -> str:
    lineas = [f"\n## Código C certificado con daedalus ({datos['certificadas']} de {datos['con_codigo_c']})\n"]
    if datos["sin_sanitizers"]:
        lineas.append("> El toolchain no trae los sanitizers: el comportamiento indefinido se detecta sólo por los "
                      "warnings de `-O2`, no al ejecutar.\n")
    for clave, titulo in (("rechazadas", "Rechazadas: errores, warnings o comportamiento indefinido"),
                          ("fragmentos", "Fragmentos que no se pueden compilar solos"),
                          ("intencionales", "Con problemas a propósito (la pregunta trata sobre el error)")):
        if not datos[clave]:
            continue
        lineas.append(f"### {titulo} ({len(datos[clave])})")
        mostradas = datos[clave] if not max_items else datos[clave][:max_items]
        for item in mostradas:
            lineas.append(f"- {item['titulo']} — `{item['archivo']}`")
            lineas.extend(f"  - {m}" for m in item["motivos"][:5])
        if len(mostradas) < len(datos[clave]):
            lineas.append(f"- … y {len(datos[clave]) - len(mostradas)} más")
        lineas.append("")
    return "\n".join(lineas)
