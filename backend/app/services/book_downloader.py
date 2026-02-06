"""
Book Downloader Service
Downloads EPUB/MOBI files from various hosts
Reuses the existing MangaDownloader infrastructure
"""

import logging
from pathlib import Path
from typing import Optional, Callable, List
from app.services.downloader import MangaDownloader

logger = logging.getLogger(__name__)


class BookDownloader(MangaDownloader):
    """
    Downloader for book files (EPUB, MOBI, AZW3, PDF)
    Inherits from MangaDownloader and reuses all download logic
    """

    def __init__(self, download_dir: str = "/downloads/books"):
        """
        Initialize book downloader

        Args:
            download_dir: Directory to save downloaded book files
        """
        super().__init__(download_dir=download_dir)
        logger.info(f"BookDownloader initialized with download_dir: {download_dir}")

    async def download_book(
        self,
        url: str,
        filename: str,
        on_progress: Optional[Callable[[int, int], None]] = None,
        backup_urls: Optional[List[str]] = None
    ) -> Optional[Path]:
        """
        Download a book file from URL with fallback support

        Args:
            url: Primary download URL
            filename: Output filename (e.g., "Book Title.epub")
            on_progress: Progress callback (bytes_downloaded, total_bytes)
            backup_urls: List of backup URLs ordered by priority

        Returns:
            Path to downloaded file or None if failed
        """
        logger.info(f"Starting book download: {filename}")

        # Use parent class download_chapter method (works for any file)
        result = await self.download_chapter(url, filename, on_progress, backup_urls)

        if result:
            logger.info(f"Book download successful: {filename}")
        else:
            logger.error(f"Book download failed: {filename}")

        return result

    def _verify_archive_integrity(self, file_path: Path) -> bool:
        """
        Override to verify EPUB/MOBI files instead of ZIP/CBZ

        Args:
            file_path: Path to the downloaded file

        Returns:
            True if file is valid
        """
        import zipfile

        if not file_path.exists():
            return False

        # Verify minimum size
        if file_path.stat().st_size < 1024:
            logger.warning(f"File too small to be valid: {file_path.name}")
            return False

        # EPUB files are ZIP archives
        if file_path.suffix.lower() in ['.epub']:
            try:
                with zipfile.ZipFile(file_path, 'r') as zf:
                    # Check for mimetype file (required in EPUB)
                    if 'mimetype' not in zf.namelist():
                        logger.error(f"Invalid EPUB: missing mimetype file")
                        return False

                    # Verify ZIP integrity
                    bad_file = zf.testzip()
                    if bad_file:
                        logger.error(f"Corrupted file in EPUB: {bad_file}")
                        return False

                    logger.debug(f"EPUB integrity verified: {file_path.name}")
                    return True
            except zipfile.BadZipFile:
                logger.error(f"Invalid EPUB file: {file_path.name}")
                return False

        # MOBI/AZW3 files - check magic bytes
        elif file_path.suffix.lower() in ['.mobi', '.azw', '.azw3']:
            try:
                with open(file_path, 'rb') as f:
                    header = f.read(100)
                    # MOBI files have specific headers
                    if b'BOOKMOBI' in header or b'TPZ' in header:
                        logger.debug(f"MOBI/AZW integrity verified: {file_path.name}")
                        return True
                    else:
                        logger.error(f"Invalid MOBI/AZW file: missing header")
                        return False
            except Exception as e:
                logger.error(f"Error verifying MOBI/AZW: {e}")
                return False

        # PDF files
        elif file_path.suffix.lower() == '.pdf':
            try:
                with open(file_path, 'rb') as f:
                    header = f.read(10)
                    if header.startswith(b'%PDF-'):
                        logger.debug(f"PDF integrity verified: {file_path.name}")
                        return True
                    else:
                        logger.error(f"Invalid PDF file: missing header")
                        return False
            except Exception as e:
                logger.error(f"Error verifying PDF: {e}")
                return False

        # Unknown format - accept if file exists with decent size
        logger.warning(f"Unknown book format: {file_path.suffix}, accepting based on size")
        return file_path.stat().st_size > 10240  # At least 10KB
