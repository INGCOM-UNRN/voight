"""Exportador de catálogo estructurado de preguntas a Markdown."""

from __future__ import annotations

from typing import List, Dict, Any


def exportar_catalogo_markdown(preguntas: List[Dict[str, Any]], titulo: str = "Catálogo de Preguntas") -> str:
    """Genera una guía de lectura rápida en Markdown con el catálogo de preguntas."""
    lineas = [f"# 📚 {titulo}\n", f"**Total de reactivos:** {len(preguntas)}\n"]
    
    for i, p in enumerate(preguntas, 1):
        nombre = p.get("name", f"Reactivo {i}")
        tipo = p.get("type", "multichoice")
        enunciado = p.get("text", "").strip()
        lineas.append(f"### {i}. {nombre} (`{tipo}`)")
        lineas.append(f"{enunciado}\n")
        
        opciones = p.get("options", [])
        if opciones:
            lineas.append("**Opciones:**")
            for opt in opciones:
                peso = opt.get("fraction", 0)
                txt = opt.get("text", "")
                badge = "✓" if float(peso) > 0 else "✗"
                lineas.append(f"- [{badge}] {txt} ({peso}%)")
            lineas.append("")
        lineas.append("---")

    return "\n".join(lineas)
