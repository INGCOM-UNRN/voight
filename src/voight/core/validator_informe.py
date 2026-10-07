"""Generación del informe de texto y de la salida JSON del analizador de bancos (GIFT / XML)."""

from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from voight.core.validator import GiftStats


class InformeMixin:
    # Atributos que define AnalizadorBanco (el mixin no se usa solo).
    stats: "GiftStats"
    issues: list
    all_questions: list
    duplicates: list
    descriptions: list
    similarity_threshold: float

    def generate_report(self, output_file: Optional[str] = None) -> str:
        """Generate the analysis report."""
        lines = []
        
        lines.append("=" * 80)
        lines.append("INFORME DE EVALUACIÓN DE PREGUNTAS (GIFT / MOODLE XML)")
        lines.append("=" * 80)
        lines.append("")
        
        # General summary
        lines.append("📊 RESUMEN GENERAL")
        lines.append("-" * 80)
        lines.append(f"Total de archivos: {self.stats.total_files}")
        for formato, count in sorted(self.stats.by_format.items()):
            lines.append(f"  {formato.upper():4s}: {count} archivos, {self.stats.questions_by_format.get(formato, 0)} preguntas")
        lines.append(f"  ✅ Archivos válidos: {self.stats.valid_files}")
        lines.append(f"  ❌ Archivos inválidos: {self.stats.invalid_files}")
        lines.append(f"Total de preguntas: {self.stats.total_questions}")
        lines.append("")
        
        # Question types
        lines.append("📝 TIPOS DE PREGUNTAS")
        lines.append("-" * 80)
        if self.stats.by_type:
            for q_type, count in self.stats.by_type.most_common():
                percentage = (count / self.stats.total_questions * 100) if self.stats.total_questions > 0 else 0
                lines.append(f"  {q_type:20s}: {count:5d} ({percentage:5.1f}%)")
        else:
            lines.append("  No hay preguntas")
        lines.append("")
        
        # Categories
        lines.append("📂 CATEGORÍAS")
        lines.append("-" * 80)
        if self.stats.by_category:
            for category, count in self.stats.by_category.most_common():
                lines.append(f"  {category[:60]:60s}: {count:4d}")
        else:
            lines.append("  No se encontraron categorías")
        lines.append("")
        
        # Tags
        lines.append("🏷️  TAGS MÁS COMUNES")
        lines.append("-" * 80)
        if self.stats.by_tag:
            for tag, count in self.stats.by_tag.most_common():
                lines.append(f"  {tag:30s}: {count:4d}")
        else:
            lines.append("  No se encontraron tags")
        lines.append("")
        
        # Content quality
        lines.append("✨ CALIDAD DE CONTENIDO")
        lines.append("-" * 80)
        lines.append(f"Preguntas con tags: {self.stats.with_tags}")
        lines.append(f"Preguntas sin tags: {self.stats.without_tags}")
        lines.append(f"Preguntas con feedback global: {self.stats.with_feedback}")
        lines.append(f"Preguntas sin feedback global: {self.stats.without_feedback}")
        lines.append(f"Preguntas vacías: {self.stats.empty_questions}")
        lines.append("")
        
        # Distribution by depth
        lines.append("📁 DISTRIBUCIÓN POR PROFUNDIDAD DE DIRECTORIOS")
        lines.append("-" * 80)
        if self.stats.files_by_depth:
            for depth in sorted(self.stats.files_by_depth.keys()):
                count = self.stats.files_by_depth[depth]
                lines.append(f"  Nivel {depth}: {count} archivos")
        lines.append("")
        
        # Detected issues
        if self.issues:
            lines.append("⚠️  PROBLEMAS DETECTADOS")
            lines.append("-" * 80)
            lines.append(f"Total de problemas: {len(self.issues)}")
            lines.append("")
            for issue in self.issues:
                lines.append(f"  {issue}")
            lines.append("")
        
        # Parse errors
        if self.stats.parse_errors:
            lines.append("❌ ERRORES DE PARSEO")
            lines.append("-" * 80)
            for error_info in self.stats.parse_errors:
                lines.append(f"  {error_info['filepath']}")
                lines.append(f"    Error: {error_info['error']['message']}")
            lines.append("")
        
        # Description questions (possible issues)
        if self.descriptions:
            lines.append("📄 PREGUNTAS TIPO DESCRIPTION (posibles problemas)")
            lines.append("-" * 80)
            lines.append(f"Total: {len(self.descriptions)}")
            lines.append("Nota: Las preguntas tipo 'Description' no tienen respuestas.")
            lines.append("      Esto puede indicar un error en el formato de la pregunta.")
            lines.append("")
            for desc in self.descriptions:
                lines.append(f"  📄 {desc['filepath']}")
                lines.append(f"     Título: {desc['title']}")
                if desc['text'] and desc['text'] != "<sin texto>":
                    text_preview = desc['text'].replace('\n', ' ')[:80]
                    lines.append(f"     Texto: {text_preview}...")
                lines.append("")
        
        # Duplicates
        if self.duplicates:
            lines.append("🔄 PREGUNTAS DUPLICADAS O MUY SIMILARES")
            lines.append("-" * 80)
            lines.append(f"Total de duplicados encontrados: {len(self.duplicates)}")
            lines.append(f"Threshold de similitud: {self.similarity_threshold}")
            lines.append("")
            
            for idx, dup in enumerate(self.duplicates, 1):
                q1 = self.all_questions[dup["index1"]]
                q2 = self.all_questions[dup["index2"]]
                
                lines.append(f"Duplicado {idx}: Similitud = {dup['similarity']:.3f}")
                lines.append(f"  Pregunta A ({q1['type']}, {q1.get('format', 'gift')}): {q1['title'][:70]}")
                lines.append(f"    Archivo: {q1['filepath']}")
                lines.append(f"  Pregunta B ({q2['type']}, {q2.get('format', 'gift')}): {q2['title'][:70]}")
                lines.append(f"    Archivo: {q2['filepath']}")
                lines.append(f"  Comando: meld -n '{q1['filepath']}' '{q2['filepath']}'")
                lines.append("")
        
        # Recommendations
        lines.append("💡 RECOMENDACIONES")
        lines.append("-" * 80)
        
        if self.stats.without_tags > 0:
            percentage = (self.stats.without_tags / self.stats.total_questions * 100) if self.stats.total_questions > 0 else 0
            lines.append(f"  • {percentage:.1f}% de preguntas sin tags - considera añadir tags para mejor organización")
        
        if self.stats.without_feedback > 0:
            percentage = (self.stats.without_feedback / self.stats.total_questions * 100) if self.stats.total_questions > 0 else 0
            lines.append(f"  • {percentage:.1f}% de preguntas sin feedback global - el feedback ayuda al aprendizaje")
        
        if self.stats.empty_questions > 0:
            lines.append(f"  • {self.stats.empty_questions} preguntas vacías detectadas - requieren revisión")
        
        if self.stats.invalid_files > 0:
            lines.append(f"  • {self.stats.invalid_files} archivos con errores - necesitan corrección")
        
        if self.duplicates:
            lines.append(f"  • {len(self.duplicates)} preguntas duplicadas detectadas - considera revisar para eliminar redundancias")
        
        if not self.issues and not self.stats.parse_errors and not self.duplicates:
            lines.append("  • ¡Todo se ve bien! No se detectaron problemas significativos")
        
        lines.append("")
        lines.append("=" * 80)
        
        report = "\n".join(lines)
        
        if output_file:
            Path(output_file).write_text(report, encoding='utf-8')
            print(f"\n✅ Informe guardado en: {output_file}")
        
        return report
    
    def to_json(self) -> dict:
        """Convert analysis results to JSON-serializable dict."""
        return {
            "stats": {
                "totalFiles": self.stats.total_files,
                "byFormat": dict(self.stats.by_format),
                "questionsByFormat": dict(self.stats.questions_by_format),
                "validFiles": self.stats.valid_files,
                "invalidFiles": self.stats.invalid_files,
                "totalQuestions": self.stats.total_questions,
                "byType": dict(self.stats.by_type),
                "byCategory": dict(self.stats.by_category),
                "withTags": self.stats.with_tags,
                "withoutTags": self.stats.without_tags,
                "byTag": dict(self.stats.by_tag),
                "withFeedback": self.stats.with_feedback,
                "withoutFeedback": self.stats.without_feedback,
                "emptyQuestions": self.stats.empty_questions,
                "parseErrors": self.stats.parse_errors,
                "filesByDepth": dict(self.stats.files_by_depth)
            },
            "issues": self.issues,
            "duplicates": [
                {
                    "similarity": d["similarity"],
                    "question1": {
                        "filepath": self.all_questions[d["index1"]]["filepath"],
                        "title": self.all_questions[d["index1"]]["title"],
                        "type": self.all_questions[d["index1"]]["type"],
                        "format": self.all_questions[d["index1"]].get("format", "gift"),
                    },
                    "question2": {
                        "filepath": self.all_questions[d["index2"]]["filepath"],
                        "title": self.all_questions[d["index2"]]["title"],
                        "type": self.all_questions[d["index2"]]["type"],
                        "format": self.all_questions[d["index2"]].get("format", "gift"),
                    }
                }
                for d in self.duplicates
            ],
            "descriptions": self.descriptions
        }
