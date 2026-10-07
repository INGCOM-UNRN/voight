import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List
from voight.core.xml_tools import sanitize_filename

def extract_title(question_text: str) -> str:
    """Extrae el título de una pregunta GIFT."""
    title_match = re.search(r'^::(.*?)::', question_text, re.DOTALL)
    if title_match:
        return title_match.group(1).strip()
    return ""

def split_gift_questions(content: str) -> List[str]:
    """Divide el contenido GIFT en preguntas individuales (una línea en blanco corta
    sólo con las llaves balanceadas, como el parser)."""
    from voight.core.formatter import _bloques_gift
    return [p.strip() for p in _bloques_gift(content) if p.strip()]

def _destino_libre(directorio: Path, base: str, sufijo: str, indice: int) -> Path:
    destino = directorio / f"{base}{sufijo}"
    if destino.exists():
        destino = directorio / f"{base}_{indice}{sufijo}"
    return destino


def split_xml_file(file_path: Path, simular: bool = False) -> int:
    """Divide un Moodle XML con varias preguntas en un archivo por pregunta.

    Cada archivo lleva la categoría vigente (la última `<question type="category">`
    anterior) para que al importarlo la pregunta caiga en el mismo lugar.
    """
    from voight.core.formatter import format_xml_content

    raiz = ET.fromstring(file_path.read_text(encoding='utf-8'))
    preguntas = [q for q in raiz.findall('question') if q.get('type') != 'category']
    if len(preguntas) <= 1:
        return 0

    categoria = None
    count = 0
    for i, q in enumerate(raiz.findall('question')):
        if q.get('type') == 'category':
            categoria = q
            continue
        nombre = (q.findtext('name/text') or '').strip()
        base = sanitize_filename(nombre) if nombre else f"{file_path.stem}_{i+1}"
        quiz = ET.Element('quiz')
        if categoria is not None:
            quiz.append(categoria)
        quiz.append(q)
        destino = _destino_libre(file_path.parent, base, '.xml', i + 1)
        if not simular:
            destino.write_text(format_xml_content(ET.tostring(quiz, encoding='unicode')), encoding='utf-8')
        count += 1
    return count


def split_file(file_path: Path, simular: bool = False) -> int:
    """Divide un archivo GIFT o Moodle XML en varios archivos individuales."""
    if file_path.suffix == '.xml':
        return split_xml_file(file_path, simular)
    if not file_path.suffix == '.gift':
        return 0
        
    content = file_path.read_text(encoding='utf-8')
    bloques = split_gift_questions(content)

    # Cada archivo lleva la categoría vigente, como en XML: importada sola, la
    # pregunta cae en el mismo lugar. Los bloques que sólo declaran la categoría (o
    # sólo tienen comentarios) no son preguntas y no generan archivo.
    categoria = None
    preguntas = []
    for bloque in bloques:
        lineas = bloque.splitlines()
        cats = [linea.strip() for linea in lineas if linea.strip().startswith("$CATEGORY")]
        if cats:
            categoria = cats[-1]
        if all(not ln.strip() or ln.strip().startswith(("$CATEGORY", "//")) for ln in lineas):
            continue
        preguntas.append((categoria, bloque))

    if len(preguntas) <= 1:
        return 0

    count = 0
    for i, (cat, q) in enumerate(preguntas):
        title = extract_title(re.sub(r"(?m)^\s*(//|\$CATEGORY).*\n?", "", q))
        base_name = sanitize_filename(title) if title else f"{file_path.stem}_{i+1}"
        new_path = _destino_libre(file_path.parent, base_name, '.gift', i + 1)
        encabezado = f"{cat}\n\n" if cat and "$CATEGORY" not in q else ""
        if not simular:
            new_path.write_text(encabezado + q + "\n", encoding='utf-8')
        count += 1

    return count
