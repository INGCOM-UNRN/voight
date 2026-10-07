import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

def slugify(text: str) -> str:
    """Convierte un texto en un slug (minúsculas, sin caracteres especiales, guiones bajos)."""
    # Eliminar acentos y caracteres especiales básicos
    import unicodedata
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    # Reemplazar caracteres no alfanuméricos por guiones bajos
    s = re.sub(r'[^\w\s-]', '', text).strip()
    s = re.sub(r'[-\s]+', '_', s)
    return s.lower()

def get_question_title(file_path: Path) -> Optional[str]:
    """Extrae el título de una pregunta GIFT o XML."""
    if file_path.suffix == '.gift':
        content = file_path.read_text(encoding='utf-8')
        title_match = re.search(r'^::(.*?)::', content, re.DOTALL)
        if title_match:
            return title_match.group(1).strip()
    elif file_path.suffix == '.xml':
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            # Buscar en la estructura típica de Moodle XML
            name_elem = root.find('.//question/name/text')
            if name_elem is not None and name_elem.text:
                return name_elem.text.strip()
        except Exception:
            pass
    return None

def set_question_title(file_path: Path, new_title: str, simular: bool = False) -> bool:
    """Actualiza el título interno de una pregunta GIFT o XML."""
    if file_path.suffix == '.gift':
        content = file_path.read_text(encoding='utf-8')
        # Si ya tiene título, reemplazarlo
        if re.search(r'^::(.*?)::', content, re.DOTALL):
            new_content = re.sub(r'^::(.*?)::', f'::{new_title}::', content, count=1, flags=re.DOTALL)
        else:
            # Si no tiene, añadirlo al inicio
            new_content = f"::{new_title}::\n{content}"
        
        if content != new_content:
            if not simular:
                file_path.write_text(new_content, encoding='utf-8')
            return True
            
    elif file_path.suffix == '.xml':
        try:
            # Para XML es más seguro usar regex si queremos preservar CDATA y formato exacto,
            # pero intentaremos con ElementTree primero y si falla o ensucia, fallback.
            # Moodle XML suele tener <name><text>Titulo</text></name>
            content = file_path.read_text(encoding='utf-8')
            
            # Intentar con regex para mayor fidelidad de formato
            pattern = r'(<name>\s*<text[^>]*>)(.*?)(</text>\s*</name>)'
            match = re.search(pattern, content, re.DOTALL)
            if match:
                # Ver si el contenido tiene CDATA
                inner_content = match.group(2)
                if '<![CDATA[' in inner_content:
                    replacement = f'<![CDATA[{new_title}]]>'
                else:
                    replacement = new_title
                
                new_content = re.sub(pattern, rf'\1{replacement}\3', content, count=1, flags=re.DOTALL)
                if content != new_content:
                    if not simular:
                        file_path.write_text(new_content, encoding='utf-8')
                    return True
        except Exception:
            pass
    return False

def rename_to_slug(file_path: Path, simular: bool = False) -> Optional[Path]:
    """Renombra el archivo a su versión slugificada."""
    new_name = slugify(file_path.stem) + file_path.suffix
    new_path = file_path.parent / new_name
    if file_path != new_path:
        # Manejar colisiones
        counter = 1
        while new_path.exists():
            new_name = f"{slugify(file_path.stem)}_{counter}{file_path.suffix}"
            new_path = file_path.parent / new_name
            counter += 1
        if not simular:
            file_path.rename(new_path)
        return new_path
    return None

def rename_from_title(file_path: Path, simular: bool = False) -> Optional[Path]:
    """Renombra el archivo basándose en el título de la pregunta."""
    title = get_question_title(file_path)
    if title:
        new_name = slugify(title) + file_path.suffix
        new_path = file_path.parent / new_name
        if file_path != new_path:
            counter = 1
            while new_path.exists():
                new_name = f"{slugify(title)}_{counter}{file_path.suffix}"
                new_path = file_path.parent / new_name
                counter += 1
            if not simular:
                file_path.rename(new_path)
            return new_path
    return None
