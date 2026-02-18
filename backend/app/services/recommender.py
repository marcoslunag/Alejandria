"""
Recomendador Local - Sin modelos externos ni IA

Genera recomendaciones basadas en el perfil de la biblioteca del usuario:
géneros frecuentes, autores repetidos, publishers, y scores promedio.
Las recomendaciones se buscan en AniList (manga), ComicVine (comics)
y Google Books (libros) usando los atributos del perfil.

Cache en memoria por (user_id, fecha) — se recalcula cada día.
"""

import logging
from datetime import date, datetime
from collections import Counter
from typing import Optional

logger = logging.getLogger(__name__)

# In-memory cache: {(user_id, date_str): [recommendations]}
_cache: dict = {}


class LocalRecommender:
    """Genera recomendaciones locales basadas en la biblioteca del usuario."""

    def build_user_profile(self, user_id: int, db) -> dict:
        """
        Construye el perfil del usuario a partir de su biblioteca.
        Retorna: top géneros, autores, publishers, content_types y score medio.
        """
        from app.models.manga import Manga
        from app.models.comic import Comic
        from app.models.book import Book

        profile = {
            'genres': Counter(),
            'authors': set(),
            'publishers': set(),
            'content_types': set(),
            'avg_score': 0.0,
            'anilist_ids': set(),
            'google_books_ids': set(),
            'comicvine_ids': set(),
        }

        scores = []

        # Manga
        mangas = db.query(Manga).filter(Manga.user_id == user_id).all()
        if mangas:
            profile['content_types'].add('manga')
            for m in mangas:
                if m.genres:
                    for g in m.genres:
                        profile['genres'][g] += 1
                if m.authors:
                    for a in m.authors:
                        profile['authors'].add(a.strip())
                if m.average_score:
                    scores.append(m.average_score)
                if m.anilist_id:
                    profile['anilist_ids'].add(m.anilist_id)

        # Comics
        comics = db.query(Comic).filter(Comic.user_id == user_id).all()
        if comics:
            profile['content_types'].add('comics')
            for c in comics:
                if c.genres:
                    for g in c.genres:
                        profile['genres'][g] += 1
                if c.publisher:
                    profile['publishers'].add(c.publisher)
                if c.comicvine_id:
                    profile['comicvine_ids'].add(c.comicvine_id)

        # Books
        books = db.query(Book).filter(Book.user_id == user_id).all()
        if books:
            profile['content_types'].add('books')
            for b in books:
                if b.categories:
                    for cat in b.categories:
                        profile['genres'][cat] += 1
                if b.authors:
                    for a in b.authors:
                        profile['authors'].add(a.strip())
                if b.average_rating:
                    scores.append(b.average_rating * 20)  # 0-5 → 0-100
                if b.google_books_id:
                    profile['google_books_ids'].add(b.google_books_id)

        profile['avg_score'] = sum(scores) / len(scores) if scores else 70.0
        return profile

    def _score_candidate(self, candidate: dict, profile: dict) -> float:
        """
        Calcula score compuesto para un candidato:
        - 50% overlap de géneros con el perfil
        - 30% match de autor
        - 20% similitud de score
        """
        candidate_genres = set(candidate.get('genres', []))
        profile_genres = set(profile['genres'].keys())

        genre_overlap = (
            len(candidate_genres & profile_genres) / len(candidate_genres | profile_genres)
            if candidate_genres or profile_genres
            else 0.0
        )

        author_match = 0.0
        candidate_authors = {a.strip() for a in candidate.get('authors', [])}
        if candidate_authors & profile['authors']:
            author_match = 1.0

        candidate_score = candidate.get('score', profile['avg_score'])
        score_similarity = 1.0 - abs(candidate_score - profile['avg_score']) / 100.0

        return genre_overlap * 0.5 + author_match * 0.3 + score_similarity * 0.2

    def _build_reason_label(self, candidate: dict, profile: dict) -> str:
        """Genera etiqueta de razón legible para la recomendación."""
        candidate_genres = set(candidate.get('genres', []))
        profile_genres = set(profile['genres'].keys())
        matching = candidate_genres & profile_genres

        candidate_authors = {a.strip() for a in candidate.get('authors', [])}
        if candidate_authors & profile['authors']:
            author = next(iter(candidate_authors & profile['authors']))
            return f"Del mismo autor: {author}"

        if matching:
            top_genre = max(matching, key=lambda g: profile['genres'].get(g, 0))
            return f"Basado en tu interés en {top_genre}"

        return "Similar a tu biblioteca"

    async def _get_manga_recommendations(self, profile: dict, limit: int) -> list:
        """Busca manga recomendado en AniList por géneros principales."""
        if not profile['genres']:
            return []

        try:
            from app.services.anilist import get_anilist_service

            anilist = get_anilist_service()
            top_genres = [g for g, _ in profile['genres'].most_common(3)]

            results = []
            for genre in top_genres[:2]:
                search_results = await anilist.search_manga(genre, page=1)
                for item in search_results.get('results', [])[:5]:
                    if item.get('anilist_id') not in profile['anilist_ids']:
                        results.append({
                            'content_type': 'manga',
                            'title': item.get('title', ''),
                            'cover': item.get('cover_image', ''),
                            'score': item.get('average_score', 0),
                            'genres': item.get('genres', []),
                            'authors': item.get('authors', []),
                            'external_id': item.get('anilist_id'),
                            'anilist_id': item.get('anilist_id'),
                            'description': item.get('description', ''),
                            'status': item.get('status', ''),
                        })

            return results[:limit]
        except Exception as e:
            logger.error(f"Error getting manga recommendations: {e}")
            return []

    async def _get_book_recommendations(self, profile: dict, limit: int) -> list:
        """Busca libros recomendados en Google Books por autor o género."""
        try:
            from app.services.google_books import get_google_books_service

            gb = get_google_books_service()

            # Query by top author or top genre
            query_parts = []
            if profile['authors']:
                query_parts.append(f'inauthor:"{next(iter(profile["authors"]))}"')
            elif profile['genres']:
                query_parts.append(list(profile['genres'].keys())[0])

            if not query_parts:
                return []

            search_results = await gb.search_books(query_parts[0], max_results=10)
            results = []
            for item in search_results.get('results', []):
                if item.get('google_books_id') not in profile['google_books_ids']:
                    results.append({
                        'content_type': 'book',
                        'title': item.get('title', ''),
                        'cover': item.get('cover_image', item.get('thumbnail', '')),
                        'score': (item.get('average_rating') or 0) * 20,
                        'genres': item.get('categories', []),
                        'authors': item.get('authors', []),
                        'external_id': item.get('google_books_id'),
                        'google_books_id': item.get('google_books_id'),
                        'description': item.get('description', ''),
                    })

            return results[:limit]
        except Exception as e:
            logger.error(f"Error getting book recommendations: {e}")
            return []

    async def get_recommendations(
        self, user_id: int, db, limit: int = 20, content_type: str = 'all'
    ) -> list:
        """
        Genera recomendaciones para el usuario.
        Cache: recalcula si cache_date != hoy.
        """
        cache_key = (user_id, str(date.today()), content_type, limit)
        if cache_key in _cache:
            return _cache[cache_key]

        profile = self.build_user_profile(user_id, db)

        if not profile['content_types']:
            # Empty library - can't recommend
            return []

        candidates = []

        # Get manga recs if library has manga or no filter
        if content_type in ('all', 'manga') and 'manga' in profile['content_types']:
            manga_recs = await self._get_manga_recommendations(profile, limit // 2 + 5)
            candidates.extend(manga_recs)

        # Get book recs if library has books or no filter
        if content_type in ('all', 'books') and 'books' in profile['content_types']:
            book_recs = await self._get_book_recommendations(profile, limit // 2 + 5)
            candidates.extend(book_recs)

        # Score and rank candidates
        for c in candidates:
            c['recommendation_score'] = self._score_candidate(c, profile)
            c['reason_label'] = self._build_reason_label(c, profile)

        candidates.sort(key=lambda x: x['recommendation_score'], reverse=True)
        result = candidates[:limit]

        _cache[cache_key] = result
        return result


# Singleton
_recommender = None


def get_recommender() -> LocalRecommender:
    global _recommender
    if _recommender is None:
        _recommender = LocalRecommender()
    return _recommender
