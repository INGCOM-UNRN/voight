"""Modelo de datos GIFT: tipos de pregunta y estructuras."""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional

from enum import Enum

# Versión del contrato de datos GIFT que consumen otras herramientas (scorm-tools
# `from-gift`). Subir la mayor si cambia la forma del dict de `parse_gift`.
GIFT_CONTRACT_VERSION = "1.1.0"  # 1.0.1: retro de V/F en el orden de Moodle; 1.1.0: claves metadata y moodle


class QuestionType(Enum):
    CATEGORY = "Category"
    DESCRIPTION = "Description"
    MC = "MC"
    TF = "TF"
    SHORT = "Short"
    MATCHING = "Matching"
    NUMERICAL = "Numerical"
    ESSAY = "Essay"
    CLOZE = "Cloze"  # sólo desde Moodle XML (cloze / multianswer)


@dataclass
class FormattedText:
    format: str = "moodle"
    text: str = ""


@dataclass
class Choice:
    is_correct: bool = False
    weight: Optional[float] = None
    text: Optional[FormattedText] = None
    feedback: Optional[FormattedText] = None


@dataclass
class MatchPair:
    subquestion: FormattedText = field(default_factory=FormattedText)
    subanswer: str = ""


@dataclass
class NumericalAnswer:
    type: str = "simple"  # simple, range, high-low
    number: Optional[float] = None
    range: Optional[float] = None
    number_high: Optional[float] = None
    number_low: Optional[float] = None


@dataclass
class Question:
    type: str = ""
    title: Optional[str] = None
    stem: Optional[FormattedText] = None
    id: Optional[str] = None
    tags: list = field(default_factory=list)
    has_embedded_answers: bool = False
    global_feedback: Optional[FormattedText] = None
    # Specific fields by type
    choices: list = field(default_factory=list)
    match_pairs: list = field(default_factory=list)
    is_true: Optional[bool] = None
    true_feedback: Optional[FormattedText] = None
    false_feedback: Optional[FormattedText] = None
    # Clasificación leída de comentarios o tags (bloom, dificultad_enunciado, …).
    metadata: dict = field(default_factory=dict)
    # Sólo desde Moodle XML: penalty, defaultgrade, shuffleanswers, answernumbering, single.
    moodle: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary, excluding None values and empty lists."""
        result: Dict[str, Any] = {"type": self.type}
        if self.title:
            result["title"] = self.title
        if self.stem:
            result["stem"] = asdict(self.stem)
        if self.id:
            result["id"] = self.id
        if self.tags:
            result["tags"] = self.tags
        if self.has_embedded_answers:
            result["hasEmbeddedAnswers"] = self.has_embedded_answers
        if self.global_feedback:
            result["globalFeedback"] = asdict(self.global_feedback)
        if self.choices:
            result["choices"] = [
                {k: (asdict(v) if hasattr(v, '__dataclass_fields__') else v) 
                 for k, v in asdict(c).items() if v is not None}
                for c in self.choices
            ]
        if self.match_pairs:
            result["matchPairs"] = [asdict(mp) for mp in self.match_pairs]
        if self.is_true is not None:
            result["isTrue"] = self.is_true
        if self.true_feedback:
            result["trueFeedback"] = asdict(self.true_feedback)
        if self.false_feedback:
            result["falseFeedback"] = asdict(self.false_feedback)
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        if self.moodle:
            result["moodle"] = dict(self.moodle)
        return result
