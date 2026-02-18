"""
Content Matcher - Motor de matching anti-duplicados
Normaliza títulos y detecta series ya existentes en la biblioteca
"""

import re
import unicodedata
import logging
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

STOP_WORDS = {
    'the', 'a', 'an', 'of', 'and', 'or', 'in', 'on', 'at', 'to',
    'el', 'la', 'los', 'las', 'de', 'del', 'y', 'e', 'en', 'un', 'una',
    'vol', 'volume', 'tomo', 'parte', 'part',
}


class ContentMatcher:
    """Detecta duplicados fuzzy por normalización de título y overlap de keywords."""

    def normalize(self, title: str) -> str:
        """Normaliza un título para comparación: lowercase, sin acentos, sin puntuación, sin stop words."""
        # NFD decomposition + remove combining chars (diacritics)
        nfkd = unicodedata.normalize('NFD', title.lower())
        ascii_str = ''.join(c for c in nfkd if unicodedata.category(c) != 'Mn')
        # Remove punctuation and extra spaces
        cleaned = re.sub(r'[^\w\s]', ' ', ascii_str)
        # Filter stop words and short tokens
        words = [w for w in cleaned.split() if w not in STOP_WORDS and len(w) > 1]
        # Remove trailing pure numbers (vol 1, tomo 2, etc.)
        while words and re.match(r'^\d+$', words[-1]):
            words.pop()
        return ' '.join(words)

    def similarity(self, a: str, b: str) -> float:
        """Jaccard similarity over normalized keywords."""
        a_norm = set(self.normalize(a).split())
        b_norm = set(self.normalize(b).split())
        if not a_norm or not b_norm:
            return 0.0
        intersection = a_norm & b_norm
        union = a_norm | b_norm
        return len(intersection) / len(union)

    def find_duplicate(self, db: Session, title: str, content_type: str, user_id: int):
        """
        Busca un ítem similar (≥ 0.8 Jaccard) en la biblioteca del usuario.

        Returns the existing DB model instance or None.
        """
        from app.models.manga import Manga
        from app.models.comic import Comic
        from app.models.book import Book

        model_map = {'manga': Manga, 'comic': Comic, 'book': Book}
        model = model_map.get(content_type)
        if not model:
            return None

        items = db.query(model).filter(model.user_id == user_id).all()
        best_match = None
        best_score = 0.0

        for item in items:
            score = self.similarity(title, item.title)
            if score > best_score:
                best_score = score
                best_match = item

        if best_score >= 0.8:
            logger.info(
                f"Duplicate detected: '{title}' ≈ '{best_match.title}' "
                f"(score={best_score:.2f}, type={content_type})"
            )
            return best_match

        return None
