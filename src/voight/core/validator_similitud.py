"""Similitud textual (TF-IDF + Jaccard) y detección de duplicados del analizador de bancos."""

import math
import re
from collections import defaultdict
from typing import Dict, Optional

# Pesos de la similitud combinada: coseno TF-IDF y Jaccard (más estricto).
PESO_COSENO = 0.4
PESO_JACCARD = 0.6


class SimilitudMixin:
    # Atributos que define AnalizadorBanco (el mixin no se usa solo).
    all_questions: list
    duplicates: list
    similarity_threshold: float

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text for comparison."""
        text = text.lower()
        # Mantener letras, números y espacios
        text = re.sub(r'[^a-záéíóúñü0-9\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def _tokenize(self, text: str) -> list:
        """Tokenize text into words, keeping all tokens."""
        words = text.split()
        # Mantener todas las palabras/tokens, incluyendo números
        return [w for w in words if w]
    
    def _compute_word_freq(self, text: str) -> dict:
        """Compute word frequency."""
        words = self._tokenize(text)
        freq: Dict[str, int] = defaultdict(int)
        for word in words:
            freq[word] += 1
        return dict(freq)
    
    def _compute_idf(self, all_texts: list) -> dict:
        """Compute IDF (inverse document frequency)."""
        doc_count: Dict[str, int] = defaultdict(int)
        num_docs = len(all_texts)
        
        for text in all_texts:
            words = set(self._tokenize(text))
            for word in words:
                doc_count[word] += 1
        
        # IDF suavizado (siempre positivo): con log(N / (1 + df)) una palabra que comparten
        # todos o casi todos los documentos pesa 0 o negativo, y en un conjunto chico dos
        # preguntas idénticas quedaban con coseno 0.
        idf = {}
        for word, count in doc_count.items():
            idf[word] = math.log((1 + num_docs) / (1 + count)) + 1
        
        return idf
    
    def _compute_tfidf_vector(self, text: str, idf: dict) -> dict:
        """Compute TF-IDF vector."""
        freq = self._compute_word_freq(text)
        total_words = sum(freq.values())
        
        if total_words == 0:
            return {}
        
        tfidf = {}
        for word, count in freq.items():
            tf = count / total_words
            tfidf[word] = tf * idf.get(word, 0)
        
        return tfidf
    
    def _cosine_similarity(self, vec1: dict, vec2: dict, mag1: Optional[float] = None, mag2: Optional[float] = None) -> float:
        """Compute cosine similarity."""
        if not vec1 or not vec2:
            return 0.0
        
        # Sólo las palabras comunes aportan al producto punto.
        if len(vec1) > len(vec2):
            vec1, vec2, mag1, mag2 = vec2, vec1, mag2, mag1
        dot_product = sum(v * vec2[word] for word, v in vec1.items() if word in vec2)
        if mag1 is None:
            mag1 = math.sqrt(sum(v ** 2 for v in vec1.values()))
        if mag2 is None:
            mag2 = math.sqrt(sum(v ** 2 for v in vec2.values()))
        
        if mag1 == 0 or mag2 == 0:
            return 0.0
        
        return dot_product / (mag1 * mag2)
    
    def _jaccard_similarity(self, text1, text2) -> float:
        """Compute Jaccard similarity between two texts (o dos conjuntos de palabras)."""
        words1 = text1 if isinstance(text1, (set, frozenset)) else set(self._tokenize(text1))
        words2 = text2 if isinstance(text2, (set, frozenset)) else set(self._tokenize(text2))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1 & words2)
        union = len(words1) + len(words2) - intersection
        
        return intersection / union if union > 0 else 0.0
    
    def _combined_similarity(self, q1: dict, q2: dict) -> float:
        """Compute combined similarity using multiple metrics."""
        # Similitud Jaccard (más sensible a diferencias en palabras individuales)
        jaccard_sim = self._jaccard_similarity(q1.get("tokens", q1["clean_text"]), q2.get("tokens", q2["clean_text"]))
        
        # Similitud de coseno TF-IDF
        cosine_sim = self._cosine_similarity(q1["vector"], q2["vector"], q1.get("magnitude"), q2.get("magnitude"))
        
        # Combinar: promedio ponderado (Jaccard es más estricto)
        combined = (cosine_sim * PESO_COSENO) + (jaccard_sim * PESO_JACCARD)
        
        return combined

    def find_duplicates(self):
        """Find duplicate or very similar questions."""
        self.duplicates = []
        if len(self.all_questions) < 2:
            return
        
        if self.verbose:
            print(f"Buscando duplicados con threshold {self.similarity_threshold}...")
        
        # Prepare texts
        for q in self.all_questions:
            q["clean_text"] = self._clean_text(q["full_text"])
        
        # Compute IDF
        all_texts = [q["clean_text"] for q in self.all_questions]
        idf = self._compute_idf(all_texts)
        
        # Compute TF-IDF vectors (y lo que se reusa en cada comparación)
        for q in self.all_questions:
            q["vector"] = self._compute_tfidf_vector(q["clean_text"], idf)
            q["magnitude"] = math.sqrt(sum(v ** 2 for v in q["vector"].values()))
            q["tokens"] = frozenset(self._tokenize(q["clean_text"]))
        
        # Compare questions
        jaccard_min = (self.similarity_threshold - PESO_COSENO) / PESO_JACCARD
        for i, j in self._candidate_pairs():
            # Sin el Jaccard mínimo no se llega al umbral aunque el coseno sea 1.
            if self._jaccard_similarity(self.all_questions[i]["tokens"], self.all_questions[j]["tokens"]) < jaccard_min - 1e-9:
                continue
            # Usar similitud combinada (TF-IDF coseno + Jaccard)
            similarity = self._combined_similarity(
                self.all_questions[i],
                self.all_questions[j]
            )
            
            if similarity >= self.similarity_threshold:
                self.duplicates.append({
                    "index1": i,
                    "index2": j,
                    "similarity": similarity
                })
        
        # Sort by similarity
        self.duplicates.sort(key=lambda x: x["similarity"], reverse=True)

    def _candidate_pairs(self):
        """Pares (i, j), i < j, que pueden superar el umbral, en orden.

        Como el coseno no pasa de 1, `combinada >= umbral` exige
        `jaccard >= (umbral - PESO_COSENO) / PESO_JACCARD`. Para un umbral de Jaccard
        así, dos conjuntos que lo cumplen comparten al menos un token entre los
        primeros `|x| - ceil(t·|x|) + 1` de cada uno (ordenados por rareza): el
        filtrado por prefijos de los joins por similitud. Es exacto (no pierde pares)
        y evita comparar todos contra todos en repositorios de miles de preguntas.
        """
        n = len(self.all_questions)
        jaccard_min = (self.similarity_threshold - PESO_COSENO) / PESO_JACCARD
        if jaccard_min <= 0:
            for i in range(n):
                for j in range(i + 1, n):
                    yield i, j
            return

        conjuntos = [q.get("tokens") or set(self._tokenize(q["clean_text"])) for q in self.all_questions]
        frecuencia = defaultdict(int)
        for conjunto in conjuntos:
            for token in conjunto:
                frecuencia[token] += 1

        indice = defaultdict(list)
        pares = set()
        for j, conjunto in enumerate(conjuntos):
            if not conjunto:
                continue  # Jaccard 0: no llega al umbral
            ordenados = sorted(conjunto, key=lambda t: (frecuencia[t], t))
            tam = len(ordenados)
            # El margen evita perder pares por redondeo de punto flotante.
            prefijo = tam - math.ceil(jaccard_min * tam - 1e-9) + 1
            for token in ordenados[:prefijo]:
                for i in indice[token]:
                    if min(tam, len(conjuntos[i])) >= jaccard_min * max(tam, len(conjuntos[i])) - 1e-9:
                        pares.add((i, j))
                indice[token].append(j)
        yield from sorted(pares)
