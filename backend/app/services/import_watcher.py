"""
Import Watcher - Procesa archivos colocados en /imports
Detecta metadatos desde el nombre de archivo e integra a la biblioteca
"""

import os
import re
import shutil
import logging
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session

from app.database import SessionLocal

logger = logging.getLogger(__name__)

SUPPORTED_EXT = {'.cbz', '.cbr', '.pdf', '.epub', '.zip'}


def _detect_metadata(filename: str) -> dict:
    """
    Detecta tipo y metadatos desde el nombre de archivo.

    Patrones soportados:
    - "Series Name #01.cbz"          → comic, issue=1
    - "Series Name Vol.01.cbz"        → manga, volume=1
    - "Series Name - Chapter 01.cbz"  → manga, volume=1
    - "Author - Book Title.epub"       → book
    - "Book Title.epub"               → book (sin autor)
    """
    stem = Path(filename).stem
    ext = Path(filename).suffix.lower()

    result = {
        'filename': filename,
        'ext': ext,
        'content_type': None,
        'title': None,
        'issue_number': None,
        'volume_number': None,
        'author': None,
    }

    # "Series #01" — comic issue
    m = re.match(r'^(.+?)\s+#(\d+)', stem)
    if m:
        result['content_type'] = 'comic'
        result['title'] = m.group(1).strip()
        result['issue_number'] = int(m.group(2))
        return result

    # "Series Vol.01" or "Series Volume 01" — manga volume
    m = re.match(r'^(.+?)\s+[Vv]ol(?:ume)?\.?\s*(\d+)', stem)
    if m:
        result['content_type'] = 'manga'
        result['title'] = m.group(1).strip()
        result['volume_number'] = int(m.group(2))
        return result

    # "Series - Chapter 01" — manga chapter
    m = re.match(r'^(.+?)\s+-\s+[Cc]hapter\s+(\d+)', stem)
    if m:
        result['content_type'] = 'manga'
        result['title'] = m.group(1).strip()
        result['volume_number'] = int(m.group(2))
        return result

    # "Author - Book Title" — book with author
    if ext == '.epub' and ' - ' in stem:
        parts = stem.split(' - ', 1)
        result['content_type'] = 'book'
        result['author'] = parts[0].strip()
        result['title'] = parts[1].strip()
        return result

    # Fallback
    result['content_type'] = 'book' if ext == '.epub' else 'comic'
    result['title'] = stem
    return result


def _find_matching_series(db: Session, title: str, content_type: str):
    """Busca la serie más parecida en la BD para el tipo dado."""
    from app.models.manga import Manga
    from app.models.comic import Comic
    from app.models.book import Book

    title_lower = title.lower()
    kw_search = {w for w in title_lower.split() if len(w) > 2}

    model_map = {'manga': Manga, 'comic': Comic, 'book': Book}
    model = model_map.get(content_type)
    if not model:
        return None

    for item in db.query(model).all():
        item_lower = item.title.lower()
        if title_lower in item_lower or item_lower in title_lower:
            return item
        kw_item = {w for w in item_lower.split() if len(w) > 2}
        if kw_search and kw_item and len(kw_search & kw_item) >= min(2, len(kw_search)):
            return item

    return None


class ImportWatcher:
    """Procesa archivos colocados en /imports hacia la biblioteca."""

    def __init__(self):
        import_base = Path(os.getenv('IMPORT_DIR', '/imports'))
        self.import_dir = import_base
        self.processed_dir = import_base / 'processed'
        self.failed_dir = import_base / 'failed'

    def _ensure_dirs(self):
        for d in [self.import_dir, self.processed_dir, self.failed_dir]:
            d.mkdir(parents=True, exist_ok=True)

    async def process_import_queue(self):
        """Escanea /imports y procesa archivos pendientes."""
        self._ensure_dirs()

        pending = [
            f for f in self.import_dir.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXT
        ]

        if not pending:
            return

        logger.info(f"Import watcher: {len(pending)} archivo(s) pendientes")

        db = SessionLocal()
        try:
            for file_path in pending:
                await self._process_file(db, file_path)
        finally:
            db.close()

    async def _process_file(self, db: Session, file_path: Path):
        """Procesa un archivo individual de la carpeta /imports."""
        from app.models.chapter import Chapter
        from app.models.comic import ComicIssue
        from app.models.book_chapter import BookChapter
        from app.models.download import DownloadQueue

        filename = file_path.name
        logger.info(f"Procesando import: {filename}")

        try:
            meta = _detect_metadata(filename)
            content_type = meta['content_type']
            title = meta.get('title', filename)

            series = _find_matching_series(db, title, content_type)
            if not series:
                logger.warning(f"Import: sin coincidencia para '{title}' (tipo={content_type})")
                shutil.move(str(file_path), str(self.failed_dir / filename))
                return

            download_dir = Path(os.getenv('DOWNLOAD_DIR', '/downloads'))

            if content_type == 'manga':
                dest = download_dir / filename
                shutil.copy2(str(file_path), str(dest))
                vol = float(meta.get('volume_number') or 1)

                if not db.query(Chapter).filter(Chapter.manga_id == series.id, Chapter.number == vol).first():
                    ch = Chapter(
                        manga_id=series.id,
                        number=vol,
                        title=f"Vol. {int(vol)}",
                        status='downloaded',
                        file_path=str(dest),
                        downloaded_at=datetime.utcnow(),
                    )
                    db.add(ch)
                    db.commit()
                    db.refresh(ch)
                    db.add(DownloadQueue(
                        chapter_id=ch.id,
                        status='completed',
                        priority=5,
                        started_at=datetime.utcnow(),
                        completed_at=datetime.utcnow(),
                        progress=100,
                    ))
                    db.commit()
                    logger.info(f"Import manga: Vol.{int(vol)} para '{series.title}'")

            elif content_type == 'comic':
                dest = download_dir / filename
                shutil.copy2(str(file_path), str(dest))
                issue_num = str(meta.get('issue_number') or '1')

                if not db.query(ComicIssue).filter(ComicIssue.comic_id == series.id, ComicIssue.issue_number == issue_num).first():
                    issue = ComicIssue(
                        comic_id=series.id,
                        issue_number=issue_num,
                        status='downloaded',
                        file_path=str(dest),
                        downloaded_at=datetime.utcnow(),
                    )
                    db.add(issue)
                    db.commit()
                    db.refresh(issue)
                    db.add(DownloadQueue(
                        comic_issue_id=issue.id,
                        status='completed',
                        priority=5,
                        started_at=datetime.utcnow(),
                        completed_at=datetime.utcnow(),
                        progress=100,
                    ))
                    db.commit()
                    logger.info(f"Import comic: issue #{issue_num} para '{series.title}'")

            elif content_type == 'book':
                books_dir = download_dir / 'books'
                books_dir.mkdir(parents=True, exist_ok=True)
                dest = books_dir / filename
                shutil.copy2(str(file_path), str(dest))

                if not db.query(BookChapter).filter(BookChapter.book_id == series.id, BookChapter.number == 1).first():
                    bc = BookChapter(
                        book_id=series.id,
                        number=1,
                        title=title,
                        status='downloaded',
                        file_path=str(dest),
                        file_size=file_path.stat().st_size,
                    )
                    db.add(bc)
                    db.commit()
                    logger.info(f"Import book: '{title}' para '{series.title}'")

            shutil.move(str(file_path), str(self.processed_dir / filename))
            logger.info(f"Import OK: '{filename}'")

        except Exception as e:
            logger.error(f"Import ERROR '{filename}': {e}", exc_info=True)
            try:
                shutil.move(str(file_path), str(self.failed_dir / filename))
            except Exception:
                pass

    def get_status(self) -> dict:
        """Devuelve el estado de la carpeta /imports."""
        self._ensure_dirs()

        pending = [
            f.name for f in self.import_dir.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXT
        ]
        processed = sorted(
            [f.name for f in self.processed_dir.iterdir() if f.is_file()],
            reverse=True
        )[:20]
        failed = sorted(
            [f.name for f in self.failed_dir.iterdir() if f.is_file()],
            reverse=True
        )[:20]

        return {
            'import_dir': str(self.import_dir),
            'pending': pending,
            'pending_count': len(pending),
            'processed': processed,
            'processed_count': sum(1 for f in self.processed_dir.iterdir() if f.is_file()),
            'failed': failed,
            'failed_count': sum(1 for f in self.failed_dir.iterdir() if f.is_file()),
        }
