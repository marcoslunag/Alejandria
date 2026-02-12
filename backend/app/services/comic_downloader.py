"""
Comic Downloader Service
Downloads CBR/CBZ files from various hosts
Reuses the existing MangaDownloader infrastructure
"""

import logging
import zipfile
from pathlib import Path

# rarfile is optional - CBR verification will be skipped if not installed
try:
    import rarfile
    RARFILE_AVAILABLE = True
except ImportError:
    RARFILE_AVAILABLE = False
    logging.warning("rarfile module not installed - CBR verification disabled")
from typing import Optional, Callable, List
from app.services.downloader import MangaDownloader

logger = logging.getLogger(__name__)


class ComicDownloader(MangaDownloader):
    """
    Downloader for comic files (CBR, CBZ, PDF)
    Inherits from MangaDownloader and reuses all download logic
    """

    def __init__(self, download_dir: str = "/downloads/comics"):
        """
        Initialize comic downloader

        Args:
            download_dir: Directory to save downloaded comic files
        """
        super().__init__(download_dir=download_dir)
        logger.info(f"ComicDownloader initialized with download_dir: {download_dir}")

    async def download_comic(
        self,
        url: str,
        filename: str,
        on_progress: Optional[Callable[[int, int], None]] = None,
        backup_urls: Optional[List[str]] = None
    ) -> Optional[Path]:
        """
        Download a comic file from URL with fallback support

        Args:
            url: Primary download URL
            filename: Output filename (e.g., "Spider-Man #001.cbz")
            on_progress: Progress callback (bytes_downloaded, total_bytes)
            backup_urls: List of backup URLs ordered by priority

        Returns:
            Path to downloaded file or None if failed
        """
        logger.info(f"Starting comic download: {filename}")

        # Use parent class download_chapter method (works for any file)
        result = await self.download_chapter(url, filename, on_progress, backup_urls)

        if result:
            logger.info(f"Comic download successful: {filename}")
        else:
            logger.error(f"Comic download failed: {filename}")

        return result

    def _verify_archive_integrity(self, file_path: Path) -> bool:
        """
        Verify CBR/CBZ/PDF files using magic bytes (not extension).
        MEGA and other hosts may serve RAR files with .cbz extension.
        """
        if not file_path.exists():
            return False

        if file_path.stat().st_size < 1024:
            logger.warning(f"File too small to be valid: {file_path.name}")
            return False

        # Detect actual format by magic bytes (not extension)
        actual_format = self._detect_archive_format(file_path)

        if actual_format == 'zip':
            try:
                with zipfile.ZipFile(file_path, 'r') as zf:
                    bad_file = zf.testzip()
                    if bad_file:
                        logger.error(f"Corrupted file in archive: {bad_file}")
                        return False
                    if len(zf.namelist()) == 0:
                        logger.error(f"Empty archive: {file_path.name}")
                        return False
                logger.info(f"ZIP archive verified: {file_path.name}")
                return True
            except zipfile.BadZipFile:
                logger.error(f"Invalid ZIP file: {file_path.name}")
                return False

        elif actual_format == 'rar':
            # RAR file - accept as valid (KCC converter handles RAR with 7z/unrar)
            logger.info(f"RAR archive detected (saved as {file_path.suffix}), accepting: {file_path.name}")
            return True

        # PDF check
        elif file_path.suffix.lower() == '.pdf':
            try:
                with open(file_path, 'rb') as f:
                    if f.read(5) == b'%PDF-':
                        return True
                logger.error(f"Invalid PDF: {file_path.name}")
                return False
            except Exception:
                return False

        # Unknown format - accept if decent size
        logger.warning(f"Unknown archive format for {file_path.name}, accepting based on size")
        return file_path.stat().st_size > 10240
