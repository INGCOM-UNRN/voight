import re
import xml.etree.ElementTree as ET

def sanitize_filename(text: str, max_length: int = 100) -> str:
    """Sanitiza un texto para usarlo como nombre de archivo."""
    # Reemplazar caracteres no alfanuméricos por guiones bajos
    s = re.sub(r'[^\w\s-]', '', text).strip()
    s = re.sub(r'[-\s]+', '_', s)
    return s[:max_length].lower()

def ensure_cdata_in_text_blocks(xml_content: str) -> tuple[str, int]:
    """Asegura que todos los bloques <text> tengan su contenido envuelto en CDATA."""
    # Buscar bloques <text> que no tengan CDATA
    # <text>contenido</text> -> <text><![CDATA[contenido]]></text>
    count = 0
    def replace_text(match):
        nonlocal count
        start_tag = match.group(1)
        content = match.group(2)
        end_tag = match.group(3)
        
        if content.strip() and not content.strip().startswith('<![CDATA['):
            count += 1
            return f"{start_tag}<![CDATA[{content}]]>{end_tag}"
        return match.group(0)

    # Regex para capturar <text>...</text> considerando atributos
    # `(?<!/)>` excluye `<text/>`: sin eso el contenido se extendería hasta el próximo </text>.
    pattern = r'(<text\b[^>]*(?<!/)>)(.*?)(</text>)'
    new_content = re.sub(pattern, replace_text, xml_content, flags=re.DOTALL)
    return new_content, count

def remove_tags_from_xml(root: ET.Element) -> int:
    """Elimina las secciones <tags> de todas las preguntas."""
    count = 0
    for question in root.findall('.//question'):
        tags = question.find('tags')
        if tags is not None:
            question.remove(tags)
            count += 1
    return count
