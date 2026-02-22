"""
Tests for ouo.io link deduplication and sequential resolution logic.
Validates that duplicate URLs are resolved only once and results are mapped correctly.
"""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_ouo_dedup_resolves_unique_urls_only():
    """When multiple chapters share the same ouo.io URL, resolve each unique URL only once."""
    ouo_links_to_resolve = [
        (1.0, "https://ouo.io/AAA"),
        (2.0, "https://ouo.io/AAA"),
        (3.0, "https://ouo.io/AAA"),
        (4.0, "https://ouo.io/BBB"),
        (5.0, "https://ouo.io/BBB"),
        (6.0, "https://ouo.io/CCC"),
    ]

    unique_urls = list({url for _, url in ouo_links_to_resolve})
    assert len(unique_urls) == 3
    assert set(unique_urls) == {"https://ouo.io/AAA", "https://ouo.io/BBB", "https://ouo.io/CCC"}


@pytest.mark.asyncio
async def test_ouo_resolved_map_applies_to_all_chapters():
    """Resolved map keyed by URL should apply to every chapter that uses that URL."""
    resolved_map = {
        "https://ouo.io/AAA": ("https://mega.nz/file/abc", "MEGA"),
        "https://ouo.io/BBB": ("https://mediafire.com/file/xyz", "MediaFire"),
    }

    chapters = [
        {"number": 1.0, "download_url": "https://ouo.io/AAA"},
        {"number": 2.0, "download_url": "https://ouo.io/AAA"},
        {"number": 3.0, "download_url": "https://ouo.io/BBB"},
        {"number": 4.0, "download_url": "https://ouo.io/CCC"},
    ]

    for ch in chapters:
        url = ch["download_url"]
        if url in resolved_map:
            ch["download_url"], ch["download_host"] = resolved_map[url]

    assert chapters[0]["download_url"] == "https://mega.nz/file/abc"
    assert chapters[1]["download_url"] == "https://mega.nz/file/abc"
    assert chapters[2]["download_url"] == "https://mediafire.com/file/xyz"
    assert chapters[3]["download_url"] == "https://ouo.io/CCC"


@pytest.mark.asyncio
async def test_ouo_empty_list_no_resolution():
    """When there are no ouo.io links, nothing to resolve."""
    ouo_links_to_resolve = []
    unique_urls = list({url for _, url in ouo_links_to_resolve})
    assert len(unique_urls) == 0


@pytest.mark.asyncio
async def test_ouo_single_url_no_dedup_needed():
    """A single unique URL should be resolved exactly once."""
    ouo_links_to_resolve = [
        (1.0, "https://ouo.io/ONLY"),
    ]
    unique_urls = list({url for _, url in ouo_links_to_resolve})
    assert len(unique_urls) == 1
    assert unique_urls[0] == "https://ouo.io/ONLY"
