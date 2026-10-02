"""Acciones semánticas y utilidades de llaves del parser GIFT."""

import re

from questions.core.gift_model import FormattedText




def _llaves_balanceadas(texto: str) -> bool:
    """True si las llaves del texto están balanceadas (ignorando escapes \\{ \\})."""
    profundidad = 0
    escapado = False
    for ch in texto:
        if escapado:
            escapado = False
            continue
        if ch == "\\":
            escapado = True
            continue
        if ch == "{":
            profundidad += 1
        elif ch == "}":
            profundidad -= 1
            if profundidad < 0:
                return False
    return profundidad == 0


def _extraer_ultimo_grupo_llaves(texto: str):
    r"""Localiza el ÚLTIMO grupo balanceado {..} del texto (ignora \{ \}).

    Devuelve (antes, contenido) o None si no cierra al final.
    """
    texto = texto.rstrip()
    if not texto.endswith("}"):
        return None
    escapados = set()
    i = 0
    n = len(texto)
    while i < n:
        if texto[i] == "\\":
            escapados.add(i + 1)
            i += 2
        else:
            i += 1
    profundidad = 0
    for j in range(n - 1, -1, -1):
        if j in escapados:
            continue
        c = texto[j]
        if c == "}":
            profundidad += 1
        elif c == "{":
            profundidad -= 1
            if profundidad == 0:
                return texto[:j], texto[j + 1:-1]
    return None


_CODIGO = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)


def _extraer_grupo_intermedio(texto: str):
    r"""Formato «palabra faltante»: el bloque de respuestas en medio del enunciado
    (`El {=gato ~perro} maúlla.`).

    Sólo cuenta un grupo {..} fuera del código (``` y `) que empiece con = o ~, como los
    que Moodle acepta en ese formato (opción múltiple y respuesta corta); ignora \{ \}.
    Devuelve (antes, contenido, después) o None.
    """
    enmascarado = _CODIGO.sub(lambda m: " " * len(m.group(0)), texto)
    n = len(enmascarado)
    i = 0
    while i < n:
        c = enmascarado[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            profundidad, j = 0, i
            while j < n:
                if enmascarado[j] == "\\":
                    j += 2
                    continue
                if enmascarado[j] == "{":
                    profundidad += 1
                elif enmascarado[j] == "}":
                    profundidad -= 1
                    if profundidad == 0:
                        break
                j += 1
            if j >= n:
                return None
            contenido = texto[i + 1:j]
            if contenido.lstrip()[:1] in ("=", "~"):
                return texto[:i], contenido, texto[j + 1:]
            i = j
        i += 1
    return None


class GiftSemantics:
    """Semantic actions for the GIFT parser."""
    
    def __init__(self):
        self.current_format = "moodle"
        self.current_id = None
        self.current_tags = []
    
    def _extract_tags_and_id(self, comments: list) -> tuple:
        """Extract tags and ID from comment lines."""
        tags: list = []
        question_id = None
        
        if not comments:
            return tags, question_id
            
        for comment in comments:
            if not comment:
                continue
            comment_str = str(comment)
            # Extract ID
            id_match = re.search(r'\[id:([^\]]+)\]', comment_str)
            if id_match:
                question_id = id_match.group(1).strip()
            # Extract tags
            for tag_match in re.finditer(r'\[tag:([^\]]+)\]', comment_str):
                tags.append(tag_match.group(1).strip())
        
        return tags, question_id
    
    def _decode_escapes(self, text: str) -> str:
        """Decode escaped characters in GIFT format."""
        if not text:
            return ""
        return (text
            .replace('\\\\', '\x00')  # Temporary placeholder
            .replace('\\:', ':')
            .replace('\\#', '#')
            .replace('\\=', '=')
            .replace('\\{', '{')
            .replace('\\}', '}')
            .replace('\\~', '~')
            .replace('\\n', '\n')
            .replace('\x00', '\\'))
    
    def _parse_formatted_text(self, ast) -> FormattedText:
        """Parse formatted text from AST."""
        if ast is None:
            return FormattedText()
        
        if isinstance(ast, str):
            return FormattedText(text=self._decode_escapes(ast.strip()))
        
        if isinstance(ast, list):
            text = ''.join(str(t) for t in ast)
            return FormattedText(text=self._decode_escapes(text.strip()))
        
        return FormattedText()


_INICIO_DE_PREGUNTA = re.compile(r"^\s*(::|\$CATEGORY:)")


def corta_en_blanco(bloque: str, lineas: list, i: int) -> bool:
    """¿La línea en blanco `lineas[i]` termina el bloque de pregunta `bloque`?

    Sí si las llaves del bloque están balanceadas (el código con líneas en blanco queda
    dentro de su pregunta) o si lo siguiente, salteando comentarios `//`, es otra
    pregunta (`::título::`) o una `$CATEGORY`: así una pregunta con llaves sin cerrar
    no se traga el resto del archivo, que es lo que haría Moodle.
    """
    if _llaves_balanceadas(bloque):
        return True
    siguiente = next((x for x in lineas[i + 1:] if x.strip() and not x.lstrip().startswith("//")), "")
    return bool(_INICIO_DE_PREGUNTA.match(siguiente))
