#!/usr/bin/env python3
"""
Herramienta para verificar recursivamente un directorio de preguntas GIFT y Moodle XML.
Genera un informe detallado con estadísticas, problemas detectados y recomendaciones.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path


from voight.core.banco import EXTENSIONES, buscar_archivos, parse_archivo
from voight.core.validator_informe import InformeMixin
from voight.core.validator_similitud import SimilitudMixin


@dataclass
class GiftStats:
    """Statistics for GIFT / Moodle XML analysis."""
    total_files: int = 0
    by_format: Counter = field(default_factory=Counter)
    questions_by_format: Counter = field(default_factory=Counter)
    valid_files: int = 0
    invalid_files: int = 0
    total_questions: int = 0
    by_type: Counter = field(default_factory=Counter)
    by_category: Counter = field(default_factory=Counter)
    with_tags: int = 0
    without_tags: int = 0
    by_tag: Counter = field(default_factory=Counter)
    with_feedback: int = 0
    without_feedback: int = 0
    empty_questions: int = 0
    parse_errors: list = field(default_factory=list)
    files_by_depth: Counter = field(default_factory=Counter)


class AnalizadorBanco(SimilitudMixin, InformeMixin):
    """Analizador de un banco de preguntas (GIFT y Moodle XML): validez, estadísticas y similitud."""
    
    def __init__(self, similarity_threshold: float = 0.85, recursive: bool = True, verbose: bool = False,
                 extensions: tuple = EXTENSIONES):
        self.similarity_threshold = similarity_threshold
        self.recursive = recursive
        self.verbose = verbose
        self.extensions = extensions
        
        self.stats = GiftStats()
        self.categories: dict = defaultdict(list)
        self.issues: list = []
        self.all_questions: list = []
        self.duplicates: list = []
        self.descriptions: list = []  # Preguntas tipo Description (posibles problemas)
        self.base_path: Path = Path('.')
    
    def find_question_files(self, directory: Path) -> list:
        """Find all question files (.gift / .xml) in directory."""
        return buscar_archivos(directory, self.recursive, self.extensions)

    find_gift_files = find_question_files
    
    def analyze_file(self, filepath: Path):
        """Analyze a single GIFT or Moodle XML file."""
        self.stats.total_files += 1
        
        # Calculate depth
        try:
            rel_path = filepath.relative_to(self.base_path)
            depth = len(rel_path.parts) - 1
        except ValueError:
            depth = 0
        self.stats.files_by_depth[depth] += 1
        
        result = parse_archivo(filepath)
        self.stats.by_format[result["formato"]] += 1
        
        if not result["success"]:
            self.stats.invalid_files += 1
            self.stats.parse_errors.append({
                "filepath": str(filepath),
                "error": result["error"]
            })
            self.issues.append(f"❌ {filepath}: Error de parseo - {result['error']['message']}")
            if result["error"].get("location"):
                loc = result["error"]["location"]
                self.issues.append(f"   Línea: {loc.get('line', '?')}, Columna: {loc.get('column', '?')}")
            return
        
        self.stats.valid_files += 1
        
        if not result["questions"]:
            self.issues.append(f"⚠️  {filepath}: No contiene preguntas")
        
        for question in result["questions"]:
            self.analyze_question(question, filepath, result["formato"])
    
    def analyze_question(self, question: dict, filepath: Path, formato: str = "gift"):
        """Analyze a single question."""
        q_type = question.get("type", "Unknown")
        if q_type != "Category":
            self.stats.questions_by_format[formato] += 1
        
        # Handle categories
        if q_type == "Category":
            category = question.get("title", "Sin categoría")
            self.stats.by_category[category] += 1
            self.categories[category].append(str(filepath))
            return
        
        # Handle descriptions. En GIFT, una pregunta sin bloque de respuestas cae como
        # Description y suele ser un error de formato; en XML el tipo es explícito.
        if q_type == "Description":
            self.stats.total_questions += 1
            self.stats.by_type[q_type] += 1
            if formato != "gift":
                return
            title = question.get("title", "")
            stem = question.get("stem", {})
            stem_text = stem.get("text", "") if isinstance(stem, dict) else ""
            self.descriptions.append({
                "filepath": str(filepath),
                "title": title or "<sin título>",
                "text": stem_text[:100] if stem_text else "<sin texto>"
            })
            return
        
        self.stats.total_questions += 1
        self.stats.by_type[q_type] += 1
        
        # Analyze title and content
        title = question.get("title", "")
        stem = question.get("stem", {})
        stem_text = stem.get("text", "") if isinstance(stem, dict) else ""
        
        if not title and not stem_text:
            self.stats.empty_questions += 1
            self.issues.append(f"⚠️  {filepath}: Pregunta sin título ni texto")
        
        # Analyze feedback
        if question.get("globalFeedback"):
            self.stats.with_feedback += 1
        else:
            self.stats.without_feedback += 1
        
        # Analyze tags
        tags = question.get("tags", [])
        if tags:
            self.stats.with_tags += 1
            for tag in tags:
                self.stats.by_tag[tag] += 1
        else:
            self.stats.without_tags += 1
        
        # Type-specific validations
        self._validate_by_type(question, filepath)
        
        # Store for duplicate analysis
        answer_texts = self._extract_answer_texts(question)
        self.all_questions.append({
            "filepath": str(filepath),
            "format": formato,
            "type": q_type,
            "title": title,
            "text": stem_text,
            "answers": answer_texts,
            "full_text": f"{title} {stem_text} {' '.join(answer_texts)}"
        })
    
    def _extract_answer_texts(self, question: dict) -> list:
        """Extract answer texts from question."""
        texts = []
        
        for choice in question.get("choices", []):
            text = choice.get("text", {})
            if isinstance(text, dict):
                texts.append(text.get("text", ""))
            elif isinstance(text, str):
                texts.append(text)
        
        for pair in question.get("matchPairs", []):
            subq = pair.get("subquestion", {})
            if isinstance(subq, dict):
                texts.append(subq.get("text", ""))
            texts.append(pair.get("subanswer", ""))
        
        return texts
    
    def _validate_by_type(self, question: dict, filepath: Path):
        """Type-specific validations."""
        title = question.get("title", "<sin título>")[:50]
        q_type = question.get("type")
        
        if q_type == "MC":
            choices = question.get("choices", [])
            correct_count = sum(1 for c in choices if c.get("is_correct"))
            total_weight = sum(
                c.get("weight", 100 if c.get("is_correct") else 0)
                for c in choices
                if c.get("is_correct") or (c.get("weight") and c.get("weight") > 0)
            )
            
            if correct_count == 0 and total_weight < 95:
                self.issues.append(f"⚠️  {filepath}: Pregunta MC sin respuesta correcta - {title}")
        
        elif q_type == "Matching":
            pairs = question.get("matchPairs", [])
            if len(pairs) < 2:
                self.issues.append(f"⚠️  {filepath}: Pregunta Matching con menos de 2 pares - {title}")
        
        elif q_type == "Short":
            choices = question.get("choices", [])
            if not choices:
                self.issues.append(f"⚠️  {filepath}: Pregunta Short sin respuestas - {title}")

    def scan_directory(self, directory: str):
        """Scan a directory for question files (.gift / .xml)."""
        self.base_path = Path(directory)
        
        files = self.find_question_files(self.base_path)
        
        if not files:
            print(f"⚠️  No se encontraron archivos de preguntas ({', '.join(self.extensions)}) en {directory}")
            return
        
        print(f"Escaneando {len(files)} archivos de preguntas...")
        
        for i, filepath in enumerate(files, 1):
            if self.verbose and i % 10 == 0:
                print(f"  Procesados {i}/{len(files)} archivos...")
            self.analyze_file(filepath)
        
        self.find_duplicates()


# Nombre anterior (analiza GIFT y Moodle XML); se conserva por compatibilidad.
GiftAnalyzer = AnalizadorBanco
