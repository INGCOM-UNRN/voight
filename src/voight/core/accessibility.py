"""Auditor de accesibilidad en imágenes embebidas de preguntas Moodle."""

from __future__ import annotations

import re
from typing import Dict, Any


def validar_accesibilidad_imagenes(contenido_html: str) -> Dict[str, Any]:
    """Verifica que todas las etiquetas <img> contengan texto descriptivo alt."""
    imgs = re.findall(r"<img\b([^>]*)>", contenido_html, re.IGNORECASE)
    total_imgs = len(imgs)
    imgs_sin_alt = 0
    
    for tag_attrs in imgs:
        alt_match = re.search(r'\balt=["\x27]([^"\x27]*)["\x27]', tag_attrs, re.IGNORECASE)
        if not alt_match or not alt_match.group(1).strip():
            imgs_sin_alt += 1

    return {
        "total_imagenes": total_imgs,
        "imagenes_sin_alt": imgs_sin_alt,
        "accesible": imgs_sin_alt == 0,
        "porcentaje_conformidad": 100.0 if total_imgs == 0 else round(((total_imgs - imgs_sin_alt) / total_imgs) * 100, 1),
    }
