"""
Metadata Enricher - Refresca metadata desde fuentes externas

Actualiza cover, status, géneros, descripción y otros campos
desde AniList (manga), ComicVine (comics) y Google Books (libros).
Diseñado para ejecutarse semanalmente para mantener los datos frescos.
"""

import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class MetadataEnricher:
    """Refresca metadata de items en la biblioteca desde sus fuentes externas."""

    async def enrich_manga(self, manga_id: int, db: Session) -> bool:
        """
        Re-fetcha metadata de manga desde AniList.
        Actualiza cover, status, géneros, descripción, totales y score.
        Returns True si se actualizó algo.
        """
        from app.models.manga import Manga
        from app.services.anilist import get_anilist_service

        manga = db.query(Manga).filter(Manga.id == manga_id).first()
        if not manga or not manga.anilist_id:
            logger.warning(f"Manga {manga_id} not found or has no anilist_id")
            return False

        try:
            anilist = get_anilist_service()
            data = await anilist.get_manga_by_id(manga.anilist_id)
            if not data:
                logger.warning(f"AniList returned no data for anilist_id={manga.anilist_id}")
                return False

            updated = False

            # Update cover if we got a better one (or if current is empty)
            new_cover = data.get('cover_image') or data.get('cover_image_large')
            if new_cover and new_cover != manga.cover_image:
                manga.cover_image = new_cover
                updated = True

            new_banner = data.get('banner_image')
            if new_banner and new_banner != manga.banner_image:
                manga.banner_image = new_banner
                updated = True

            # Update status (might have changed from RELEASING to FINISHED)
            new_status = data.get('status')
            if new_status and new_status != manga.status:
                manga.status = new_status
                updated = True

            # Update genres/tags if richer
            new_genres = data.get('genres')
            if new_genres and new_genres != manga.genres:
                manga.genres = new_genres
                updated = True

            new_tags = data.get('tags')
            if new_tags and new_tags != manga.tags:
                manga.tags = new_tags
                updated = True

            # Update description if missing or short
            new_desc = data.get('description')
            if new_desc and (not manga.description or len(new_desc) > len(manga.description or '')):
                manga.description = new_desc
                updated = True

            # Update totals
            new_chapters = data.get('chapters_total')
            if new_chapters and new_chapters != manga.chapters_total:
                manga.chapters_total = new_chapters
                updated = True

            new_volumes = data.get('volumes_total')
            if new_volumes and new_volumes != manga.volumes_total:
                manga.volumes_total = new_volumes
                updated = True

            # Update score and popularity
            new_score = data.get('average_score')
            if new_score is not None:
                manga.average_score = new_score
                updated = True

            new_pop = data.get('popularity')
            if new_pop is not None:
                manga.popularity = new_pop
                updated = True

            if updated:
                manga.updated_at = datetime.utcnow()
                db.commit()
                logger.info(f"Enriched manga '{manga.title}' (id={manga_id})")
            else:
                logger.debug(f"No changes for manga '{manga.title}' (id={manga_id})")

            return updated

        except Exception as e:
            logger.error(f"Error enriching manga {manga_id}: {e}")
            return False

    async def enrich_comic(self, comic_id: int, db: Session) -> bool:
        """
        Re-fetcha metadata de comic desde ComicVine.
        Actualiza publisher, total_issues, cover, description.
        Returns True si se actualizó algo.
        """
        from app.models.comic import Comic
        from app.services.comic_service import refresh_comic_metadata

        comic = db.query(Comic).filter(Comic.id == comic_id).first()
        if not comic or not comic.comicvine_id:
            logger.warning(f"Comic {comic_id} not found or has no comicvine_id")
            return False

        try:
            from app.services.comicvine import get_comicvine_service
            comicvine = get_comicvine_service()
            details = await comicvine.get_volume(comic.comicvine_id)

            if not details:
                logger.warning(f"ComicVine returned no data for id={comic.comicvine_id}")
                return False

            updated = False

            new_cover = details.get('cover_image')
            if new_cover and new_cover != comic.cover_image:
                comic.cover_image = new_cover
                updated = True

            new_desc = details.get('description')
            if new_desc and (not comic.description or len(new_desc) > len(comic.description or '')):
                comic.description = new_desc
                updated = True

            new_count = details.get('count_of_issues')
            if new_count and new_count != comic.count_of_issues:
                comic.count_of_issues = new_count
                updated = True

            new_publisher = details.get('publisher')
            if new_publisher and (not comic.publisher or comic.publisher in ('Unknown', 'unknown', '')):
                comic.publisher = new_publisher
                updated = True

            if updated:
                comic.updated_at = datetime.utcnow()
                db.commit()
                logger.info(f"Enriched comic '{comic.title}' (id={comic_id})")

            return updated

        except Exception as e:
            logger.error(f"Error enriching comic {comic_id}: {e}")
            return False

    async def enrich_book(self, book_id: int, db: Session) -> bool:
        """
        Re-fetcha metadata de libro desde Google Books.
        Fallback a Open Library para covers de mayor resolución.
        Returns True si se actualizó algo.
        """
        from app.models.book import Book
        from app.services.google_books import get_google_books_service
        import aiohttp

        book = db.query(Book).filter(Book.id == book_id).first()
        if not book:
            logger.warning(f"Book {book_id} not found")
            return False

        updated = False

        try:
            # Primary: Google Books
            if book.google_books_id:
                gb = get_google_books_service()
                data = await gb.get_book_by_id(book.google_books_id)

                if data:
                    new_cover = data.get('cover_image')
                    if new_cover and new_cover != book.cover_image:
                        book.cover_image = new_cover
                        updated = True

                    new_desc = data.get('description')
                    if new_desc and (not book.description or len(new_desc) > len(book.description or '')):
                        book.description = new_desc
                        updated = True

                    new_pub = data.get('publisher')
                    if new_pub and not book.publisher:
                        book.publisher = new_pub
                        updated = True

                    new_cats = data.get('categories')
                    if new_cats and not book.categories:
                        book.categories = new_cats
                        updated = True

                    new_rating = data.get('average_rating')
                    if new_rating is not None and not book.average_rating:
                        book.average_rating = new_rating
                        updated = True

            # Fallback: Open Library cover (better resolution)
            if not book.cover_image and (book.isbn_13 or book.isbn_10):
                isbn = book.isbn_13 or book.isbn_10
                ol_cover = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
                # Check if cover actually exists (not a placeholder)
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.head(ol_cover, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                            if resp.status == 200 and int(resp.headers.get('Content-Length', 0)) > 1000:
                                book.cover_image = ol_cover
                                updated = True
                                logger.info(f"Got Open Library cover for book '{book.title}'")
                except Exception:
                    pass

            if updated:
                book.updated_at = datetime.utcnow()
                db.commit()
                logger.info(f"Enriched book '{book.title}' (id={book_id})")
            else:
                logger.debug(f"No changes for book '{book.title}' (id={book_id})")

            return updated

        except Exception as e:
            logger.error(f"Error enriching book {book_id}: {e}")
            return False

    async def run_weekly_enrichment(self) -> dict:
        """
        Job semanal: enriquece items añadidos hace >7 días.
        Prioriza items con cover vacío o publisher='Unknown'.
        """
        from app.database import SessionLocal
        from app.models.manga import Manga
        from app.models.comic import Comic
        from app.models.book import Book

        db = SessionLocal()
        stats = {'manga': 0, 'comics': 0, 'books': 0, 'errors': 0}

        try:
            cutoff = datetime.utcnow() - timedelta(days=7)

            # Manga: missing cover or stale
            mangas = db.query(Manga).filter(
                Manga.anilist_id.isnot(None),
                Manga.created_at < cutoff
            ).order_by(
                # Prioritize missing covers first
                Manga.cover_image.asc()
            ).limit(50).all()

            for manga in mangas:
                try:
                    if await self.enrich_manga(manga.id, db):
                        stats['manga'] += 1
                except Exception as e:
                    logger.error(f"Weekly enrichment error for manga {manga.id}: {e}")
                    stats['errors'] += 1

            # Comics: missing cover or unknown publisher
            comics = db.query(Comic).filter(
                Comic.comicvine_id.isnot(None),
                Comic.created_at < cutoff
            ).order_by(Comic.cover_image.asc()).limit(30).all()

            for comic in comics:
                try:
                    if await self.enrich_comic(comic.id, db):
                        stats['comics'] += 1
                except Exception as e:
                    logger.error(f"Weekly enrichment error for comic {comic.id}: {e}")
                    stats['errors'] += 1

            # Books: missing cover
            books = db.query(Book).filter(
                Book.created_at < cutoff
            ).order_by(Book.cover_image.asc()).limit(30).all()

            for book in books:
                try:
                    if await self.enrich_book(book.id, db):
                        stats['books'] += 1
                except Exception as e:
                    logger.error(f"Weekly enrichment error for book {book.id}: {e}")
                    stats['errors'] += 1

            logger.info(f"Weekly enrichment complete: {stats}")
            return stats

        finally:
            db.close()


# Singleton
_enricher = None

def get_metadata_enricher() -> MetadataEnricher:
    global _enricher
    if _enricher is None:
        _enricher = MetadataEnricher()
    return _enricher
