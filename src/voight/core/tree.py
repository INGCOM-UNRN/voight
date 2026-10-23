"""Export/collect de bancos GIFT y Moodle XML hacia árboles de directorios.

Absorbe la funcionalidad de moodle-reorganizer sobre un diseño propio:
un banco monolítico se exporta a un árbol `<categoría>/<pregunta>.<ext>`
(1 archivo por pregunta) y puede recolectarse nuevamente a un archivo único,
preservando categorías ($CATEGORY / type="category"), escapes de GIFT y
bloques CDATA del XML.
"""

import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from voight.core.converter import _cdata_sub, _serializar_quiz
from voight.core.incrustar import incrustar_pregunta
from voight.core.xml_tools import sanitize_filename


def sanitize_dirname(part: str) -> str:
    """Sanitiza un segmento de ruta de categoría preservando las mayúsculas."""
    s = re.sub(r'[^\w\s-]', '', part.strip()).strip()
    s = re.sub(r'[-\s]+', '_', s)
    return s[:60]


# ---------------------------------------------------------------------------
# Utilidades GIFT
# ---------------------------------------------------------------------------

def _protect_backslashes_in_code(text: str) -> str:
    r"""Reemplaza las barras (\) del código GIFT por ＼, respetando los escapes de GIFT:
    `\\` es una sola barra (→ ＼), `\{`, `\=`… son símbolos ya protegidos (quedan) y una
    barra cruda (`\n`, `\0`) se vuelve ＼."""

    def barra(m):
        siguiente = m.group(1)
        if siguiente == '\\':
            return '＼'
        if siguiente and siguiente in '{}=#~:':
            return m.group(0)
        return '＼' + siguiente

    def en_bloque(match):
        return re.sub(r'\\([\s\S]?)', barra, match.group(0))

    text = re.sub(r'```[^`]*```', en_bloque, text, flags=re.DOTALL)
    text = re.sub(r'(?<!`)(`[^`\n]+`)(?!`)', en_bloque, text)
    return text


def gift_export(input_file: Path, base_output_dir: Path) -> int:
    """Exporta un banco GIFT monolítico a un árbol de directorios."""
    print(f"Exportando GIFT desde: {input_file}")
    contenido = input_file.read_text(encoding='utf-8')

    # División por bloques como el parser: una línea en blanco sólo corta con las llaves
    # balanceadas (el código con líneas en blanco queda en su pregunta). Cada bloque
    # puede contener $CATEGORY y/o una pregunta.
    from voight.core.formatter import _bloques_gift

    bloques = [b.strip() for b in _bloques_gift(contenido) if b.strip()]

    current_category = ''
    question_count = 0
    used_filenames: dict[str, int] = {}

    from voight.core.formatter import format_gift_content
    from voight.core.parser import parse_gift

    for bloque in bloques:
        lineas = bloque.split('\n')
        declaradas = [linea for linea in lineas if linea.strip().startswith('$CATEGORY:')]
        if declaradas:
            categoria = declaradas[-1].strip()[len('$CATEGORY:'):].strip()
            partes = [sanitize_dirname(p) for p in categoria.split('/')
                      if p.strip() and p != '$course$']
            current_category = '/'.join(partes)
        # La pregunta, con sus comentarios (tags, id, clasificación), sin la $CATEGORY.
        cuerpo = '\n'.join(linea for linea in lineas if not linea.strip().startswith('$CATEGORY:')).strip()
        preguntas = [q for q in parse_gift(cuerpo)['questions'] if q['type'] != 'Category'] if cuerpo else []
        if not preguntas:
            continue  # sólo comentarios o la declaración de una categoría

        formatted = format_gift_content(cuerpo).rstrip('\n') + '\n'
        # El título lo da el parser: un comentario como `// CAT: Algo::` no lo confunde.
        titulo_completo = (preguntas[0].get('title') or '').strip() or 'sin título'

        categoria_del_titulo = ''
        titulo_real = titulo_completo
        if '/' in titulo_completo:
            partes_titulo = titulo_completo.split('/')
            if len(partes_titulo) > 1:
                titulo_real = partes_titulo[-1]
                categoria_del_titulo = '/'.join(
                    sanitize_dirname(p) for p in partes_titulo[:-1])

        categoria_final = categoria_del_titulo or current_category
        base_name = sanitize_filename(titulo_real)

        output_dir = base_output_dir / categoria_final if categoria_final else base_output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        if base_name in used_filenames:
            used_filenames[base_name] += 1
            filename = f"{base_name}_{used_filenames[base_name]}.gift"
        else:
            used_filenames[base_name] = 0
            filename = f"{base_name}.gift"

        destino = output_dir / filename
        destino.write_text(formatted, encoding='utf-8')
        print(f"  Creado: {destino.relative_to(base_output_dir)}")
        question_count += 1

    print(f"\n✓ Exportación completada: {question_count} preguntas")
    return question_count


def gift_collect(base_input_dir: Path, output_file: Path) -> int:
    """Recolecta un árbol de preguntas GIFT en un archivo monolítico."""
    print(f"Recolectando GIFT desde: {base_input_dir}")

    gift_files = sorted(
        (str(p.relative_to(base_input_dir)), p)
        for p in base_input_dir.rglob('*.gift') if p.is_file()
    )

    if not gift_files:
        print("No se encontraron archivos .gift en el directorio indicado.")
        return 0

    question_count = 0
    current_category = None
    lineas_salida = []

    for rel_path, filepath in gift_files:
        dir_path = str(Path(rel_path).parent)
        dir_path = '' if dir_path == '.' else dir_path.replace(os.sep, '/')

        if dir_path != current_category:
            current_category = dir_path
            if dir_path:
                lineas_salida.append(f"\n$CATEGORY: $course$/{dir_path}\n")
            else:
                lineas_salida.append("\n$CATEGORY: $course$\n")

        content = filepath.read_text(encoding='utf-8')
        content = _protect_backslashes_in_code(content)

        lineas_salida.append(f"// {rel_path}")
        lineas_salida.append(content.strip() + '\n')
        question_count += 1
        print(f"  Agregada: {rel_path}")

    output_file.write_text('\n'.join(lineas_salida), encoding='utf-8')
    print(f"\n✓ Colección completada: {question_count} preguntas en {output_file}")
    return question_count


# ---------------------------------------------------------------------------
# Moodle XML
# ---------------------------------------------------------------------------

# Un único serializador para todo el paquete (ver converter._serializar_quiz).
serializar_quiz = _serializar_quiz


def _quiz_de_pregunta(question: ET.Element) -> ET.Element:
    quiz = ET.Element('quiz')
    quiz.append(question)
    return quiz


def xml_export(input_file: Path, base_output_dir: Path) -> int:
    """Exporta un banco Moodle XML monolítico a un árbol de directorios."""
    print(f"Exportando Moodle XML desde: {input_file}")

    try:
        root = ET.fromstring(input_file.read_text(encoding='utf-8'))
    except (ET.ParseError, UnicodeDecodeError) as e:
        print(f"Error: no se pudo interpretar el XML: {e}", file=sys.stderr)
        return -1

    current_category = ''
    question_count = 0
    used_filenames: dict[str, int] = {}

    for question in root.findall('question'):
        qtype = question.get('type')

        if qtype == 'category':
            texto = question.find('category/text')
            if texto is not None and texto.text:
                partes = [sanitize_dirname(p) for p in texto.text.split('/')
                          if p.strip() and p != '$course$']
                current_category = '/'.join(partes)
            continue

        nombre = question.find('name/text')
        if nombre is None or not nombre.text:
            continue

        base_name = sanitize_filename(nombre.text.strip())

        output_dir = base_output_dir / current_category if current_category else base_output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        if base_name in used_filenames:
            used_filenames[base_name] += 1
            filename = f"{base_name}_{used_filenames[base_name]}.xml"
        else:
            used_filenames[base_name] = 0
            filename = f"{base_name}.xml"

        destino = output_dir / filename
        destino.write_text(serializar_quiz(_quiz_de_pregunta(question)), encoding='utf-8')
        print(f"  Creado: {destino.relative_to(base_output_dir)}")
        question_count += 1

    print(f"\n✓ Exportación completada: {question_count} preguntas")
    return question_count


def xml_collect(base_input_dir: Path, output_file: Path, incrustar: bool = True,
                formato_diagrama: str = 'png') -> int:
    """Recolecta un árbol de preguntas Moodle XML en un archivo monolítico.

    Con `incrustar`, los diagramas mermaid y las imágenes relativas se adjuntan a la
    salida (ver `incrustar.py`); los archivos del árbol no cambian.
    """
    print(f"Recolectando Moodle XML desde: {base_input_dir}")

    xml_files = sorted(
        (str(p.relative_to(base_input_dir)), p)
        for p in base_input_dir.rglob('*.xml')
        if p.is_file() and not p.name.startswith('.')
    )

    if not xml_files:
        print("No se encontraron archivos .xml en el directorio indicado.")
        return 0

    quiz_root = ET.Element('quiz')
    current_category = None
    question_count = 0

    for rel_path, filepath in xml_files:
        dir_path = str(Path(rel_path).parent)
        dir_path = '' if dir_path == '.' else dir_path.replace(os.sep, '/')

        if dir_path != current_category:
            current_category = dir_path
            cat_q = ET.SubElement(quiz_root, 'question', {'type': 'category'})
            cat = _cdata_sub(cat_q, 'category')
            ruta = f"$course$/{dir_path}" if dir_path else "$course$"
            _cdata_sub(cat, "text", ruta)

        try:
            tree = ET.parse(filepath)
            for question in tree.getroot().findall('question'):
                if question.get('type') == 'category':
                    continue
                if incrustar:
                    incrustar_pregunta(question, filepath.parent, formato_diagrama)
                quiz_root.append(question)
                question_count += 1
                print(f"  Agregada: {rel_path}")
        except (ET.ParseError, UnicodeDecodeError) as e:
            print(f"  Error interpretando {filepath}: {e}", file=sys.stderr)

    output_file.write_text(serializar_quiz(quiz_root), encoding='utf-8')
    print(f"\n✓ Colección completada: {question_count} preguntas en {output_file}")
    return question_count


# ---------------------------------------------------------------------------
# Punto de entrada unificado por formato
# ---------------------------------------------------------------------------

def exportar(archivo: Path, dir_destino: Path, formato: str | None = None) -> int:
    """Exporta un banco a un árbol de directorios según su formato."""
    formato = (formato or ('gift' if archivo.suffix.lower() == '.gift' else 'xml')).lower()
    dir_destino.mkdir(parents=True, exist_ok=True)
    if formato == 'gift':
        return gift_export(archivo, dir_destino)
    if formato == 'xml':
        return xml_export(archivo, dir_destino)
    raise ValueError(f"Formato desconocido: {formato}")


def recolectar(directorio: Path, archivo_destino: Path, formato: str | None = None,
               incrustar: bool = True, formato_diagrama: str = 'png') -> int:
    """Recolecta un árbol de directorios en un banco según el formato.

    `incrustar` y `formato_diagrama` sólo aplican a Moodle XML (GIFT no lleva archivos).
    """
    formato = (formato or ('gift' if archivo_destino.suffix.lower() == '.gift' else 'xml')).lower()
    if formato == 'gift':
        return gift_collect(directorio, archivo_destino)
    if formato == 'xml':
        return xml_collect(directorio, archivo_destino, incrustar, formato_diagrama)
    raise ValueError(f"Formato desconocido: {formato}")
