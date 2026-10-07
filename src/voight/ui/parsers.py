"""Parsers del editor web: Moodle XML nativo y adaptador GIFT sobre el modelo unificado.

Ambos exponen el mismo contrato al editor. Campos comunes (name, questiontext, formatos,
generalfeedback, defaultgrade, penalty, tags) y, según `answer_mode`:

- choices (multichoice, shortanswer): answers [{fraction, text, feedback}]
- numerical / formulas (numerical, calculated*): answers con `tolerance`
- truefalse: answers [{text: 'true'|'false', fraction, feedback}]
- pairs (matching): subquestions [{text, answer}]
- ordering: answers en el orden correcto
- groups (gapselect, ddwtos): choices [{text, group, infinite}] para los huecos [[n]]
- none: sin respuestas editables (ensayo, descripción, cloze, arrastrar sobre imagen…)

Al guardar un XML sólo se tocan los elementos que el editor conoce para ese tipo: el resto
(unidades, datasets, imágenes, zonas, opciones de plugins) se conserva tal cual.
"""

import copy
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from voight.core.converter import _escape_gift, _seguro_para_gift, question_to_gift, valor_y_tolerancia
from voight.core.gift_model import Choice, FormattedText, MatchPair, Question
from voight.core.gift_semantics import corta_en_blanco
from voight.core.parser import GiftParser


# Tipos GIFT del modelo unificado -> tipos visibles por el editor (Moodle)
_TIPOS_A_EDITOR = {
    "MC": "multichoice",
    "Short": "shortanswer",
    "TF": "truefalse",
    "Matching": "matching",
    "Numerical": "numerical",
    "Essay": "essay",
    "Description": "description",
}

MODOS = {
    "multichoice": "choices",
    "shortanswer": "choices",
    "numerical": "numerical",
    "calculated": "formulas",
    "calculatedsimple": "formulas",
    "calculatedmulti": "formulas",
    "truefalse": "truefalse",
    "matching": "pairs",
    "ordering": "ordering",
    "gapselect": "groups",
    "ddwtos": "groups",
}

_CON_ANSWERS = ("choices", "numerical", "formulas", "truefalse", "ordering")

# Opciones propias de cada tipo que el editor muestra y guarda (booleanas como '1'/'0').
_BOOLEANOS = ("single", "shuffleanswers", "usecase", "responserequired", "subcats")
_ESCALARES = {
    "multichoice": ("single", "shuffleanswers", "answernumbering"),
    "shortanswer": ("usecase",),
    "matching": ("shuffleanswers",),
    "gapselect": ("shuffleanswers",),
    "ddwtos": ("shuffleanswers",),
    "essay": ("responseformat", "responserequired", "responsefieldlines", "attachments"),
    "randomsamatch": ("choose", "subcats"),
}

_FORMATOS_GIFT = {"markdown": "markdown", "html": "html", "plain": "plain", "moodle": "moodle_auto_format"}


def _a_bool(valor) -> str:
    return '1' if str(valor).strip().lower() in ('1', 'true', 'yes') else '0'


def _fraccion(valor) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


class QuestionParser:
    """Parser de preguntas XML de Moodle"""

    def __init__(self):
        try:
            import markdown
            self.md = markdown.Markdown(extensions=['extra', 'codehilite', 'fenced_code'])
        except ImportError:
            self.md = None

    # -- lectura -----------------------------------------------------------

    @staticmethod
    def _leer(filepath):
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
        return ET.parse(filepath, parser=parser)

    @staticmethod
    def _pregunta(raiz):
        """La primera pregunta que no es una categoría (o la raíz si es una <question>)."""
        candidatas = [raiz] if raiz.tag == 'question' else raiz.iter('question')
        for q in candidatas:
            if q.get('type') != 'category':
                return q
        raise ValueError("No se encontró ninguna pregunta en el XML")

    def parse_question(self, filepath):
        """Parsea un archivo XML de pregunta de Moodle a un diccionario editable."""
        try:
            q = self._pregunta(self._leer(filepath).getroot())
        except ET.ParseError as e:
            raise ValueError(f"Error al parsear XML: {e}")

        tipo = q.get('type', 'unknown')
        modo = MODOS.get(tipo, 'none')
        qt, gf = q.find('questiontext'), q.find('generalfeedback')
        data = {
            'type': tipo,
            'answer_mode': modo,
            'source_format': 'xml',
            'name': self._get_text_content(q, 'name/text'),
            'questiontext': self._get_text_content(q, 'questiontext/text'),
            'questiontext_format': qt.get('format') if qt is not None else None,
            'generalfeedback': self._get_text_content(q, 'generalfeedback/text'),
            'generalfeedback_format': gf.get('format') if gf is not None else None,
            'defaultgrade': self._get_text_content(q, 'defaultgrade'),
            'penalty': self._get_text_content(q, 'penalty'),
            'hidden': self._get_text_content(q, 'hidden'),
            'tags': self._get_tags(q),
            'answers': self._get_answers(q) if modo in _CON_ANSWERS else [],
            'filepath': filepath,
        }
        if modo == 'ordering':
            data['answers'].sort(key=lambda a: _fraccion(a['fraction']))
        elif modo == 'pairs':
            data['subquestions'] = [
                {'text': self._get_text_content(s, 'text'), 'answer': self._get_text_content(s, 'answer/text')}
                for s in q.findall('subquestion')
            ]
        elif modo == 'groups':
            etiqueta = 'dragbox' if tipo == 'ddwtos' else 'selectoption'
            data['choices'] = [
                {'text': self._get_text_content(c, 'text'), 'group': self._get_text_content(c, 'group') or '1',
                 'infinite': c.find('infinite') is not None}
                for c in q.findall(etiqueta)
            ]
        if tipo.startswith('calculated'):
            data['datasets'] = [
                {'name': self._get_text_content(d, 'name/text'),
                 'min': self._get_text_content(d, 'minimum/text'),
                 'max': self._get_text_content(d, 'maximum/text')}
                for d in q.findall('dataset_definitions/dataset_definition')
            ]
        if tipo in ('ddimageortext', 'ddmarker'):
            data['drags'] = [self._get_text_content(d, 'text') for d in q.findall('drag')]

        for campo in _ESCALARES.get(tipo, ()):
            valor = self._get_text_content(q, campo)
            data[campo] = _a_bool(valor) if campo in _BOOLEANOS and valor else valor
        if tipo == 'essay':
            data['graderinfo'] = self._get_text_content(q, 'graderinfo/text')
        return data

    def _get_text_content(self, element, path):
        elem = element.find(path)
        return (elem.text or '').strip() if elem is not None else ''

    def _get_tags(self, question_elem):
        return [t.text.strip() for t in question_elem.findall('tags/tag/text') if t.text]

    def _get_answers(self, question_elem):
        answers = []
        for answer_elem in question_elem.findall('answer'):
            text_elem = answer_elem.find('text')
            feedback_elem = answer_elem.find('feedback')
            answer = {
                'fraction': answer_elem.get('fraction', '0'),
                'answer_format': answer_elem.get('format'),
                'text_format': text_elem.get('format') if text_elem is not None else None,
                'text': self._get_text_content(answer_elem, 'text'),
                'feedback': self._get_text_content(answer_elem, 'feedback/text'),
                'feedback_format': feedback_elem.get('format') if feedback_elem is not None else None,
            }
            if answer_elem.find('tolerance') is not None:
                answer['tolerance'] = self._get_text_content(answer_elem, 'tolerance')
            answers.append(answer)
        return answers

    def render_markdown(self, text):
        """Renderiza markdown a HTML"""
        if not text or self.md is None:
            return ''
        return self.md.convert(text)

    # -- escritura ---------------------------------------------------------

    def save_question(self, filepath, question_data):
        """Guarda la pregunta editada: sólo cambia lo que el editor conoce para su tipo."""
        try:
            tree = self._leer(filepath)
            raiz = tree.getroot()
            q = self._pregunta(raiz)
            tipo = q.get('type', '')  # el tipo es el del archivo, no el que manda el cliente
            modo = MODOS.get(tipo, 'none')
            d = question_data

            self._texto(q, 'name/text', d.get('name', ''))
            self._texto(q, 'questiontext/text', d.get('questiontext', ''))
            if d.get('questiontext_format'):
                q.find('questiontext').set('format', d['questiontext_format'])
            if 'generalfeedback' in d:
                self._texto(q, 'generalfeedback/text', d['generalfeedback'], formato='html')
            for campo in ('defaultgrade', 'penalty'):
                if d.get(campo) not in (None, ''):
                    self._texto(q, campo, d[campo])

            if modo in _CON_ANSWERS and 'answers' in d:
                self._guardar_answers(q, tipo, modo, d['answers'])
            elif modo == 'pairs' and 'subquestions' in d:
                self._guardar_pares(q, d['subquestions'])
            elif modo == 'groups' and 'choices' in d:
                self._guardar_grupos(q, tipo, d['choices'])

            for campo in _ESCALARES.get(tipo, ()):
                if campo in d:
                    self._escalar(q, campo, d[campo])
            if tipo == 'essay' and 'graderinfo' in d:
                self._texto(q, 'graderinfo/text', d['graderinfo'], formato='html')

            if 'tags' in d:
                self._guardar_tags(q, d['tags'])

            self._write_xml(raiz, filepath)
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Error guardando pregunta: {e}")

    @staticmethod
    def _texto(padre, ruta, valor, formato=None):
        """Escribe el texto de padre/ruta, creando los elementos que falten."""
        actual = padre
        for parte in ruta.split('/'):
            hijo = actual.find(parte)
            if hijo is None:
                hijo = ET.SubElement(actual, parte)
                if formato and parte != 'text':
                    hijo.set('format', formato)
            actual = hijo
        actual.text = '' if valor is None else str(valor)
        return actual

    def _escalar(self, q, campo, valor):
        el = q.find(campo)
        if valor in (None, '') and el is None:
            return  # sin valor y sin elemento: queda el valor por defecto de Moodle
        if campo in _BOOLEANOS:
            si = _a_bool(valor) == '1'
            # Se respeta cómo lo escribió Moodle: true/false o 1/0 (single siempre true/false).
            palabras = campo == 'single' or (el is not None and (el.text or '').strip() in ('true', 'false'))
            valor = ('true' if si else 'false') if palabras else ('1' if si else '0')
        self._texto(q, campo, valor)

    @staticmethod
    def _sincronizar(q, etiqueta, items, rellenar, nuevo):
        """Actualiza en su lugar los elementos `etiqueta` de q con `items`: reutiliza los que
        hay (conservan sus hijos desconocidos), clona el último para los nuevos y borra los
        que sobran."""
        existentes = q.findall(etiqueta)
        ultimo = existentes[-1] if existentes else None
        for i, item in enumerate(items):
            if i < len(existentes):
                el = existentes[i]
            else:
                el = copy.deepcopy(ultimo) if ultimo is not None else nuevo()
                hijos = list(q)
                q.insert(hijos.index(ultimo) + 1 if ultimo is not None else len(hijos), el)
                ultimo = el
            rellenar(el, item, i)
        for el in existentes[len(items):]:
            q.remove(el)

    def _guardar_answers(self, q, tipo, modo, answers):
        formato = 'html' if modo in ('choices', 'ordering') else 'moodle_auto_format'

        def nuevo():
            el = ET.Element('answer', {'fraction': '0', 'format': formato})
            ET.SubElement(el, 'text')
            if modo in ('numerical', 'formulas'):
                ET.SubElement(el, 'tolerance').text = '0'
            return el

        def rellenar(el, a, i):
            el.set('fraction', str(i + 1) if modo == 'ordering' else f"{_fraccion(a.get('fraction')):g}")
            self._texto(el, 'text', a.get('text', ''))
            if a.get('feedback') or el.find('feedback') is not None:
                self._texto(el, 'feedback/text', a.get('feedback', ''), formato='html')
            if modo in ('numerical', 'formulas') and a.get('tolerance') not in (None, ''):
                self._texto(el, 'tolerance', a['tolerance'])

        self._sincronizar(q, 'answer', answers, rellenar, nuevo)

    def _guardar_pares(self, q, pares):
        def nuevo():
            el = ET.Element('subquestion', {'format': 'html'})
            ET.SubElement(el, 'text')
            ET.SubElement(ET.SubElement(el, 'answer'), 'text')
            return el

        def rellenar(el, par, _):
            self._texto(el, 'text', par.get('text', ''))
            self._texto(el, 'answer/text', par.get('answer', ''))

        self._sincronizar(q, 'subquestion', pares, rellenar, nuevo)

    def _guardar_grupos(self, q, tipo, opciones):
        etiqueta = 'dragbox' if tipo == 'ddwtos' else 'selectoption'

        def nuevo():
            el = ET.Element(etiqueta)
            ET.SubElement(el, 'text')
            ET.SubElement(el, 'group')
            return el

        def rellenar(el, op, _):
            self._texto(el, 'text', op.get('text', ''))
            self._texto(el, 'group', str(op.get('group') or '1'))
            if tipo == 'ddwtos':
                infinito = el.find('infinite')
                if op.get('infinite') and infinito is None:
                    ET.SubElement(el, 'infinite')
                elif not op.get('infinite') and infinito is not None:
                    el.remove(infinito)

        self._sincronizar(q, etiqueta, opciones, rellenar, nuevo)

    @staticmethod
    def _guardar_tags(q, tags):
        anterior = q.find('tags')
        posicion = list(q).index(anterior) if anterior is not None else len(q)
        if anterior is not None:
            q.remove(anterior)
        if tags:
            nuevo = ET.Element('tags')
            for tag in tags:
                ET.SubElement(ET.SubElement(nuevo, 'tag'), 'text').text = tag
            q.insert(posicion, nuevo)

    @staticmethod
    def _write_xml(raiz, filepath):
        # El formateador del proyecto: sangría, <text> en CDATA (el código con < y & queda
        # intacto) y los comentarios (p. ej. la clasificación) conservados.
        from voight.core.formatter import format_xml_content

        xml = format_xml_content(ET.tostring(raiz, encoding='unicode'))
        Path(filepath).write_text(xml, encoding='utf-8')


class GiftQuestionAdapter:
    """Adapta archivos GIFT al mismo contrato de edición que el parser XML.

    Lectura: la primera pregunta del archivo, del modelo unificado a la forma del editor.
    Escritura: reemplaza sólo el bloque de esa pregunta (con sus tags en el comentario que
    la precede) y conserva la categoría, los demás comentarios y las otras preguntas.
    """

    _TIPOS_DE_EDITOR = {v: k for k, v in _TIPOS_A_EDITOR.items()}

    def __init__(self):
        self._parser = GiftParser()

    # -- lectura -----------------------------------------------------------

    def _primera(self, contenido):
        for q in self._parser._manual_parse(contenido):
            if q.type != "Category":
                return q
        raise ValueError("El archivo GIFT no contiene preguntas")

    def parse_question(self, filepath) -> dict:
        q = self._primera(Path(filepath).read_text(encoding='utf-8'))
        tipo = _TIPOS_A_EDITOR.get(q.type, 'description')
        texto = lambda ft: ft.text if ft else ''  # noqa: E731

        data = {
            'type': tipo,
            'answer_mode': MODOS.get(tipo, 'none'),
            'source_format': 'gift',
            'name': q.title or '',
            'questiontext': texto(q.stem),
            'questiontext_format': _FORMATOS_GIFT.get(q.stem.format if q.stem else 'moodle', 'moodle_auto_format'),
            'generalfeedback': texto(q.global_feedback),
            'generalfeedback_format': 'html',
            'defaultgrade': '1',
            'penalty': '0.3333333',
            'hidden': '0',
            'tags': list(q.tags),
            'answers': [],
            'embedded': q.has_embedded_answers,
            'filepath': filepath,
        }

        if q.type in ('MC', 'Short'):
            if q.type == 'MC':
                data['single'] = '0' if sum(1 for c in q.choices if c.is_correct) > 1 else '1'
                data['shuffleanswers'] = '1'
            else:
                data['usecase'] = '0'
            for c in q.choices:
                frac = c.weight if c.weight is not None else (100 if c.is_correct else 0)
                data['answers'].append({'fraction': f"{frac:g}", 'text': texto(c.text), 'feedback': texto(c.feedback)})
        elif q.type == 'TF':
            for valor, es_correcta, fb in (('true', True, q.true_feedback), ('false', False, q.false_feedback)):
                data['answers'].append({
                    'fraction': '100' if q.is_true == es_correcta else '0',
                    'text': valor,
                    'feedback': texto(fb),
                })
        elif q.type == 'Matching':
            data['subquestions'] = [{'text': texto(p.subquestion), 'answer': p.subanswer or ''} for p in q.match_pairs]
        elif q.type == 'Numerical':
            for c in q.choices:
                valor, tolerancia = valor_y_tolerancia(texto(c.text))
                frac = c.weight if c.weight is not None else (100 if c.is_correct else 0)
                data['answers'].append({'fraction': f"{frac:g}", 'text': valor, 'tolerance': tolerancia or '0',
                                        'feedback': texto(c.feedback)})
        return data

    # -- escritura ---------------------------------------------------------

    def save_question(self, filepath, d: dict) -> None:
        """Reescribe la primera pregunta del archivo con los campos editados."""
        tipo = d.get('type', 'multichoice')
        modelo = self._TIPOS_DE_EDITOR.get(tipo)
        if modelo is None:
            raise ValueError(f"GIFT no tiene el tipo '{tipo}'")
        formato = {v: k for k, v in _FORMATOS_GIFT.items()}.get(d.get('questiontext_format'), 'moodle')
        enunciado = d.get('questiontext', '').replace('\r\n', '\n').strip()
        # Palabra faltante: el bloque de respuestas va en el lugar del _____.
        antes, hueco, despues = enunciado.partition('_____') if modelo in ('MC', 'Short') else (enunciado, '', '')

        q = Question(type=modelo, title=d.get('name', '').strip() or None,
                     stem=FormattedText(format=formato, text=antes.rstrip() if hueco else enunciado))
        if d.get('generalfeedback', '').strip():
            q.global_feedback = FormattedText(text=d['generalfeedback'].strip())

        def ft(valor):
            return FormattedText(text=valor.strip()) if valor and valor.strip() else None

        respuestas = d.get('answers', [])
        if modelo in ('MC', 'Short', 'Numerical'):
            for a in respuestas:
                frac = _fraccion(a.get('fraction'))
                if modelo == 'Numerical':
                    tol = str(a.get('tolerance') or '').strip()
                    texto = a.get('text', '').strip() + (f":{tol}" if tol and _fraccion(tol) else '')
                else:
                    texto = a.get('text', '')
                correcta = abs(frac - 100) < 0.01 or (modelo != 'MC' and frac > 0)
                peso = None if abs(frac - 100) < 0.01 or (modelo == 'MC' and frac == 0) else frac
                if modelo == 'Numerical' and frac == 0:
                    correcta, peso = False, None
                q.choices.append(Choice(is_correct=correcta, weight=peso, text=FormattedText(text=texto),
                                        feedback=ft(a.get('feedback', ''))))
        elif modelo == 'TF':
            por_valor = {a.get('text', '').lower(): a for a in respuestas}
            q.is_true = _fraccion(por_valor.get('true', {}).get('fraction')) > 0
            q.true_feedback = ft(por_valor.get('true', {}).get('feedback', ''))
            q.false_feedback = ft(por_valor.get('false', {}).get('feedback', ''))
        elif modelo == 'Matching':
            q.match_pairs = [MatchPair(subquestion=FormattedText(text=p.get('text', '')), subanswer=p.get('answer', ''))
                             for p in d.get('subquestions', [])]

        gift = question_to_gift(q)
        if hueco:
            gift += ' ' + _escape_gift(despues.lstrip(), 'stem')
        gift = _seguro_para_gift(gift)

        contenido = Path(filepath).read_text(encoding='utf-8')
        nuevo = _reemplazar_primera_pregunta(contenido, gift, d.get('tags'))
        Path(filepath).write_text(nuevo, encoding='utf-8')


_TAG = re.compile(r'\s*\[tag:[^\]]+\]')


def _reemplazar_primera_pregunta(contenido: str, gift: str, tags) -> str:
    """Reemplaza el bloque de la primera pregunta (separado como lo hace el parser) y,
    si se pasan `tags`, los [tag:…] del comentario que la precede."""
    lineas = contenido.split('\n')
    inicio = next((i for i, linea in enumerate(lineas)
                   if linea.strip() and not linea.strip().startswith(('//', '$CATEGORY:'))), None)
    if inicio is None:
        prefijo = contenido.rstrip('\n')
        return (prefijo + '\n\n' if prefijo else '') + gift + '\n'

    fin, bloque = inicio, []
    while fin < len(lineas):
        linea = lineas[fin]
        if not linea.strip() and corta_en_blanco('\n'.join(bloque), lineas, fin):
            break
        if linea.strip().startswith('$CATEGORY:'):
            break
        bloque.append(linea)
        fin += 1
    while fin > inicio and not lineas[fin - 1].strip():
        fin -= 1

    comentarios = inicio
    while comentarios > 0 and lineas[comentarios - 1].strip().startswith('//'):
        comentarios -= 1
    previos = lineas[comentarios:inicio]
    if tags is not None:
        previos = [_TAG.sub('', c).rstrip() for c in previos]
        previos = [c for c in previos if c.strip() not in ('//', '')]
        if tags:
            previos.append('// ' + ' '.join(f'[tag:{t}]' for t in tags))

    lineas[comentarios:fin] = previos + gift.split('\n')
    return '\n'.join(lineas).rstrip('\n') + '\n'
