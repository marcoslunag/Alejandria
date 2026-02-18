"""
Content Scheduler Service
Handles automated tasks like checking for new chapters, downloads, conversions
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.database import SessionLocal
from app.models.manga import Manga
from app.models.chapter import Chapter
from app.models.book import Book
from app.models.book_chapter import BookChapter
from app.models.comic import Comic, ComicIssue
from app.models.download import DownloadQueue
from app.services.scraper import TomosMangaScraper
from app.services.downloader import MangaDownloader
from app.services.book_downloader import BookDownloader
from app.services.converter import KCCConverter
from app.services.stk_kindle_sender import get_stk_sender
from pathlib import Path
from datetime import datetime, timedelta
import logging
import asyncio

logger = logging.getLogger(__name__)


class ContentScheduler:
    """
    Scheduler para tareas automáticas:
    - Buscar nuevos capítulos cada 6 horas
    - Procesar cola de descargas
    - Convertir archivos descargados
    - Enviar archivos convertidos al Kindle
    - Limpiar archivos antiguos
    """

    def __init__(
        self,
        check_interval_hours: int = 6,
        download_dir: str = "/downloads",
        library_dir: str = "/library"
    ):
        """
        Initialize scheduler

        Args:
            check_interval_hours: Hours between chapter checks
            download_dir: Directory for downloads
            library_dir: Directory for processed content (manga, comics, books)
        """
        self.scheduler = AsyncIOScheduler()
        self.check_interval_hours = check_interval_hours

        # Initialize services
        self.scraper = TomosMangaScraper()
        self.downloader = MangaDownloader(download_dir=download_dir)
        self.book_downloader = BookDownloader(download_dir=str(Path(download_dir) / "books"))
        self.converter = KCCConverter(output_dir=str(Path(library_dir) / "kindle"))

        # Tracking
        self.is_running = False
        self.active_downloads = {}

    def start(self):
        """Inicia el scheduler"""
        if self.is_running:
            logger.warning("Scheduler is already running")
            return

        # Buscar nuevos capítulos cada X horas
        self.scheduler.add_job(
            self.check_new_chapters,
            IntervalTrigger(hours=self.check_interval_hours),
            id='check_chapters',
            replace_existing=True,
            max_instances=1
        )

        # Procesar cola de descargas cada 5 minutos
        self.scheduler.add_job(
            self.process_download_queue,
            IntervalTrigger(minutes=5),
            id='process_downloads',
            replace_existing=True,
            max_instances=1
        )

        # Procesar conversiones cada 10 minutos
        self.scheduler.add_job(
            self.process_conversions,
            IntervalTrigger(minutes=10),
            id='process_conversions',
            replace_existing=True,
            max_instances=1
        )

        # Enviar archivos al Kindle cada 15 minutos
        # (reads settings from DB, so always schedule)
        self.scheduler.add_job(
            self.send_to_kindle,
            IntervalTrigger(minutes=15),
            id='send_kindle',
            replace_existing=True,
            max_instances=1
        )

        # Limpiar archivos viejos diariamente a las 3 AM
        self.scheduler.add_job(
            self.cleanup_old_files,
            CronTrigger(hour=3, minute=0),
            id='cleanup',
            replace_existing=True
        )

        # Buscar fuentes de cómics cada 6 horas
        self.scheduler.add_job(
            self.check_comic_sources,
            IntervalTrigger(hours=self.check_interval_hours),
            id='check_comic_sources',
            replace_existing=True,
            max_instances=1
        )

        # Reintentar descargas fallidas cada hora
        self.scheduler.add_job(
            self.retry_failed_downloads,
            IntervalTrigger(hours=1),
            id='retry_downloads',
            replace_existing=True,
            max_instances=1
        )

        self.scheduler.start()
        self.is_running = True
        logger.info(f"Scheduler started (check interval: {self.check_interval_hours}h)")

    def stop(self):
        """Detiene el scheduler"""
        if not self.is_running:
            return

        self.scheduler.shutdown(wait=True)
        self.is_running = False
        logger.info("Scheduler stopped")

    async def check_new_chapters(self):
        """Busca nuevos capítulos para todos los manga en la biblioteca"""
        logger.info("Checking for new chapters...")

        db: Session = SessionLocal()
        try:
            # Obtener todos los manga (monitorizados o no) que están en publicación
            # Para los finalizados no tiene sentido buscar nuevos capítulos
            manga_list = db.query(Manga).filter(
                Manga.status.in_(['RELEASING', None])  # En publicación o sin estado definido
            ).all()

            logger.info(f"Checking {len(manga_list)} manga for new chapters")

            for manga in manga_list:
                await self._check_manga(manga, db)

            logger.info("Chapter check completed")

        except Exception as e:
            logger.error(f"Error in check_new_chapters: {e}")
        finally:
            db.close()

    async def _check_manga(self, manga: Manga, db: Session):
        """Busca nuevos capítulos para un manga específico"""
        try:
            logger.info(f"Checking manga: {manga.title}")

            # Scrapear página del manga
            details = self.scraper.get_manga_details(manga.url)

            if not details or not details.get('chapters'):
                logger.warning(f"No chapters found for {manga.title}")
                return

            # Obtener números de capítulos existentes
            existing_chapters = db.query(Chapter.number).filter(
                Chapter.manga_id == manga.id
            ).all()
            existing_numbers = {ch.number for ch in existing_chapters}

            # Identificar nuevos capítulos
            new_chapters = []
            for ch_data in details['chapters']:
                if ch_data['number'] not in existing_numbers:
                    new_chapters.append(ch_data)

            if new_chapters:
                logger.info(f"Found {len(new_chapters)} new chapters for {manga.title}")

                # Añadir nuevos capítulos a la DB
                for ch_data in new_chapters:
                    # Usar el download_url y backup_url que ya vienen procesados del scraper
                    download_url = ch_data.get('download_url') or self._select_best_download_link(ch_data.get('download_links', []))
                    backup_url = ch_data.get('backup_url')
                    download_host = ch_data.get('download_host', 'unknown')

                    chapter = Chapter(
                        manga_id=manga.id,
                        number=ch_data['number'],
                        title=ch_data['title'],
                        url=ch_data['url'],
                        download_url=download_url,
                        backup_url=backup_url,
                        download_host=download_host,
                        volume_range_start=ch_data.get('volume_range_start'),
                        volume_range_end=ch_data.get('volume_range_end'),
                        status='pending'
                    )
                    db.add(chapter)

                db.commit()

                # Solo añadir a cola de descargas si el manga está monitorizado
                if manga.monitored:
                    for ch_data in new_chapters:
                        chapter = db.query(Chapter).filter(
                            and_(
                                Chapter.manga_id == manga.id,
                                Chapter.number == ch_data['number']
                            )
                        ).first()

                        if chapter:
                            queue_item = DownloadQueue(
                                chapter_id=chapter.id,
                                status='queued'
                            )
                            db.add(queue_item)

                    db.commit()
                    logger.info(f"Queued {len(new_chapters)} chapters for auto-download (monitored)")
                else:
                    logger.info(f"Found {len(new_chapters)} new chapters for {manga.title} (not monitored - manual download required)")

            # Actualizar última verificación
            manga.last_check = datetime.utcnow()
            db.commit()

        except Exception as e:
            logger.error(f"Error checking {manga.title}: {e}")
            db.rollback()

    async def check_comic_sources(self):
        """
        Busca fuentes de descarga para cómics monitorizados.
        - Cómics sin fuentes buscadas (sources_searched=False)
        - Cómics con issues sin download_url
        Solo busca y guarda links — NO auto-queue downloads.
        """
        logger.info("Checking comic sources...")

        db: Session = SessionLocal()
        try:
            from app.services.comic_service import search_scrapers_for_comic
            from sqlalchemy import and_

            # Find monitored comics that need source searching
            comics = db.query(Comic).filter(
                and_(
                    Comic.monitored == True,
                    Comic.sources_searched == False
                )
            ).all()

            if not comics:
                # Also check comics with issues missing download URLs
                comics_with_missing = db.query(Comic).join(ComicIssue).filter(
                    and_(
                        Comic.monitored == True,
                        ComicIssue.download_url == None,
                        ComicIssue.status == 'pending'
                    )
                ).distinct().limit(5).all()
                comics = comics_with_missing

            if not comics:
                logger.info("No comics need source searching")
                return

            logger.info(f"Searching sources for {len(comics)} comics")

            for comic in comics:
                try:
                    # If we already have a known scraper page URL, resolve links directly
                    # instead of doing a full text-based search
                    if comic.source_urls:
                        from app.services.comic_service import fetch_volume_from_scraper
                        for src_name, src_url in comic.source_urls.items():
                            issue_count = db.query(ComicIssue).filter(
                                ComicIssue.comic_id == comic.id
                            ).count()
                            logger.info(f"Resolving links from known source: {src_name} → {src_url}")
                            await fetch_volume_from_scraper(comic.id, src_url, src_name, issue_count)
                            break  # Only use first source
                    else:
                        logger.info(f"Searching sources for: {comic.title}")
                        await search_scrapers_for_comic(comic.id, comic.title)

                    # Mark as searched (DON'T auto-queue downloads — user decides when to download)
                    comic.sources_searched = True
                    comic.last_check = datetime.utcnow()
                    db.commit()

                    issues_with_urls = db.query(ComicIssue).filter(
                        and_(
                            ComicIssue.comic_id == comic.id,
                            ComicIssue.download_url != None
                        )
                    ).count()
                    total_issues = db.query(ComicIssue).filter(ComicIssue.comic_id == comic.id).count()
                    logger.info(f"Source search complete for '{comic.title}': {issues_with_urls}/{total_issues} issues have download URLs")

                except Exception as e:
                    logger.error(f"Error searching sources for {comic.title}: {e}")
                    db.rollback()

                # Small delay between comics
                await asyncio.sleep(2)

            # Enrich metadata: retry ComicVine for comics with publisher="Unknown"
            await self._enrich_comic_metadata(db)

            logger.info("Comic source check completed")

        except Exception as e:
            logger.error(f"Error in check_comic_sources: {e}")
        finally:
            db.close()

    async def _enrich_comic_metadata(self, db: Session):
        """
        Retry ComicVine search for comics with publisher='Unknown' that haven't been searched yet.
        Updates metadata (description, publisher, cover, etc.) if found.
        """
        from app.services.comic_service import translate_comic_title
        from app.services.comicvine import get_comicvine_service
        from sqlalchemy import and_, or_

        comics = db.query(Comic).filter(
            and_(
                Comic.monitored == True,
                Comic.comicvine_search_attempted == False,
                or_(
                    Comic.publisher == "Unknown",
                    Comic.publisher == None,
                    Comic.comicvine_id == None
                )
            )
        ).limit(5).all()

        if not comics:
            return

        comicvine = get_comicvine_service()
        logger.info(f"Enriching metadata for {len(comics)} comics with missing ComicVine data")

        for comic in comics:
            try:
                translated = translate_comic_title(comic.title)

                # Try multiple queries
                search_queries = []
                if translated.lower() != comic.title.lower():
                    search_queries.append(translated)
                search_queries.append(comic.title)

                # Fuzzy: first 2-3 significant words
                skip_words = {'el', 'la', 'los', 'las', 'de', 'del', 'the', 'a', 'an', 'of', 'en', 'y', 'and'}
                words = [w for w in translated.split() if w.lower() not in skip_words]
                if len(words) >= 2:
                    fuzzy = ' '.join(words[:3])
                    if fuzzy.lower() not in [q.lower() for q in search_queries]:
                        search_queries.append(fuzzy)

                found = False
                for query in search_queries:
                    logger.info(f"ComicVine enrichment: searching '{query}' for comic '{comic.title}'")
                    result = await comicvine.search_volumes(query, page=1, per_page=5)

                    if result.get('results'):
                        for cv_result in result['results'][:3]:
                            details = await comicvine.get_volume(cv_result['comicvine_id'])
                            if details:
                                comic.comicvine_id = details['comicvine_id']
                                comic.title_original = details.get('title')
                                comic.description = details.get('description') or comic.description
                                comic.publisher = details.get('publisher') or comic.publisher
                                comic.start_year = details.get('start_year') or comic.start_year
                                comic.writers = details.get('writers') or comic.writers
                                comic.artists = details.get('artists') or comic.artists
                                comic.comicvine_url = details.get('comicvine_url')
                                if not comic.cover_image and details.get('cover_image'):
                                    comic.cover_image = details['cover_image']
                                found = True
                                logger.info(f"Enriched '{comic.title}' with ComicVine: {details['title']} ({details.get('publisher', 'N/A')})")
                                break
                    if found:
                        break

                comic.comicvine_search_attempted = True
                db.commit()

                await asyncio.sleep(1)  # Rate limit

            except Exception as e:
                logger.error(f"Error enriching metadata for '{comic.title}': {e}")
                comic.comicvine_search_attempted = True
                db.commit()

    def _mark_bundled_chapters_downloaded(
        self, db: Session, manga_id: int, download_url: str, file_path: str, exclude_chapter_id: int
    ):
        """
        Marca todos los capítulos que comparten el mismo download_url como descargados.
        Esto sucede cuando un archivo contiene múltiples tomos (ej: Gantz Tomos 1-4).

        Args:
            db: Database session
            manga_id: ID del manga
            download_url: URL de descarga compartida
            file_path: Path al archivo descargado
            exclude_chapter_id: ID del capítulo que ya fue marcado (para evitar duplicar)
        """
        try:
            # Buscar otros capítulos del mismo manga con el mismo download_url
            related_chapters = db.query(Chapter).filter(
                and_(
                    Chapter.manga_id == manga_id,
                    Chapter.download_url == download_url,
                    Chapter.id != exclude_chapter_id,
                    Chapter.status == 'pending'
                )
            ).all()

            if related_chapters:
                logger.info(f"Marking {len(related_chapters)} bundled chapters as downloaded")

                for ch in related_chapters:
                    ch.status = 'downloaded'
                    ch.file_path = file_path  # Mismo archivo para todos
                    ch.downloaded_at = datetime.utcnow()

                    # Eliminar de la cola de descargas si estaba pendiente
                    db.query(DownloadQueue).filter(
                        and_(
                            DownloadQueue.chapter_id == ch.id,
                            DownloadQueue.status == 'queued'
                        )
                    ).delete()

                db.commit()
                logger.info(f"Bundled chapters marked: {[ch.number for ch in related_chapters]}")

        except Exception as e:
            logger.error(f"Error marking bundled chapters: {e}")

    def _select_best_download_link(self, links: list) -> str:
        """Selecciona el mejor enlace de descarga según prioridad usando host_manager"""
        if not links:
            return ""

        try:
            from app.services.host_manager import select_best_links
            best_links = select_best_links(links, max_links=1)
            if best_links:
                return best_links[0].get('url', '')
        except ImportError:
            pass

        # Fallback: prioridad manual si host_manager no está disponible
        priority = {
            'Fireload': 1,
            'MediaFire': 2,
            'MEGA': 3,
            'Google Drive': 4,
            '1fichier': 5,
        }

        sorted_links = sorted(
            links,
            key=lambda x: priority.get(x.get('host', ''), 99)
        )

        return sorted_links[0]['url'] if sorted_links else ""

    async def process_download_queue(self):
        """Procesa la cola de descargas pendientes"""
        logger.debug("Processing download queue...")

        db: Session = SessionLocal()
        try:
            # Obtener elementos en cola (limitar a 3 descargas simultáneas)
            pending = db.query(DownloadQueue).filter(
                DownloadQueue.status == 'queued'
            ).order_by(
                DownloadQueue.priority.desc(),
                DownloadQueue.created_at
            ).limit(3).all()

            if not pending:
                return

            logger.info(f"Processing {len(pending)} downloads")

            # Procesar descargas
            tasks = []
            for item in pending:
                tasks.append(self._process_download(item.id))

            await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            logger.error(f"Error in process_download_queue: {e}")
        finally:
            db.close()

    async def _process_download(self, queue_id: int):
        """Procesa una descarga individual (manga o libro)"""
        db: Session = SessionLocal()
        try:
            item = db.query(DownloadQueue).filter(DownloadQueue.id == queue_id).first()
            if not item:
                return

            # Determinar tipo de contenido
            content_type = item.content_type or 'manga'

            if content_type == 'manga':
                await self._process_manga_download(db, item)
            elif content_type == 'book':
                await self._process_book_download(db, item)
            elif content_type == 'comic':
                await self._process_comic_download(db, item)
            else:
                logger.error(f"Unknown content_type: {content_type}")
                item.status = 'failed'
                item.error_message = f"Unknown content type: {content_type}"
                db.commit()

        except Exception as e:
            logger.error(f"Error in _process_download: {e}")
            if item:
                item.status = 'failed'
                item.error_message = str(e)
                item.retry_count += 1
                db.commit()
        finally:
            db.close()

    async def _process_manga_download(self, db: Session, item: DownloadQueue):
        """Procesa una descarga de manga"""
        chapter = db.query(Chapter).filter(Chapter.id == item.chapter_id).first()
        if not chapter:
            item.status = 'failed'
            item.error_message = "Chapter not found"
            db.commit()
            return

        manga = db.query(Manga).filter(Manga.id == chapter.manga_id).first()
        if not manga:
            item.status = 'failed'
            item.error_message = "Manga not found"
            db.commit()
            return

        # Actualizar estado
        item.status = 'downloading'
        item.started_at = datetime.utcnow()
        chapter.status = 'downloading'
        db.commit()

        logger.info(f"Downloading manga: {manga.title} - Chapter {chapter.number}")

        # Callback de progreso
        async def on_progress(downloaded, total):
            if total > 0:
                progress = int((downloaded / total) * 100)
                item.progress = progress
                item.bytes_downloaded = downloaded
                item.total_bytes = total
                db.commit()

        # Generar nombre de archivo
        filename = f"{manga.slug}_ch{chapter.number:05.1f}.cbz"

        # Construir lista de backup URLs si existen
        backup_urls = [chapter.backup_url] if chapter.backup_url else None

        # Descargar con sistema de fallback
        file_path = await self.downloader.download_chapter(
            url=chapter.download_url,
            filename=filename,
            on_progress=on_progress,
            backup_urls=backup_urls
        )

        if file_path and file_path.exists():
            # Éxito
            item.status = 'completed'
            item.completed_at = datetime.utcnow()
            item.progress = 100
            chapter.status = 'downloaded'
            chapter.file_path = str(file_path)
            chapter.downloaded_at = datetime.utcnow()

            # Guardar metadatos para ComicInfo.xml
            self._save_manga_metadata(manga, chapter, file_path)

            # Si este capítulo está en un paquete con otros tomos, marcarlos también
            if chapter.is_bundled and chapter.download_url:
                self._mark_bundled_chapters_downloaded(
                    db, manga.id, chapter.download_url, str(file_path), chapter.id
                )

            logger.info(f"Download completed: {filename}")
        else:
            # Fallo
            item.status = 'failed'
            item.retry_count += 1
            item.error_message = "Download failed"
            chapter.status = 'error'
            logger.error(f"Download failed: {filename}")

        db.commit()

    async def _process_book_download(self, db: Session, item: DownloadQueue):
        """Procesa una descarga de libro"""
        book_chapter = db.query(BookChapter).filter(BookChapter.id == item.book_chapter_id).first()
        if not book_chapter:
            item.status = 'failed'
            item.error_message = "Book chapter not found"
            db.commit()
            return

        book = db.query(Book).filter(Book.id == book_chapter.book_id).first()
        if not book:
            item.status = 'failed'
            item.error_message = "Book not found"
            db.commit()
            return

        # Actualizar estado
        item.status = 'downloading'
        item.started_at = datetime.utcnow()
        book_chapter.status = 'downloading'
        db.commit()

        logger.info(f"Downloading book: {book.title} - {book_chapter.title or 'Chapter ' + str(book_chapter.number)}")

        # Callback de progreso
        async def on_progress(downloaded, total):
            if total > 0:
                progress = int((downloaded / total) * 100)
                item.progress = progress
                item.bytes_downloaded = downloaded
                item.total_bytes = total
                db.commit()

        # Generar nombre de archivo
        filename = f"{book.slug}.epub"
        if book_chapter.number > 1:
            filename = f"{book.slug}_vol{book_chapter.number}.epub"

        # Construir lista de backup URLs si existen
        backup_urls = [book_chapter.backup_url] if book_chapter.backup_url else None

        # Check if URL needs Playwright (antupload, etc)
        needs_playwright = 'antupload.com' in book_chapter.download_url.lower()

        if needs_playwright:
            # Use Playwright for antupload downloads
            logger.info(f"Using Playwright for antupload download: {book_chapter.download_url}")
            from app.services.book_scrapers.playwright_scraper import get_playwright_scraper

            playwright_scraper = await get_playwright_scraper()
            page = await playwright_scraper._create_page()

            try:
                # Navigate to antupload page
                await page.goto(book_chapter.download_url, wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(2)

                # Find #downloadB button
                download_btn = await page.query_selector('#downloadB')
                if download_btn:
                    btn_href = await download_btn.get_attribute('href')
                    logger.info(f"Found #downloadB button with href: {btn_href}")

                    # Click and capture download
                    async with page.expect_download(timeout=30000) as download_info:
                        await download_btn.click()

                    download = await download_info.value

                    # Save file
                    download_dir = Path(self.book_downloader.download_dir)
                    download_dir.mkdir(parents=True, exist_ok=True)
                    file_path = download_dir / filename

                    await download.save_as(str(file_path))
                    logger.info(f"✅ Download captured and saved: {file_path}")
                else:
                    logger.error("Could not find #downloadB button")
                    file_path = None
            except Exception as e:
                logger.error(f"Playwright download failed: {e}")
                file_path = None
            finally:
                await page.close()
        else:
            # Use regular downloader for other hosts
            file_path = await self.book_downloader.download_book(
                url=book_chapter.download_url,
                filename=filename,
                on_progress=on_progress,
                backup_urls=backup_urls
            )

        if file_path and file_path.exists():
            # Éxito
            item.status = 'completed'
            item.completed_at = datetime.utcnow()
            item.progress = 100
            book_chapter.status = 'downloaded'
            book_chapter.file_path = str(file_path)
            book_chapter.downloaded_at = datetime.utcnow()

            # Obtener tamaño del archivo
            book_chapter.file_size = file_path.stat().st_size

            logger.info(f"Download completed: {filename}")
        else:
            # Fallo
            item.status = 'failed'
            item.retry_count += 1
            item.error_message = "Download failed"
            book_chapter.status = 'error'
            logger.error(f"Download failed: {filename}")

        db.commit()

    async def _process_comic_download(self, db: Session, item: DownloadQueue):
        """Procesa una descarga de comic issue via DownloadQueue"""
        from app.services.comic_service import download_comic_issue

        issue = db.query(ComicIssue).filter(ComicIssue.id == item.comic_issue_id).first()
        if not issue:
            item.status = 'failed'
            item.error_message = "Comic issue not found"
            db.commit()
            return

        comic = db.query(Comic).filter(Comic.id == issue.comic_id).first()
        if not comic:
            item.status = 'failed'
            item.error_message = "Comic not found"
            db.commit()
            return

        # Update queue status
        item.status = 'downloading'
        item.started_at = datetime.utcnow()
        db.commit()

        issue_num = issue.issue_number or "?"
        logger.info(f"Downloading comic: {comic.title} - Issue #{issue_num}")

        # Call the existing download function (manages its own DB session)
        await download_comic_issue(issue.id)

        # Reload issue to check result
        db.refresh(issue)

        if issue.status == 'downloaded':
            item.status = 'completed'
            item.completed_at = datetime.utcnow()
            item.progress = 100
            logger.info(f"Comic download completed: {comic.title} Issue #{issue_num}")
        else:
            item.status = 'failed'
            item.error_message = issue.error_message or "Download failed"
            item.retry_count += 1
            logger.error(f"Comic download failed: {comic.title} Issue #{issue_num}")

        db.commit()

    async def process_conversions(self):
        """
        Procesa conversiones de CBZ a EPUB.

        El KCC Worker container maneja la conversión real de archivos.
        Este método:
        1. Detecta cuando el KCC Worker ha completado la conversión
        2. Actualiza el estado en la DB
        3. Si KCC Worker no está disponible, usa conversión local como fallback
        """
        logger.debug("Processing conversions...")

        db: Session = SessionLocal()
        try:
            # Obtener capítulos de manga descargados no convertidos
            chapters = db.query(Chapter).filter(
                Chapter.status.in_(['downloaded', 'converting'])
            ).limit(10).all()

            if chapters:
                logger.info(f"Checking conversion status for {len(chapters)} manga chapters")
                for chapter in chapters:
                    await self._check_or_convert_chapter(chapter.id)

            # Obtener issues de comics descargados no convertidos
            comic_issues = db.query(ComicIssue).filter(
                ComicIssue.status.in_(['downloaded', 'converting'])
            ).limit(10).all()

            if comic_issues:
                logger.info(f"Checking conversion status for {len(comic_issues)} comic issues")
                for issue in comic_issues:
                    await self._check_or_convert_comic_issue(issue.id)

        except Exception as e:
            logger.error(f"Error in process_conversions: {e}")
        finally:
            db.close()

    async def _check_or_convert_chapter(self, chapter_id: int):
        """
        Verifica si el capítulo ya fue convertido por KCC Worker,
        o lo convierte usando el servicio local como fallback.

        Soporta archivos divididos en partes (ej: "Tomo 001 - Parte 1.mobi").
        """
        db: Session = SessionLocal()
        try:
            chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
            if not chapter:
                return

            manga = db.query(Manga).filter(Manga.id == chapter.manga_id).first()
            if not manga:
                return

            # Buscar archivo convertido en /library/kindle (output del KCC Worker)
            kindle_dir = Path(self.converter.output_dir)

            # Extraer número de tomo/capítulo
            chapter_num = int(chapter.number) if chapter.number == int(chapter.number) else chapter.number

            # Buscar archivos convertidos que coincidan con el manga y número
            # El KCC Worker puede crear nombres como:
            # - "One Piece - Tomo 111 (#1122-1133).epub"
            # - "berserk - Tomo 001 - Parte 1.mobi"
            # - "berserk - Tomo 001 - Parte 2.mobi"
            manga_name_lower = manga.title.lower().replace(' ', '')
            manga_slug_lower = manga.slug.lower().replace('-', '') if manga.slug else ''

            import re

            # Buscar TODOS los archivos convertidos (epub y mobi)
            converted_files = []

            for ext in ['*.epub', '*.mobi']:
                for conv_file in kindle_dir.glob(ext):
                    file_name = conv_file.stem  # Mantener mayúsculas para mejor matching
                    file_name_lower = file_name.lower().replace(' ', '').replace('-', '')

                    # Verificar si contiene el nombre del manga (o slug)
                    manga_match = (
                        manga_name_lower in file_name_lower or
                        manga_slug_lower in file_name_lower or
                        file_name_lower.startswith(manga_slug_lower) if manga_slug_lower else False
                    )

                    if not manga_match:
                        continue

                    # Buscar el ÚLTIMO número de tomo en el nombre del archivo
                    # Esto es importante para archivos como "gantz - Tomo 007 - Tomo 012.epub"
                    # donde 007 es el bundle y 012 es el tomo real
                    all_tomo_matches = list(re.finditer(r'tomo\s*(\d+)', file_name_lower))
                    
                    if all_tomo_matches:
                        # Tomar el último match (el número de tomo real)
                        last_match = all_tomo_matches[-1]
                        file_tomo_num = int(last_match.group(1))
                        
                        if file_tomo_num == chapter_num:
                            converted_files.append(conv_file)
                            continue
                    
                    # Fallback: buscar patrones alternativos
                    alt_patterns = [
                        rf'chapter\s*0*{chapter_num}(?:\D|$)',
                        rf'ch\s*0*{chapter_num}(?:\D|$)',
                        rf'parte\s*0*{chapter_num}(?:\D|$)',  # Para archivos divididos por partes
                    ]

                    for pattern in alt_patterns:
                        if re.search(pattern, file_name_lower):
                            converted_files.append(conv_file)
                            break

            # Ordenar archivos para mantener el orden de las partes
            # Los archivos pueden tener "Parte 1", "Parte 2", etc.
            def extract_part_number(f):
                match = re.search(r'parte\s*(\d+)', f.name.lower())
                return int(match.group(1)) if match else 0

            converted_files.sort(key=lambda f: (f.name.lower(), extract_part_number(f)))

            # Si encontramos archivos convertidos, actualizar DB
            if converted_files:
                chapter.status = 'converted'
                # Guardar todas las rutas separadas por '|' para archivos divididos
                chapter.converted_path = '|'.join(str(f) for f in converted_files)
                chapter.converted_at = datetime.utcnow()
                db.commit()

                if len(converted_files) == 1:
                    logger.info(f"Found converted file: {converted_files[0].name} for {manga.title} Ch {chapter_num}")
                else:
                    logger.info(f"Found {len(converted_files)} converted parts for {manga.title} Ch {chapter_num}: {[f.name for f in converted_files]}")
                return

            # Si no hay archivo convertido, verificar si el fuente existe
            if chapter.file_path:
                input_file = Path(chapter.file_path)

                if not input_file.exists():
                    # El archivo fuente fue procesado y eliminado por KCC Worker
                    # pero no encontramos el convertido - puede estar en proceso
                    if chapter.status == 'downloaded':
                        logger.info(f"Source file processed, waiting for conversion output: {input_file.name}")
                        chapter.status = 'converting'
                        db.commit()
                    return

                # Archivo fuente existe pero no hay convertido:
                # Marcar como 'converting' y esperar a KCC Worker
                if chapter.status == 'downloaded':
                    chapter.status = 'converting'
                    db.commit()
                    logger.info(f"Waiting for KCC Worker to convert: {input_file.name}")
                    return

            # Si lleva mucho tiempo en 'converting', marcar como error
            if chapter.status == 'converting':
                time_in_converting = datetime.utcnow() - (chapter.downloaded_at or datetime.utcnow())
                if time_in_converting.total_seconds() > 3600:  # 1 hora
                    logger.error(f"Conversion timeout for {manga.title} Ch {chapter_num}")
                    chapter.status = 'error'
                    chapter.error_message = "Conversion timeout - check KCC Worker"
                    db.commit()

        except Exception as e:
            logger.error(f"Error in _check_or_convert_chapter: {e}")
        finally:
            db.close()

    async def _check_or_convert_comic_issue(self, issue_id: int):
        """
        Verifica si el issue de comic ya fue convertido por KCC Worker.
        Soporta archivos divididos en partes (ej: "Comic - Issue 001 - Parte 1.epub").
        """
        db: Session = SessionLocal()
        try:
            issue = db.query(ComicIssue).filter(ComicIssue.id == issue_id).first()
            if not issue:
                return

            comic = db.query(Comic).filter(Comic.id == issue.comic_id).first()
            if not comic:
                return

            # Buscar archivo convertido en /library/kindle (output del KCC Worker)
            kindle_dir = Path(self.converter.output_dir)

            # Extraer número de issue
            issue_num = issue.issue_number or "1"
            try:
                issue_num_int = int(float(issue_num))
            except (ValueError, TypeError):
                issue_num_int = 1

            # Crear patrones de nombre basados en el comic y issue
            # Nombres posibles:
            # - "Batman - Issue 001.epub"
            # - "Batman - Issue 001 - Parte 1.epub"
            # - "Spider-Man - Issue 042.epub"
            comic_name_lower = comic.title.lower().replace(' ', '').replace('-', '')
            comic_slug_lower = comic.slug.lower().replace('-', '') if comic.slug else ''

            import re

            # Buscar archivos convertidos (epub y mobi)
            converted_files = []

            for ext in ['*.epub', '*.mobi']:
                for conv_file in kindle_dir.glob(ext):
                    file_name = conv_file.stem
                    file_name_lower = file_name.lower().replace(' ', '').replace('-', '')

                    # Verificar si contiene el nombre del comic
                    comic_match = (
                        comic_name_lower in file_name_lower or
                        comic_slug_lower in file_name_lower or
                        (file_name_lower.startswith(comic_slug_lower) if comic_slug_lower else False)
                    )

                    if not comic_match:
                        continue

                    # Buscar número de issue en el nombre del archivo
                    # Patterns: "Issue 001", "Issue001", "#001", "001"
                    issue_patterns = [
                        rf'issue\s*0*{issue_num_int}(?:\D|$)',
                        rf'#\s*0*{issue_num_int}(?:\D|$)',
                        rf'(?:^|\D)0*{issue_num_int}(?:\D|$)',
                    ]

                    for pattern in issue_patterns:
                        if re.search(pattern, file_name_lower):
                            converted_files.append(conv_file)
                            break

            # Ordenar archivos para mantener el orden de las partes
            def extract_part_number(f):
                match = re.search(r'parte\s*(\d+)', f.name.lower())
                return int(match.group(1)) if match else 0

            converted_files.sort(key=lambda f: (f.name.lower(), extract_part_number(f)))

            # Si encontramos archivos convertidos, actualizar DB
            if converted_files:
                issue.status = 'converted'
                issue.converted_path = '|'.join(str(f) for f in converted_files)
                issue.converted_at = datetime.utcnow()
                db.commit()

                if len(converted_files) == 1:
                    logger.info(f"Found converted file: {converted_files[0].name} for {comic.title} Issue {issue_num}")
                else:
                    logger.info(f"Found {len(converted_files)} converted parts for {comic.title} Issue {issue_num}")
                return

            # Si no hay archivo convertido, verificar si el fuente existe
            if issue.file_path:
                input_file = Path(issue.file_path)

                if not input_file.exists():
                    # El archivo fuente fue procesado por KCC Worker
                    if issue.status == 'downloaded':
                        logger.info(f"Source file processed, waiting for conversion output: {input_file.name}")
                        issue.status = 'converting'
                        db.commit()
                    return

                # Archivo fuente existe pero no hay convertido:
                # Marcar como 'converting' y esperar a KCC Worker
                if issue.status == 'downloaded':
                    issue.status = 'converting'
                    db.commit()
                    logger.info(f"Waiting for KCC Worker to convert: {input_file.name}")
                    return

            # Si lleva mucho tiempo en 'converting', marcar como error
            if issue.status == 'converting':
                time_in_converting = datetime.utcnow() - (issue.downloaded_at or datetime.utcnow())
                if time_in_converting.total_seconds() > 3600:  # 1 hora
                    logger.error(f"Conversion timeout for {comic.title} Issue {issue_num}")
                    issue.status = 'error'
                    issue.error_message = "Conversion timeout - check KCC Worker"
                    db.commit()

        except Exception as e:
            logger.error(f"Error in _check_or_convert_comic_issue: {e}")
        finally:
            db.close()

    async def _convert_chapter_local(self, chapter_id: int):
        """Convierte un capítulo usando KCC local (fallback)"""
        db: Session = SessionLocal()
        try:
            chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
            if not chapter or not chapter.file_path:
                return

            input_file = Path(chapter.file_path)

            if not input_file.exists():
                logger.error(f"Source file not found for local conversion: {input_file}")
                chapter.status = 'error'
                chapter.error_message = "Source file not found"
                db.commit()
                return

            logger.info(f"Local conversion: {input_file.name}")

            # Ejecutar conversión en thread pool (KCC es síncrono)
            loop = asyncio.get_event_loop()
            output_file = await loop.run_in_executor(
                None,
                self.converter.optimize_for_manga,
                input_file,
                "KPW5"
            )

            if output_file and output_file.exists():
                chapter.status = 'converted'
                chapter.converted_path = str(output_file)
                chapter.converted_at = datetime.utcnow()
                logger.info(f"Local conversion completed: {output_file.name}")
            else:
                chapter.status = 'error'
                chapter.error_message = "Conversion failed"
                logger.error(f"Local conversion failed: {input_file.name}")

            db.commit()

        except Exception as e:
            logger.error(f"Error in _convert_chapter_local: {e}")
            if chapter:
                chapter.status = 'error'
                chapter.error_message = str(e)
                db.commit()
        finally:
            db.close()

    async def send_to_kindle(self):
        """Envía archivos convertidos al Kindle via STK (por usuario)"""
        logger.debug("Checking for files to send to Kindle...")

        db: Session = SessionLocal()
        try:
            from app.models.user import User

            # Obtener capítulos de manga convertidos no enviados, agrupados por usuario
            chapters = db.query(Chapter).filter(
                Chapter.status == 'converted'
            ).limit(6).all()

            for chapter in chapters:
                manga = chapter.manga
                if not manga:
                    continue
                user = db.query(User).filter(User.id == manga.user_id).first()
                if not user or not user.auto_send_to_kindle or not user.stk_device_serial:
                    continue
                await self._send_chapter_to_kindle(chapter.id, user)

            # Obtener issues de comic convertidos no enviados
            comic_issues = db.query(ComicIssue).filter(
                ComicIssue.status == 'converted'
            ).limit(6).all()

            for issue in comic_issues:
                comic = issue.comic
                if not comic:
                    continue
                user = db.query(User).filter(User.id == comic.user_id).first()
                if not user or not user.auto_send_to_kindle or not user.stk_device_serial:
                    continue
                await self._send_comic_issue_to_kindle(issue.id, user)

        except Exception as e:
            logger.error(f"Error in send_to_kindle: {e}")
        finally:
            db.close()

    async def _send_chapter_to_kindle(self, chapter_id: int, user):
        """
        Envía un capítulo individual al Kindle usando el STK del usuario.
        Soporta archivos divididos en partes (rutas separadas por '|' en converted_path).
        """
        db: Session = SessionLocal()
        try:
            chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
            if not chapter or not chapter.converted_path:
                return

            manga = db.query(Manga).filter(Manga.id == chapter.manga_id).first()
            if not manga:
                return

            # Manejar múltiples archivos (partes) separados por '|'
            file_paths = [Path(p.strip()) for p in chapter.converted_path.split('|') if p.strip()]

            # Verificar que todos los archivos existen
            missing_files = [f for f in file_paths if not f.exists()]
            if missing_files:
                logger.error(f"Converted files not found: {[str(f) for f in missing_files]}")
                return

            if len(file_paths) > 1:
                logger.info(f"Sending {len(file_paths)} parts for {manga.title} Ch {int(chapter.number)}")

            stk_sender = get_stk_sender(user.id)
            if not stk_sender.is_authenticated():
                logger.error(f"STK not authenticated for user {user.id}")
                return

            all_success = True
            for idx, file_path in enumerate(file_paths):
                file_size_mb = file_path.stat().st_size / (1024 * 1024)
                part_info = f" (Part {idx + 1}/{len(file_paths)})" if len(file_paths) > 1 else ""
                logger.info(f"Sending to Kindle via STK: {file_path.name}{part_info} ({file_size_mb:.1f}MB)")

                result = stk_sender.send_file(
                    file_path=file_path,
                    device_serials=[user.stk_device_serial] if user.stk_device_serial else None
                )

                if result.get('success'):
                    logger.info(f"Sent via STK: {file_path.name}")
                else:
                    logger.error(f"Failed to send via STK: {file_path.name} — {result.get('message')}")
                    all_success = False

            # Marcar como enviado solo si todas las partes se enviaron correctamente
            if all_success:
                chapter.status = 'sent'
                chapter.sent_at = datetime.utcnow()
                logger.info(f"Successfully sent all parts to Kindle for {manga.title} Ch {int(chapter.number)}")
            else:
                logger.error(f"Some parts failed to send for {manga.title} Ch {int(chapter.number)}")

            db.commit()

        except Exception as e:
            logger.error(f"Error in _send_chapter_to_kindle: {e}")
        finally:
            db.close()

    async def _send_comic_issue_to_kindle(self, issue_id: int, user):
        """
        Envía un issue de comic al Kindle usando el STK del usuario.
        Soporta archivos divididos en partes (rutas separadas por '|' en converted_path).
        """
        db: Session = SessionLocal()
        try:
            issue = db.query(ComicIssue).filter(ComicIssue.id == issue_id).first()
            if not issue or not issue.converted_path:
                return

            comic = db.query(Comic).filter(Comic.id == issue.comic_id).first()
            if not comic:
                return

            # Manejar múltiples archivos (partes) separados por '|'
            file_paths = [Path(p.strip()) for p in issue.converted_path.split('|') if p.strip()]

            # Verificar que todos los archivos existen
            missing_files = [f for f in file_paths if not f.exists()]
            if missing_files:
                logger.error(f"Converted files not found: {[str(f) for f in missing_files]}")
                return

            issue_num = issue.issue_number or "?"
            if len(file_paths) > 1:
                logger.info(f"Sending {len(file_paths)} parts for {comic.title} Issue {issue_num}")

            stk_sender = get_stk_sender(user.id)
            if not stk_sender.is_authenticated():
                logger.error(f"STK not authenticated for user {user.id}")
                return

            all_success = True
            for idx, file_path in enumerate(file_paths):
                file_size_mb = file_path.stat().st_size / (1024 * 1024)
                part_info = f" (Part {idx + 1}/{len(file_paths)})" if len(file_paths) > 1 else ""
                logger.info(f"Sending to Kindle via STK: {file_path.name}{part_info} ({file_size_mb:.1f}MB)")

                result = stk_sender.send_file(
                    file_path=file_path,
                    device_serials=[user.stk_device_serial] if user.stk_device_serial else None
                )

                if result.get('success'):
                    logger.info(f"Sent via STK: {file_path.name}")
                else:
                    logger.error(f"Failed to send via STK: {file_path.name} — {result.get('message')}")
                    all_success = False

            # Marcar como enviado solo si todas las partes se enviaron correctamente
            if all_success:
                issue.status = 'sent'
                issue.sent_at = datetime.utcnow()
                logger.info(f"Successfully sent all parts to Kindle for {comic.title} Issue {issue_num}")
            else:
                logger.error(f"Some parts failed to send for {comic.title} Issue {issue_num}")

            db.commit()

        except Exception as e:
            logger.error(f"Error in _send_comic_issue_to_kindle: {e}")
        finally:
            db.close()

    async def retry_failed_downloads(self):
        """Reintenta descargas fallidas"""
        logger.debug("Retrying failed downloads...")

        db: Session = SessionLocal()
        try:
            # Obtener descargas fallidas que pueden reintentarse
            failed = db.query(DownloadQueue).filter(
                and_(
                    DownloadQueue.status == 'failed',
                    DownloadQueue.retry_count < DownloadQueue.max_retries
                )
            ).all()

            if not failed:
                return

            logger.info(f"Retrying {len(failed)} failed downloads")

            for item in failed:
                item.status = 'queued'
                db.commit()

        except Exception as e:
            logger.error(f"Error in retry_failed_downloads: {e}")
        finally:
            db.close()

    async def cleanup_old_files(self):
        """Limpia archivos descargados de más de X días"""
        logger.info("Cleaning up old files...")

        db: Session = SessionLocal()
        try:
            # Archivos de más de 7 días
            cutoff_date = datetime.utcnow() - timedelta(days=7)

            old_chapters = db.query(Chapter).filter(
                and_(
                    Chapter.sent_at is not None,
                    Chapter.sent_at < cutoff_date
                )
            ).all()

            cleaned_count = 0
            for chapter in old_chapters:
                # Eliminar archivos físicos
                if chapter.file_path:
                    file_path = Path(chapter.file_path)
                    if file_path.exists():
                        file_path.unlink()
                        cleaned_count += 1

                if chapter.converted_path:
                    converted_path = Path(chapter.converted_path)
                    if converted_path.exists():
                        converted_path.unlink()
                        cleaned_count += 1

                # Actualizar DB (opcional: eliminar registros o solo paths)
                chapter.file_path = None
                chapter.converted_path = None

            db.commit()
            logger.info(f"Cleaned up {cleaned_count} old files")

        except Exception as e:
            logger.error(f"Error in cleanup_old_files: {e}")
        finally:
            db.close()

    def get_status(self) -> dict:
        """Obtiene estado del scheduler"""
        jobs = self.scheduler.get_jobs()

        return {
            'running': self.is_running,
            'jobs': [
                {
                    'id': job.id,
                    'next_run': job.next_run_time.isoformat() if job.next_run_time else None
                }
                for job in jobs
            ],
            'active_downloads': len(self.active_downloads)
        }

    def _save_manga_metadata(self, manga: Manga, chapter: Chapter, file_path: Path):
        """
        Guarda metadatos del manga como JSON junto al archivo descargado.
        El converter usará estos datos para generar ComicInfo.xml.
        """
        import json

        try:
            metadata_path = file_path.with_suffix('.metadata.json')

            # Construir diccionario de metadatos
            metadata = {
                'title': manga.title,
                'title_romaji': manga.title_romaji,
                'title_english': manga.title_english,
                'title_native': manga.title_native,
                'description': manga.description,
                'authors': manga.authors or [],
                'artists': manga.artists or [],
                'genres': manga.genres or [],
                'tags': [t['name'] if isinstance(t, dict) else t for t in (manga.tags or [])],
                'status': manga.status,
                'start_date': manga.start_date,
                'end_date': manga.end_date,
                'average_score': manga.average_score,
                'anilist_url': manga.anilist_url,
                'anilist_id': manga.anilist_id,
                'country': manga.country,
                'is_adult': getattr(manga, 'is_adult', False),
                # Info del capítulo/tomo
                'volume_number': int(chapter.number),
                'chapter_title': chapter.title,
            }

            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)

            logger.info(f"Metadata saved: {metadata_path}")

        except Exception as e:
            logger.warning(f"Could not save metadata for {file_path}: {e}")


# Singleton instance
_scheduler_instance: ContentScheduler = None


def set_scheduler(scheduler: ContentScheduler):
    """Set the global scheduler instance"""
    global _scheduler_instance
    _scheduler_instance = scheduler


def get_scheduler() -> ContentScheduler:
    """Get the global scheduler instance"""
    global _scheduler_instance
    return _scheduler_instance
