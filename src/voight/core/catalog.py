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
        if p.get("category"):
            lineas.append(f"**Categoría:** {p['category']}\n")
        if p.get("source"):
            lineas.append(f"**Origen:** `{p['source']}`\n")
        
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


def para_catalogo(pregunta: dict) -> dict:
    """Adapta el modelo GIFT/XML al catálogo docente sin modificarlo ni perder la referencia."""
    opciones = []
    for opcion in pregunta.get("choices", []):
        texto = (opcion.get("text") or {}).get("text", "")
        if not texto and opcion.get("numericalAnswer"):
            import json
            texto = json.dumps(opcion["numericalAnswer"], ensure_ascii=False)
        peso = opcion.get("weight")
        opciones.append({"text": texto, "fraction": peso if peso is not None
                         else (100 if opcion.get("is_correct") else 0)})
    if pregunta.get("type") == "TF":
        opciones = [{"text": "Verdadero", "fraction": 100 if pregunta.get("isTrue") else 0},
                    {"text": "Falso", "fraction": 0 if pregunta.get("isTrue") else 100}]
    for par in pregunta.get("matchPairs", []):
        opciones.append({"text": f"{(par.get('subquestion') or {}).get('text', '')} → {par.get('subanswer', '')}",
                         "fraction": 100})
    return {"name": pregunta.get("title") or "Sin título", "type": pregunta.get("type"),
            "text": (pregunta.get("stem") or {}).get("text", ""), "options": opciones,
            "category": pregunta["categoria"],
            "source": f"{pregunta['archivo']} (pregunta {pregunta['indice']})"}
