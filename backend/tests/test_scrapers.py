"""
Integration tests for all scrapers, downloaders, and resolvers.
These tests hit real external services and verify the scraping pipeline.
Run inside Docker: docker exec alejandria-backend pytest tests/test_scrapers.py -v
"""
import pytest
import asyncio
import aiohttp


# ============================================================================
# MANGA SCRAPERS
# ============================================================================

class TestTomosMangaScraper:
    def test_search_returns_results(self):
        from app.services.tomosmanga_search import TomosMangaSearch
        scraper = TomosMangaSearch()
        results = scraper.search("Gantz")
        assert isinstance(results, list), "Search should return a list"
        assert len(results) > 0, "Should find at least one result for 'Gantz'"
        first = results[0]
        assert "title" in first, "Result must have 'title'"
        assert "url" in first, "Result must have 'url'"
        assert "tomosmanga.com" in first["url"], "URL should be from tomosmanga.com"

    def test_search_scoring(self):
        from app.services.tomosmanga_search import TomosMangaSearch
        scraper = TomosMangaSearch()
        result = scraper.find_best_match("Gantz")
        assert result is not None, "Should find a best match for 'Gantz'"
        assert "url" in result, "Best match must have 'url'"

    def test_search_no_results(self):
        from app.services.tomosmanga_search import TomosMangaSearch
        scraper = TomosMangaSearch()
        results = scraper.search("xyznotarealmanganame123456")
        assert isinstance(results, list)
        assert len(results) == 0, "Should return empty for nonexistent manga"


class TestMangayComicsScraper:
    def test_search_returns_results(self):
        from app.services.mangaycomics_scraper import MangayComicsScraper
        scraper = MangayComicsScraper()
        results = scraper.search_manga("Naruto")
        assert isinstance(results, list), "Search should return a list"
        assert len(results) > 0, "Should find results for 'Naruto'"
        first = results[0]
        assert "title" in first, "Result must have 'title'"
        assert "url" in first, "Result must have 'url'"

    def test_search_no_results(self):
        from app.services.mangaycomics_scraper import MangayComicsScraper
        scraper = MangayComicsScraper()
        results = scraper.search_manga("xyznotarealmanganame123456")
        assert isinstance(results, list)


class TestTomosMangaDetails:
    def test_get_manga_details(self):
        from app.services.scraper import TomosMangaScraper
        scraper = TomosMangaScraper()
        details = scraper.get_manga_details("https://tomosmanga.com/descargar-gantz-e/")
        assert details is not None, "Should get details for Gantz"
        assert "title" in details, "Details must have 'title'"
        assert "chapters" in details, "Details must have 'chapters'"
        assert len(details["chapters"]) > 0, "Should have at least one chapter/volume"
        ch = details["chapters"][0]
        assert "number" in ch, "Chapter must have 'number'"


# ============================================================================
# BOOK SCRAPERS
# ============================================================================

class TestLectulandiaScraper:
    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        from app.services.book_scrapers import LectulandiaScraper
        scraper = LectulandiaScraper()
        results = await scraper.search("El principito")
        assert isinstance(results, list), "Search should return a list"
        assert len(results) > 0, "Should find results for 'El principito'"
        first = results[0]
        assert "title" in first, "Result must have 'title'"
        assert "url" in first, "Result must have 'url'"

    @pytest.mark.asyncio
    async def test_search_no_results(self):
        from app.services.book_scrapers import LectulandiaScraper
        scraper = LectulandiaScraper()
        try:
            results = await asyncio.wait_for(
                scraper.search("xyznotarealbookname123456"), timeout=60.0
            )
            assert isinstance(results, list)
            assert len(results) == 0
        except asyncio.TimeoutError:
            pytest.skip("Lectulandia search timed out (Playwright slow)")


# ============================================================================
# COMIC SCRAPERS
# ============================================================================

class TestCBRComicsScraper:
    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        from app.services.comic_scrapers.cbrcomics import CBRComicsScraper
        scraper = CBRComicsScraper()
        results = await scraper.search("Spider-Man")
        assert isinstance(results, list), "Search should return a list"
        assert len(results) > 0, "Should find results for 'Spider-Man'"
        first = results[0]
        assert "title" in first, "Result must have 'title'"
        assert "url" in first, "Result must have 'url'"

    @pytest.mark.asyncio
    async def test_get_download_links(self):
        from app.services.comic_scrapers.cbrcomics import CBRComicsScraper
        scraper = CBRComicsScraper()
        results = await scraper.search("Paper Girls")
        if results:
            result = await scraper.get_download_links(results[0]["url"])
            assert result is not None, "Should return a result object"
            assert hasattr(result, "success"), "Result must have 'success' attribute"


class TestMegaComicsScraper:
    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        from app.services.comic_scrapers.megacomics import MegaComicsScraper
        scraper = MegaComicsScraper()
        results = await scraper.search("Batman")
        assert isinstance(results, list), "Search should return a list"
        assert len(results) > 0, "Should find results for 'Batman'"


# ============================================================================
# METADATA SERVICES
# ============================================================================

class TestAniListService:
    @pytest.mark.asyncio
    async def test_search_manga(self):
        from app.services.anilist import AnilistService
        service = AnilistService()
        results = await service.search_manga("One Piece")
        assert results is not None
        assert "results" in results
        assert len(results["results"]) > 0
        first = results["results"][0]
        assert "anilist_id" in first
        assert "title" in first

    @pytest.mark.asyncio
    async def test_get_manga_by_id(self):
        from app.services.anilist import AnilistService
        service = AnilistService()
        manga = await service.get_manga_by_id(30013)  # One Piece
        assert manga is not None
        assert manga["anilist_id"] == 30013
        assert "title" in manga

    @pytest.mark.asyncio
    async def test_get_trending(self):
        from app.services.anilist import AnilistService
        service = AnilistService()
        trending = await service.get_trending_manga()
        assert isinstance(trending, list)
        assert len(trending) > 0


class TestGoogleBooksService:
    @pytest.mark.asyncio
    async def test_search_books(self):
        from app.services.google_books import get_google_books_service
        service = get_google_books_service()
        results = await service.search_books("Don Quijote")
        assert results is not None
        assert "results" in results
        assert len(results["results"]) > 0


class TestComicVineService:
    @pytest.mark.asyncio
    async def test_search_volumes(self):
        import os
        from app.services.comicvine import get_comicvine_service
        service = get_comicvine_service()
        try:
            results = await service.search_volumes("Spider-Man")
            assert results is not None
            # search_volumes may return a dict with 'results' key or a list
            if isinstance(results, dict):
                assert "results" in results
                items = results["results"]
            else:
                items = results
            assert isinstance(items, list)
            if items:
                first = items[0]
                assert "comicvine_id" in first or "title" in first or "name" in first
        except Exception as e:
            api_key = os.environ.get("COMICVINE_API_KEY", "")
            if not api_key:
                pytest.skip("COMICVINE_API_KEY not set")
            else:
                raise


# ============================================================================
# RESOLVERS
# ============================================================================

class TestOuoResolver:
    @pytest.mark.asyncio
    async def test_resolve_returns_url_or_none(self):
        from app.services.ouo_resolver import resolve_ouo_link
        # OUO.io often blocks automated requests, so we just test it doesn't crash
        result = await resolve_ouo_link("https://ouo.io/Rp8drl")
        assert result is None or isinstance(result, str)


class TestTeraBoxBypass:
    def test_get_download_link(self):
        from app.services.terabox_bypass import TeraBoxBypass
        bypass = TeraBoxBypass()
        result = bypass.get_download_link("https://terabox.com/s/1bSVBkDGAVorkQuVQdAQAuA")
        assert isinstance(result, dict)
        assert "ok" in result
        if result["ok"]:
            assert "download_link" in result
            assert result["download_link"] is not None


# ============================================================================
# DOWNLOADERS
# ============================================================================

class TestMangaDownloader:
    def test_verify_archive_zip(self, tmp_path):
        """Test ZIP archive verification"""
        import zipfile
        from app.services.downloader import MangaDownloader
        
        dl = MangaDownloader(str(tmp_path))
        
        zip_path = tmp_path / "test.cbz"
        with zipfile.ZipFile(zip_path, "w") as zf:
            # Must be > 1024 bytes to pass minimum size check
            zf.writestr("page001.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 2000)
        
        assert dl._verify_archive_integrity(zip_path) is True

    def test_verify_archive_too_small(self, tmp_path):
        """Test rejection of too-small files"""
        from app.services.downloader import MangaDownloader
        
        dl = MangaDownloader(str(tmp_path))
        small = tmp_path / "tiny.cbz"
        small.write_bytes(b"PK\x03\x04" + b"\x00" * 10)
        
        assert dl._verify_archive_integrity(small) is False

    def test_detect_archive_format(self, tmp_path):
        """Test format detection by magic bytes"""
        from app.services.downloader import MangaDownloader
        
        dl = MangaDownloader(str(tmp_path))
        
        zip_file = tmp_path / "test.zip"
        zip_file.write_bytes(b"PK\x03\x04" + b"\x00" * 1000)
        assert dl._detect_archive_format(zip_file) == "zip"
        
        rar_file = tmp_path / "test.rar"
        rar_file.write_bytes(b"Rar!\x1a\x07\x00" + b"\x00" * 1000)
        assert dl._detect_archive_format(rar_file) == "rar"

    def test_extract_gdrive_id(self):
        from app.services.downloader import MangaDownloader
        dl = MangaDownloader()
        
        assert dl._extract_gdrive_id("https://drive.google.com/file/d/1abc123/view") == "1abc123"
        assert dl._extract_gdrive_id("https://drive.google.com/uc?id=xyz789") == "xyz789"
        assert dl._extract_gdrive_id("https://example.com/no-gdrive") is None


# ============================================================================
# HOST MANAGER
# ============================================================================

class TestHostManager:
    def test_identify_host(self):
        from app.services.host_manager import identify_host
        
        assert identify_host("https://mega.nz/file/abc123") == "mega"
        assert identify_host("https://www.mediafire.com/file/abc") == "mediafire"
        assert identify_host("https://drive.google.com/file/d/123") == "google_drive"
        assert identify_host("https://terabox.com/s/abc") == "terabox"

    def test_sort_download_links(self):
        from app.services.host_manager import sort_download_links
        
        links = [
            {"url": "https://terabox.com/s/abc"},
            {"url": "https://mega.nz/file/123"},
            {"url": "https://drive.google.com/file/d/456"},
        ]
        sorted_links = sort_download_links(links)
        assert len(sorted_links) == 3
        urls = [l["url"] for l in sorted_links]
        # Google Drive should be before TeraBox
        gdrive_idx = next(i for i, u in enumerate(urls) if "google" in u)
        terabox_idx = next(i for i, u in enumerate(urls) if "terabox" in u)
        assert gdrive_idx < terabox_idx, "Google Drive should be prioritized over TeraBox"


# ============================================================================
# CONTENT MATCHER (Anti-duplicates)
# ============================================================================

class TestContentMatcher:
    def test_normalize_title(self):
        from app.services.content_matcher import ContentMatcher
        matcher = ContentMatcher()
        result = matcher.normalize("  Hello World!  ")
        assert "hello" in result
        assert "world" in result

    def test_similarity(self):
        from app.services.content_matcher import ContentMatcher
        matcher = ContentMatcher()
        score = matcher.similarity("one piece", "one piece")
        assert score >= 0.99, "Identical strings should have similarity ~1.0"
        
        score = matcher.similarity("one piece manga", "two completely different words")
        assert score < 0.8, "Different strings should have low similarity"


# ============================================================================
# TRANSLATOR
# ============================================================================

class TestTranslator:
    def test_translate_genres(self):
        """Test genre translation"""
        from app.services.translator import translate_genres
        genres = translate_genres(["Action", "Adventure", "Comedy"])
        assert isinstance(genres, list)
        assert len(genres) == 3

    def test_translate_status(self):
        """Test status translation"""
        from app.services.translator import translate_status
        result = translate_status("FINISHED")
        assert isinstance(result, str)
        assert len(result) > 0
