import re
import xml.etree.ElementTree as ET

from voight.core.parser import GiftParser, Question


def convert_html_tags_to_markdown(text):
    """Convierte tags HTML (y sus versiones fullwidth) a markdown."""
    # Versiones fullwidth (comunes en algunos de estos archivos)
    text = re.sub(r'＜p＞(.*?)＜/p＞', r'\1\n', text, flags=re.DOTALL)
    text = re.sub(r'＜code＞(.*?)＜/code＞', r'`\1`', text, flags=re.DOTALL)
    text = re.sub(r'＜strong＞(.*?)＜/strong＞', r'**\1**', text, flags=re.DOTALL)
    text = re.sub(r'＜pre＞(.*?)＜/pre＞', r'```\n\1\n```', text, flags=re.DOTALL)

    # Versiones normales
    text = re.sub(r'<code>(.*?)</code>', r'`\1`', text, flags=re.DOTALL)
    text = re.sub(r'<p>(.*?)</p>', r'\1\n', text, flags=re.DOTALL)
    text = re.sub(r'<strong>(.*?)</strong>', r'**\1**', text, flags=re.DOTALL)
    text = re.sub(r'<b>(.*?)</b>', r'**\1**', text, flags=re.DOTALL)
    text = re.sub(r'<pre>(.*?)</pre>', r'```\n\1\n```', text, flags=re.DOTALL)
    text = re.sub(r'<br\s*/?>', r'\n', text)

    return text.strip()


_CAMPO_HTML = re.compile(
    r'(<(\w+)\b[^>]*?)\bformat="html"([^>]*>\s*<text\b[^>]*(?<!/)>)(.*?)(</text>)', re.DOTALL)


def html_a_markdown_xml(xml: str) -> tuple:
    """Convierte a markdown los campos HTML de un Moodle XML, uno por uno.

    Sólo los campos cuyo texto cambia pasan a format="markdown" (y a CDATA); los demás
    conservan su formato. Devuelve el XML y la cantidad de campos convertidos.
    """
    from voight.core.codigo import _CDATA, _desescapar_xml, a_cdata

    convertidos = 0

    def campo(m: re.Match) -> str:
        nonlocal convertidos
        antes, _, medio, contenido, cierre = m.groups()
        partes = _CDATA.findall(contenido)
        texto = "".join(partes) if partes and not _CDATA.sub("", contenido).strip() else _desescapar_xml(contenido)
        nuevo = convert_html_tags_to_markdown(texto)
        if nuevo == texto.strip():
            return m.group(0)
        convertidos += 1
        return f'{antes}format="markdown"{medio}{a_cdata(nuevo)}{cierre}'

    return _CAMPO_HTML.sub(campo, xml), convertidos


# ============================================================================
# Conversores GIFT <-> Moodle XML sobre el modelo unificado de preguntas
# ============================================================================

_CD_OPEN = "\ue000"
_CD_CLOSE = "\ue001"


def _escape_gift(text: str, context: str = "stem") -> str:
    """Escapa caracteres especiales de GIFT según el contexto."""
    if not text:
        return ""
    out = text.replace('\\', '\\\\')
    specials = {
        "title": [':', '~', '=', '#', '{', '}'],
        "stem": ['~', '=', '#', '{', '}'],
        "answer": ['=', '#', '{', '}', '~'],
    }.get(context, ['~', '=', '#', '{', '}'])
    for ch in specials:
        out = out.replace(ch, '\\' + ch)
    return out


def _cdata(s: str) -> str:
    s = s.replace("]]>", "]]]]><![CDATA[>")
    return f"{_CD_OPEN}{s}{_CD_CLOSE}"


def _cdata_sub(parent, tag, text=None):
    """Agrega un subelemento cuyo texto se envolverá en CDATA al serializar."""
    el = ET.SubElement(parent, tag)
    if text is not None:
        el.text = _cdata(text)
    return el


def _plain_sub(parent, tag, value=None, attrs=None):
    """Agrega un subelemento estructural con texto plano (sin CDATA)."""
    el = ET.SubElement(parent, tag, attrs or {})
    if value is not None:
        el.text = str(value)
    return el


def _formato_moodle(ft) -> str:
    fmt = (getattr(ft, "format", None) or "moodle").lower()
    return {"markdown": "markdown", "html": "html"}.get(fmt, "moodle_auto_format")


def _ft_text(ft) -> str:
    if ft is None:
        return ""
    return ft.text or ""


def _agregar_feedback(answer_el, feedback) -> None:
    if feedback is not None:
        fb = _plain_sub(answer_el, "feedback")
        fb.set("format", "html")
        _cdata_sub(fb, "text", _ft_text(feedback))


def _pregunta_a_xml(q: Question, defaultgrade: float = 1.0) -> ET.Element:
    """Serializa una Question del modelo unificado a un elemento <question> de Moodle."""
    if q.type == "Category":
        el = ET.Element("question", {"type": "category"})
        cat = _cdata_sub(el, "category")
        ruta = q.title or "$course$"
        if not ruta.startswith("$course$"):
            ruta = f"$course$/{ruta}"
        _cdata_sub(cat, "text", ruta)
        return el

    tipo_moodle = {
        "MC": "multichoice",
        "Short": "shortanswer",
        "TF": "truefalse",
        "Matching": "matching",
        "Numerical": "numerical",
        "Essay": "essay",
        "Description": "description",
    }
    qtype = tipo_moodle.get(q.type, q.type.lower())
    es_cloze = q.has_embedded_answers and "{" in _ft_text(q.stem)
    if q.type == "Description" and es_cloze:
        qtype = "cloze"

    el = ET.Element("question", {"type": qtype})
    _cdata_sub(_cdata_sub(el, "name"), "text", q.title or "Pregunta")

    qt = _cdata_sub(el, "questiontext")
    qt.set("format", _formato_moodle(q.stem))
    _cdata_sub(qt, "text", _ft_text(q.stem))

    if q.global_feedback is not None:
        gf = _cdata_sub(el, "generalfeedback")
        gf.set("format", "html")
        _cdata_sub(gf, "text", _ft_text(q.global_feedback))

    def respuesta(texto, fraccion, formato="moodle_auto_format"):
        ans = _plain_sub(el, "answer", attrs={"fraction": f"{fraccion:g}", "format": formato})
        _cdata_sub(ans, "text", texto)
        return ans

    if q.type == "MC":
        multiple = sum(1 for c in q.choices if c.is_correct) > 1
        _plain_sub(el, "single", "false" if multiple else "true")
        _plain_sub(el, "shuffleanswers", "true")
        for c in q.choices:
            frac = 100.0 if c.is_correct else 0.0
            if c.weight is not None:
                frac = float(c.weight)
            ans = respuesta(_ft_text(c.text), frac, _formato_moodle(c.text))
            _agregar_feedback(ans, c.feedback)
        _plain_sub(el, "defaultgrade", f"{defaultgrade:g}")
        _plain_sub(el, "penalty", "0.3333333")

    elif q.type == "Short":
        _plain_sub(el, "usecase", "0")
        for c in q.choices:
            # =%50%Paris: respuesta aceptada con crédito parcial.
            frac = float(c.weight) if c.weight is not None else (100.0 if c.is_correct else 0.0)
            ans = respuesta(_ft_text(c.text), frac)
            _agregar_feedback(ans, c.feedback)
        _plain_sub(el, "defaultgrade", f"{defaultgrade:g}")
        _plain_sub(el, "penalty", "0.3333333")

    elif q.type == "TF":
        _plain_sub(el, "shuffleanswers", "false")
        for valor, es_verdadera in (("true", True), ("false", False)):
            acierto = (q.is_true == es_verdadera)
            ans = respuesta(valor, 100.0 if acierto else 0.0)
            fb = q.true_feedback if es_verdadera else q.false_feedback
            _agregar_feedback(ans, fb)
        _plain_sub(el, "defaultgrade", f"{defaultgrade:g}")
        _plain_sub(el, "penalty", "1")

    elif q.type == "Matching":
        _plain_sub(el, "shuffleanswers", "true")
        for par in q.match_pairs:
            sq = _cdata_sub(el, "subquestion")
            sq.set("format", _formato_moodle(par.subquestion))
            _cdata_sub(sq, "text", _ft_text(par.subquestion))
            ans = _cdata_sub(sq, "answer")
            _cdata_sub(ans, "text", par.subanswer or "")
        _plain_sub(el, "defaultgrade", f"{max(defaultgrade, len(q.match_pairs)):g}")
        _plain_sub(el, "penalty", "0.3333333")

    elif q.type == "Numerical":
        for c in q.choices:
            raw = (_ft_text(c.text) or "").strip()
            if raw.endswith("%") and ":" not in raw:
                continue  # residuo de peso porcentual, no un valor numérico
            numero, tolerancia = valor_y_tolerancia(raw)
            frac = c.weight if c.weight is not None else (100.0 if c.is_correct else 0.0)
            ans = respuesta(numero, frac)
            if tolerancia:
                _plain_sub(ans, "tolerance", tolerancia)
            _agregar_feedback(ans, c.feedback)
        _plain_sub(el, "defaultgrade", f"{defaultgrade:g}")
        _plain_sub(el, "penalty", "0.3333333")

    elif q.type == "Essay":
        _plain_sub(el, "responseformat", "editor")
        _plain_sub(el, "responsefieldlines", "10")
        _plain_sub(el, "defaultgrade", f"{defaultgrade:g}")
        _plain_sub(el, "penalty", "0")

    return el


def _serializar_quiz(quiz: ET.Element) -> str:
    """Serializa un <quiz> armado con `_cdata_sub` y/o elementos parseados.

    No desescapa el documento entero ni borra líneas en blanco (las del código de un
    CDATA son contenido): quita las marcas de CDATA y deja que el formateador XML vuelva
    a envolver cada <text> en CDATA e indente.
    """
    from voight.core.formatter import format_xml_content

    xml = ET.tostring(quiz, encoding="unicode").replace(_CD_OPEN, "").replace(_CD_CLOSE, "")
    return format_xml_content(xml)


def valor_y_tolerancia(raw: str) -> tuple:
    """(valor, tolerancia) de una respuesta numérica de GIFT: `3:0.5`, el rango `1..5`
    (como Moodle, el punto medio ± la mitad del intervalo) o un número solo (tolerancia "")."""
    raw = (raw or "").strip()
    numero = r"[+-]?\d+(?:\.\d+)?"
    m = re.match(rf"^({numero})\s*:\s*({numero})$", raw)
    if m:
        return m.group(1), m.group(2)
    m = re.match(rf"^({numero})\s*\.\.\s*({numero})$", raw)
    if m:
        bajo, alto = sorted((float(m.group(1)), float(m.group(2))))
        return f"{(bajo + alto) / 2:g}", f"{(alto - bajo) / 2:g}"
    return raw or "0", ""


def question_to_gift(q: Question, escapar_codigo: bool = True) -> str:
    """Serializa una Question del modelo unificado a GIFT (sin comentarios ni categoría).

    Los textos se escapan; el código ya protegido (fullwidth) no tiene nada que escapar.
    Con `escapar_codigo` en falso el código queda tal cual (la forma que se le envía a
    un LLM: el resultado se protege antes de interpretarlo).
    """
    if not escapar_codigo:
        from voight.core.codigo import fuera_de_codigo

        def _escape_gift(texto, contexto="stem", _escapar=globals()["_escape_gift"]):
            return fuera_de_codigo(texto or "", lambda t: _escapar(t, contexto))
    else:
        _escape_gift = globals()["_escape_gift"]
    prefijo = {"markdown": "[markdown]", "html": "[html]", "plain": "[plain]"}.get(
        (q.stem.format if q.stem else "moodle") or "moodle", "")
    encabezado = f"::{_escape_gift(q.title, 'title')}::" if q.title else ""
    enunciado = prefijo + _escape_gift(_ft_text(q.stem), "stem")

    def retro(ft, marca="#") -> str:
        return f" {marca}{_escape_gift(_ft_text(ft), 'answer')}" if ft is not None and _ft_text(ft) else ""

    def opcion(c, numerica=False) -> str:
        if c.weight is not None:
            simbolo = ("=" if c.is_correct else "~") + f"%{c.weight:g}%"
        else:
            simbolo = "=" if c.is_correct else "~"
        texto = _ft_text(c.text)
        return simbolo + (texto if numerica else _escape_gift(texto, "answer")) + retro(c.feedback)

    general = retro(q.global_feedback, "####")
    if q.type in ("MC", "Short"):
        bloque = "{\n" + "\n".join("\t" + opcion(c) for c in q.choices) + (f"\n\t{general.strip()}" if general else "") + "\n}"
    elif q.type == "Numerical":
        bloque = "{#\n" + "\n".join("\t" + opcion(c, numerica=True) for c in q.choices) + (f"\n\t{general.strip()}" if general else "") + "\n}"
    elif q.type == "TF":
        # Como Moodle: primero la retro para quien responde mal, después para quien acierta.
        mal, bien = (q.false_feedback, q.true_feedback) if q.is_true else (q.true_feedback, q.false_feedback)
        retros = ""
        if _ft_text(mal) or _ft_text(bien):
            retros = "#" + _escape_gift(_ft_text(mal), "answer")
            if _ft_text(bien):
                retros += "#" + _escape_gift(_ft_text(bien), "answer")
        bloque = "{" + ("T" if q.is_true else "F") + retros + general + "}"
    elif q.type == "Matching":
        pares = [f"\t={_escape_gift(_ft_text(p.subquestion), 'answer')} -> {_escape_gift(p.subanswer or '', 'answer')}"
                 for p in q.match_pairs]
        bloque = "{\n" + "\n".join(pares) + (f"\n\t{general.strip()}" if general else "") + "\n}"
    elif q.type == "Essay":
        bloque = "{" + general + "}"
    else:  # Description
        return (encabezado + enunciado).strip()
    return f"{encabezado}{enunciado}\n{bloque}"


def gift_to_xml(gift_content: str) -> str:
    """Convierte contenido GIFT a Moodle XML usando el modelo unificado de preguntas."""
    preguntas = GiftParser()._manual_parse(gift_content or "")
    quiz = ET.Element("quiz")
    for q in preguntas:
        quiz.append(_pregunta_a_xml(q))
    return _serializar_quiz(quiz)


# ---------------------------------------------------------------------------
# Moodle XML -> GIFT (sobre el modelo unificado)
# ---------------------------------------------------------------------------

_TIPOS_GIFT = ("MC", "Short", "TF", "Matching", "Numerical", "Essay", "Description")


def _text_de(el, default=""):
    """Extrae texto del hijo <text> de un elemento (con o sin CDATA)."""
    if el is None:
        return default
    t = el.find("text")
    if t is None:
        return default
    return t.text if t.text is not None else default


def _sin_equivalente_gift(q: ET.Element) -> str:
    """Cloze y tipos de plugins: GIFT no los representa; se conservan título y enunciado
    (las respuestas embebidas de un cloze quedan en el texto) y, si no es cloze, un {}."""
    titulo = _escape_gift(_text_de(q.find("name")).strip(), "title")
    qt = q.find("questiontext")
    formato = (qt.get("format") if qt is not None else "") or "html"
    prefijo = {"markdown": "[markdown]", "html": "[html]"}.get(formato, "")
    bloque = "" if (q.get("type") or "").lower() in ("cloze", "multianswer") else " {}"
    encabezado = f"::{titulo}:: " if titulo else ""
    return f"{encabezado}{prefijo}{_escape_gift(_text_de(qt).strip(), 'stem')}{bloque}".rstrip()


def _seguro_para_gift(gift: str) -> str:
    """Lo que GIFT no puede representar crudo dentro del código, con su forma protegida.

    Una línea vacía o de sólo espacios (también U+2007 o NBSP) corta la pregunta → `↵`;
    una línea que empieza con `//` es un comentario de GIFT → `／／`; un `->` en las
    opciones convierte la pregunta en emparejamiento → `-＞`. El resto del código queda
    igual (los demás caracteres ya los escapa `_escape_gift`).
    """
    from voight.core.codigo import MARCA_SALTO, transformar_secciones

    def proteger(codigo: str, html: bool, multilinea: bool, bloque: bool = False) -> str:
        lineas = codigo.split("\n")
        ultima = len(lineas) - 1
        for i, linea in enumerate(lineas):
            if 0 < i < ultima and not linea.strip():
                linea = MARCA_SALTO
            elif linea.lstrip().startswith("//"):
                sangria = linea[: len(linea) - len(linea.lstrip())]
                linea = sangria + "／／" + linea.lstrip()[2:]
            lineas[i] = linea.replace("->", "-＞")
        return "\n".join(lineas)

    def parrafos(texto: str) -> str:
        # Fuera del código, una línea en blanco (párrafo de markdown) se escribe con el
        # escape \\n de GIFT, que Moodle y el parser vuelven a convertir en salto de línea;
        # una línea que empieza con // (código sin backticks) también se protege.
        texto = re.sub(r"(?m)^([ \t\u3000\u2007\u00a0]*)//", "\\1／／", texto)
        return re.sub(r"\n((?:[ \t]*\n)+)", lambda m: "\n" + "\\n" * m.group(1).count("\n"), texto)

    from voight.core.codigo import fuera_de_codigo

    return fuera_de_codigo(transformar_secciones(gift, proteger, "gift")[0], parrafos, "gift")


def xml_to_gift(xml_content: str) -> str:
    """Convierte contenido Moodle XML a GIFT: XML → modelo unificado → GIFT.

    El formato de cada texto se conserva con su prefijo ([html], [markdown]); el HTML no
    se reescribe como markdown (eso es `convert html-to-md`).
    """
    from voight.core.moodle_xml import _pregunta

    raiz = ET.fromstring(xml_content)
    nodos = [raiz] if raiz.tag == "question" else raiz.findall("question")
    bloques = []
    for nodo in nodos:
        q = _pregunta(nodo)
        if q.type == "Category":
            ruta = (q.title or "").replace("$course$", "").strip().strip("/")
            bloques.append(f"$CATEGORY: $course${'/' + ruta if ruta else ''}")
        elif q.type in _TIPOS_GIFT:
            # idnumber y tags viajan en el comentario que GIFT (y el parser) entienden.
            meta = ([f"[id:{q.id}]"] if q.id else []) + [f"[tag:{t}]" for t in q.tags]
            bloques.append((f"// {' '.join(meta)}\n" if meta else "") + _seguro_para_gift(question_to_gift(q)))
        else:
            # Cloze y plugins: el enunciado también necesita las protecciones de GIFT.
            bloques.append(_seguro_para_gift(_sin_equivalente_gift(nodo)))
    return "\n\n".join(b for b in bloques if b.strip()) + ("\n" if bloques else "")
