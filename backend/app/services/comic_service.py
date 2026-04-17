"""
Comic Service - Business logic for comic operations
Extracted from api/v1/comic.py for separation of concerns
"""

import asyncio
import hashlib
import logging
import re
from datetime import datetime
from typing import List, Optional
from urllib.parse import quote

from app.models.comic import Comic, ComicIssue
from app.services.comicvine import get_comicvine_service

logger = logging.getLogger(__name__)


# ============================================================================
# COMICVINE METADATA
# ============================================================================

async def fetch_comic_issues(comic_id: int, comicvine_id: int):
    """
    Fetch issues from ComicVine and add to database
    """
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        comicvine = get_comicvine_service()

        # Get all issues (paginated)
        page = 1
        while True:
            issues = await comicvine.get_volume_issues(comicvine_id, page=page, per_page=100)

            if not issues:
                break

            for issue_data in issues:
                # Check if issue already exists
                existing = db.query(ComicIssue).filter(
                    ComicIssue.comic_id == comic_id,
                    ComicIssue.comicvine_id == issue_data['comicvine_id']
                ).first()

                if not existing:
                    issue = ComicIssue(
                        comic_id=comic_id,
                        issue_number=issue_data.get('issue_number'),
                        title=issue_data.get('title'),
                        comicvine_id=issue_data.get('comicvine_id'),
                        cover_image=issue_data.get('cover_image'),
                        description=issue_data.get('description'),
                        release_date=issue_data.get('release_date'),
                        writers=issue_data.get('writers'),
                        artists=issue_data.get('artists'),
                        colorists=issue_data.get('colorists'),
                        status='pending',
                        created_at=datetime.utcnow()
                    )
                    db.add(issue)

            db.commit()

            if len(issues) < 100:
                break
            page += 1

        logger.info(f"Fetched issues for comic {comic_id}")

    except Exception as e:
        logger.error(f"Error fetching issues for comic {comic_id}: {e}")
    finally:
        db.close()


async def fetch_issues_and_search_sources(comic_id: int, comicvine_id: int):
    """
    Background task: fetch issues from ComicVine, then search scrapers for download links.
    Does NOT auto-queue downloads — user decides when to download.
    """
    from app.database import SessionLocal

    # Step 1: Fetch issues from ComicVine
    await fetch_comic_issues(comic_id, comicvine_id)

    # Step 2: Search scrapers for download links
    db = SessionLocal()
    try:
        comic = db.query(Comic).filter(Comic.id == comic_id).first()
        if not comic:
            return

        await search_scrapers_for_comic(comic_id, comic.title)

        # Mark as searched (DON'T auto-queue downloads — user decides when to download)
        comic.sources_searched = True
        db.commit()

        issues_with_urls = db.query(ComicIssue).filter(
            ComicIssue.comic_id == comic_id,
            ComicIssue.download_url != None
        ).count()
        total_issues = db.query(ComicIssue).filter(ComicIssue.comic_id == comic_id).count()
        logger.info(f"Source search complete for '{comic.title}': {issues_with_urls}/{total_issues} issues have download URLs")

    except Exception as e:
        logger.error(f"Error in fetch_issues_and_search_sources for comic {comic_id}: {e}")
    finally:
        db.close()


async def refresh_comic_metadata(comic_id: int, comicvine_id: int):
    """
    Refresh comic metadata from ComicVine
    """
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        comicvine = get_comicvine_service()
        details = await comicvine.get_volume(comicvine_id)

        if details:
            comic = db.query(Comic).filter(Comic.id == comic_id).first()
            if comic:
                comic.description = details.get('description')
                comic.cover_image = details.get('cover_image')
                comic.count_of_issues = details.get('count_of_issues')
                comic.writers = details.get('writers')
                comic.artists = details.get('artists')
                comic.colorists = details.get('colorists')
                comic.characters = details.get('characters')
                comic.updated_at = datetime.utcnow()
                db.commit()

        # Also fetch new issues
        await fetch_comic_issues(comic_id, comicvine_id)

        logger.info(f"Refreshed metadata for comic {comic_id}")

    except Exception as e:
        logger.error(f"Error refreshing comic {comic_id}: {e}")
    finally:
        db.close()


def save_comic_metadata(comic: Comic, issue: ComicIssue, file_path):
    """
    Guarda metadatos del comic como JSON junto al archivo descargado.
    El KCC Worker usará estos datos para generar ComicInfo.xml.
    """
    import json
    from pathlib import Path

    try:
        if isinstance(file_path, str):
            file_path = Path(file_path)

        metadata_path = file_path.with_suffix('.metadata.json')

        # Construir diccionario de metadatos (formato compatible con KCC Worker)
        metadata = {
            'title': comic.title,
            'title_original': comic.title_original,
            'description': comic.description,
            'authors': comic.writers or [],  # writers = authors for comics
            'artists': comic.artists or [],
            'genres': comic.genres or [],
            'tags': [],  # Comics don't have tags like manga
            'status': None,  # Comics don't have status like manga
            'start_date': str(comic.start_year) if comic.start_year else None,
            'end_date': None,
            'average_score': None,
            'anilist_url': None,
            'anilist_id': None,
            'country': 'US',  # Most comics are American
            'is_adult': False,
            # Comic-specific info
            'publisher': comic.publisher,
            'comicvine_url': comic.comicvine_url,
            'comicvine_id': comic.comicvine_id,
            'characters': comic.characters or [],
            'colorists': comic.colorists or [],
            # Info del issue
            'volume_number': int(issue.issue_number) if issue.issue_number and issue.issue_number.isdigit() else 1,
            'chapter_title': issue.title or f"Issue #{issue.issue_number or '?'}",
            'issue_number': issue.issue_number,
            'release_date': issue.release_date,
        }

        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        logger.info(f"Comic metadata saved: {metadata_path}")

    except Exception as e:
        logger.warning(f"Could not save comic metadata for {file_path}: {e}")


# ============================================================================
# ISSUE RANGE PARSING
# ============================================================================

def _parse_issue_range(issue_range: str) -> List[int]:
    """
    Parse an issue range string into a list of issue numbers.

    Examples:
        "#1 - #2"  -> [1, 2]
        "#3"       -> [3]
        "#1-#5"    -> [1, 2, 3, 4, 5]
        "1 - 2"    -> [1, 2]
        "#10"      -> [10]
    """
    if not issue_range:
        return []

    # Try range pattern: "#1 - #2", "#1-#5", "1-5", "#1 - 5"
    range_match = re.search(r'#?(\d+)\s*[-–]\s*#?(\d+)', issue_range)
    if range_match:
        start = int(range_match.group(1))
        end = int(range_match.group(2))
        if start <= end and (end - start) < 100:
            return list(range(start, end + 1))

    # Try single issue: "#3", "3"
    single_match = re.search(r'#?(\d+)', issue_range)
    if single_match:
        return [int(single_match.group(1))]

    return []


# ============================================================================
# SCRAPER VOLUME FETCHING
# ============================================================================

async def fetch_volume_from_scraper(comic_id: int, volume_url: str, source: str, issue_count: int):
    """
    Fetch a specific volume directly from a scraper and create issues

    Args:
        comic_id: ID of the comic in database
        volume_url: Direct URL to the volume page
        source: Scraper name (e.g., "cbrcomics")
        issue_count: Number of issues in this volume
    """
    from app.database import SessionLocal
    from app.services.comic_scrapers import CBRComicsScraper, ZonaComicsScraper, MegaComicsScraper

    db = SessionLocal()
    try:
        # Get scraper instance
        scraper_map = {
            "cbrcomics": CBRComicsScraper(),
            "zonacomics": ZonaComicsScraper(),
            "megacomics": MegaComicsScraper(),
        }

        scraper = scraper_map.get(source)
        if not scraper:
            logger.error(f"Unknown scraper: {source}")
            return

        # Create issues for this volume
        for i in range(1, issue_count + 1):
            existing = db.query(ComicIssue).filter(
                ComicIssue.comic_id == comic_id,
                ComicIssue.issue_number == str(i)
            ).first()

            if not existing:
                issue = ComicIssue(
                    comic_id=comic_id,
                    issue_number=str(i),
                    status='pending',
                    created_at=datetime.utcnow()
                )
                db.add(issue)

        db.commit()

        # Get download links from scraper — skip ouo resolution so direct links appear immediately
        logger.info(f"Fetching download links for volume from {source}: {volume_url}")
        use_progressive = source in ('zonacomics', 'megacomics')
        scrape_result = await scraper.get_download_links(volume_url, resolve_ouo=not use_progressive) \
            if use_progressive else await scraper.get_download_links(volume_url)

        if scrape_result.success and scrape_result.download_links:
            issues = db.query(ComicIssue).filter(
                ComicIssue.comic_id == comic_id
            ).order_by(ComicIssue.issue_number).all()

            # Build issue_number -> issue mapping
            issue_map = {}
            for issue in issues:
                try:
                    num = int(issue.issue_number) if issue.issue_number and issue.issue_number.isdigit() else 0
                except (ValueError, TypeError):
                    num = 0
                if num > 0:
                    issue_map[num] = issue

            # Include shorteners in assignment strategy (Phase 1 — show immediately)
            # Prefer resolved links; fall back to shorteners so something appears right away
            resolved_links = [
                dl for dl in scrape_result.download_links
                if dl.link_status == 'resolved'
            ]
            assignable_links = resolved_links or [
                dl for dl in scrape_result.download_links
                if dl.link_status == 'shortener'
            ]
            assignable_links.sort(key=lambda x: x.quality_score, reverse=True)

            # Check if links have issue_range metadata (from table parsing — MegaComics)
            has_issue_mapping = any(dl.issue_range for dl in assignable_links)

            if has_issue_mapping:
                # SMART ASSIGNMENT: Use issue_range from scraper to map links to issues
                logger.info(f"Using issue_range metadata to assign {len(assignable_links)} links")
                assigned = 0
                for dl in assignable_links:
                    if not dl.issue_range:
                        continue
                    # Parse issue_range: "#1 - #2", "#3", "#1-#5", etc.
                    issue_nums = _parse_issue_range(dl.issue_range)
                    if not issue_nums:
                        continue

                    # If range covers multiple issues, create a bundle
                    if len(issue_nums) > 1:
                        bundle_id = hashlib.md5(dl.url.encode()).hexdigest()[:16]
                        first = True
                        for num in issue_nums:
                            issue = issue_map.get(num)
                            if issue and not issue.download_url:
                                issue.download_url = dl.url
                                issue.source = source
                                issue.link_status = dl.link_status
                                issue.bundle_id = bundle_id
                                issue.bundle_range = dl.issue_range
                                issue.bundle_title = f"{scrape_result.title} ({dl.issue_range})"
                                issue.is_bundle_master = first
                                first = False
                                assigned += 1
                    else:
                        # Single issue
                        issue = issue_map.get(issue_nums[0])
                        if issue and not issue.download_url:
                            issue.download_url = dl.url
                            issue.source = source
                            issue.link_status = dl.link_status
                            assigned += 1

                db.commit()
                logger.info(f"Smart assignment (Phase 1): {assigned}/{len(issues)} issues got links from {source}")

            elif len(assignable_links) >= max(2, len(issues) * 0.5):
                # Multiple links, no issue_range: assign sequentially per issue
                logger.info(f"Assigning {len(assignable_links)} links sequentially to {len(issues)} issues")
                link_idx = 0
                for issue in issues:
                    if issue.downloaded_at:
                        continue
                    if link_idx < len(assignable_links):
                        issue.download_url = assignable_links[link_idx].url
                        issue.source = source
                        issue.link_status = assignable_links[link_idx].link_status
                        logger.info(f"  Issue #{issue.issue_number}: {assignable_links[link_idx].host.value} link assigned")
                        link_idx += 1

                db.commit()
                logger.info(f"Sequential assignment (Phase 1): {min(len(assignable_links), len(issues))} issues from {source}")

            elif len(assignable_links) >= 1:
                # Few links: bundle all issues with best link
                bundle_id = hashlib.md5(volume_url.encode()).hexdigest()[:16]
                bundle_title = scrape_result.title
                bundle_range = f"#1-{issue_count}"

                undownloaded = [iss for iss in issues if not iss.downloaded_at]
                for idx, issue in enumerate(undownloaded):
                    issue.bundle_id = bundle_id
                    issue.bundle_title = bundle_title
                    issue.bundle_range = bundle_range
                    issue.is_bundle_master = (idx == 0)
                    issue.download_url = assignable_links[0].url
                    issue.source = f"{source} (bundle)"
                    issue.link_status = assignable_links[0].link_status

                    if issue.is_bundle_master and len(assignable_links) > 1:
                        issue.backup_url = assignable_links[1].url

                skipped = len(issues) - len(undownloaded)
                db.commit()
                logger.info(f"Bundle assignment (Phase 1): {bundle_title} with {len(undownloaded)} issues ({skipped} already downloaded)")

            else:
                logger.warning(f"No assignable links found for volume: {volume_url}")

            # ── Phase 2: Resolve ouo shorteners progressively, commit after each ──
            if use_progressive:
                from app.services.ouo_resolver import resolve_ouo_link
                from app.services.comic_scrapers.base import HostType as HT

                # Group issues by their ouo shortener URL (dedup for bundle cases)
                ouo_groups: dict = {}
                for issue in db.query(ComicIssue).filter(
                    ComicIssue.comic_id == comic_id,
                    ComicIssue.link_status == 'shortener',
                ).all():
                    if issue.download_url and ('ouo.io' in issue.download_url or 'ouo.press' in issue.download_url):
                        ouo_groups.setdefault(issue.download_url, []).append(issue)

                if ouo_groups:
                    logger.info(f"Phase 2: resolving {len(ouo_groups)} unique ouo links for {comic_id}")
                    for ouo_url, bundle_issues in ouo_groups.items():
                        try:
                            resolved_url = await resolve_ouo_link(ouo_url)
                            if resolved_url:
                                for bi in bundle_issues:
                                    bi.download_url = resolved_url
                                    bi.link_status = 'resolved'
                                db.commit()  # ← frontend sees this via polling
                                logger.info(f"Resolved ouo → {resolved_url[:60]} ({len(bundle_issues)} issues)")
                            else:
                                logger.warning(f"Could not resolve ouo: {ouo_url[:60]}")
                        except Exception as e:
                            logger.error(f"Phase 2 ouo resolution failed for {ouo_url[:60]}: {e}")
        else:
            logger.warning(f"No download links found for volume: {volume_url}")

        # Mark as searched (but DON'T auto-queue downloads — user decides when to download)
        comic = db.query(Comic).filter(Comic.id == comic_id).first()
        if comic:
            comic.sources_searched = True
            db.commit()

    except Exception as e:
        logger.error(f"Error fetching volume from scraper: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


# ============================================================================
# DOWNLOAD FUNCTIONS
# ============================================================================

async def download_comic_issue(issue_id: int):
    """Background task to download a comic issue"""
    from app.database import SessionLocal
    from app.services.comic_downloader import ComicDownloader
    from pathlib import Path
    import os

    db = SessionLocal()
    try:
        issue = db.query(ComicIssue).filter(ComicIssue.id == issue_id).first()
        if not issue:
            logger.error(f"Issue {issue_id} not found")
            return

        comic = db.query(Comic).filter(Comic.id == issue.comic_id).first()
        if not comic:
            logger.error(f"Comic for issue {issue_id} not found")
            return

        # BUNDLE LOGIC: Skip if part of bundle but NOT the master
        if issue.bundle_id and not issue.is_bundle_master:
            logger.info(f"Issue #{issue.issue_number} is part of bundle '{issue.bundle_title}' - skipping (master will download)")
            issue.status = "pending"  # Keep as pending, master will update it
            db.commit()
            return

        if not issue.download_url:
            issue.status = "error"
            issue.error_message = "No download URL"
            db.commit()
            return

        # Log if this is a bundle master
        if issue.is_bundle_master:
            logger.info(f"Downloading BUNDLE MASTER: {issue.bundle_title} ({issue.bundle_range})")

        # Create downloader
        download_dir = os.getenv("DOWNLOAD_DIR", "/downloads")
        downloader = ComicDownloader(download_dir=download_dir)

        # Step 1: Resolve URL shorteners before downloading
        download_url = issue.download_url
        resolved_url = await downloader.resolve_url(download_url)
        if resolved_url:
            download_url = resolved_url
            logger.info(f"Resolved URL: {download_url[:80]}")
            # Persist resolved URL to DB so users see the real URL, not the shortener
            if download_url != issue.download_url:
                issue.download_url = download_url
                issue.link_status = 'resolved'
                db.commit()
        else:
            issue.status = "error"
            issue.error_message = f"Could not resolve URL shortener: {issue.download_url[:50]}"
            db.commit()
            return

        # Step 2: Check if resolved URL is a MediaFire folder (bundle with individual files)
        if 'mediafire.com/folder/' in download_url.lower() and issue.is_bundle_master and issue.bundle_id:
            await _download_mediafire_folder_bundle(
                issue, comic, download_url, downloader, download_dir, db
            )
            return

        # Step 2b: Check if URL is a CBRComics page (contains MEGA folder links)
        if 'cbrcomicsweb.space' in download_url.lower() and issue.is_bundle_master and issue.bundle_id:
            mega_folder_url = await _extract_mega_folder_from_page(download_url)
            if mega_folder_url:
                logger.info(f"CBRComics: Extracted MEGA folder URL: {mega_folder_url}")
                await _download_mega_folder_bundle(
                    issue, comic, mega_folder_url, downloader, download_dir, db
                )
                return
            else:
                issue.status = "error"
                issue.error_message = "Could not extract MEGA folder URL from CBRComics page"
                db.commit()
                return

        # Step 2c: Check if resolved URL is a MEGA folder (bundle with individual files)
        if 'mega.nz/folder/' in download_url.lower() and issue.is_bundle_master and issue.bundle_id:
            await _download_mega_folder_bundle(
                issue, comic, download_url, downloader, download_dir, db
            )
            return

        # Step 3: Regular single-file download
        issue_num = issue.issue_number or "000"
        safe_title = "".join(c for c in comic.title if c.isalnum() or c in " -_")[:50]
        filename = f"{safe_title} - Issue {issue_num}.cbz"

        # Download using resolved URL directly (skip re-resolving shorteners)
        backup_urls = [issue.backup_url] if issue.backup_url else None
        result = await downloader.download_comic(
            url=download_url,
            filename=filename,
            backup_urls=backup_urls
        )

        if result and result.exists():
            issue.status = "downloaded"
            issue.file_path = str(result)
            issue.file_size = result.stat().st_size
            issue.downloaded_at = datetime.utcnow()
            issue.error_message = None

            # Save metadata for KCC Worker to generate ComicInfo.xml
            save_comic_metadata(comic, issue, result)

            logger.info(f"Downloaded comic issue: {filename}")

            # BUNDLE LOGIC: If this is a bundle master, mark ALL bundle issues as downloaded
            if issue.is_bundle_master and issue.bundle_id:
                bundle_issues = db.query(ComicIssue).filter(
                    ComicIssue.bundle_id == issue.bundle_id,
                    ComicIssue.id != issue.id
                ).all()

                for bi in bundle_issues:
                    bi.status = "downloaded"
                    bi.file_path = str(result)
                    bi.file_size = result.stat().st_size
                    bi.downloaded_at = datetime.utcnow()
                    bi.error_message = None

                db.commit()
                logger.info(f"BUNDLE: Marked {len(bundle_issues) + 1} issues from '{issue.bundle_title}' as downloaded")
        else:
            issue.status = "error"
            issue.error_message = "Download failed"
            issue.download_attempts = (issue.download_attempts or 0) + 1
            logger.error(f"Failed to download issue {issue_id}")

        db.commit()

    except Exception as e:
        logger.error(f"Error downloading issue {issue_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        try:
            issue = db.query(ComicIssue).filter(ComicIssue.id == issue_id).first()
            if issue:
                issue.status = "error"
                issue.error_message = str(e)[:500]
                db.commit()
        except:
            pass
    finally:
        db.close()


async def _download_mediafire_folder_bundle(
    master_issue: "ComicIssue",
    comic: "Comic",
    folder_url: str,
    downloader,
    download_dir: str,
    db
):
    """
    Download a MediaFire folder bundle: list files, match to issues, download each.
    Uses lock files (.downloading) like manga to prevent KCC from processing prematurely.
    """
    from pathlib import Path
    from app.services.generic_downloader import list_mediafire_folder

    logger.info(f"MediaFire folder bundle: {folder_url}")

    # Get all bundle issues
    bundle_issues = db.query(ComicIssue).filter(
        ComicIssue.bundle_id == master_issue.bundle_id
    ).order_by(ComicIssue.issue_number).all()

    logger.info(f"Bundle has {len(bundle_issues)} issues")

    # Step 1: List files in the MediaFire folder (without downloading)
    folder_result = await list_mediafire_folder(folder_url)
    if not folder_result.get("ok") or not folder_result.get("files"):
        master_issue.status = "error"
        master_issue.error_message = f"Could not list MediaFire folder: {folder_result.get('error', 'unknown')}"
        master_issue.download_attempts = (master_issue.download_attempts or 0) + 1
        db.commit()
        return

    folder_files = folder_result["files"]
    logger.info(f"MediaFire folder has {len(folder_files)} files")

    # Step 2: Match folder files to issues by tomo/issue number
    def extract_number(filename: str) -> int:
        from app.services.comic_scrapers.title_parser import extract_issue_from_filename
        result = extract_issue_from_filename(filename)
        return result if result else 0

    # Build issue_number -> issue mapping
    issue_map = {}
    for bi in bundle_issues:
        try:
            num = int(bi.issue_number) if bi.issue_number and bi.issue_number.isdigit() else 0
        except (ValueError, TypeError):
            num = 0
        if num > 0:
            issue_map[num] = bi

    # Build file_number -> folder file mapping
    file_map = {}
    for ff in folder_files:
        num = extract_number(ff["name"])
        if num > 0:
            file_map[num] = ff

    logger.info(f"Issue numbers: {sorted(issue_map.keys())}")
    logger.info(f"File numbers: {sorted(file_map.keys())}")

    # If number matching fails, try sequential
    use_sequential = False
    if not file_map or len(set(issue_map.keys()) & set(file_map.keys())) == 0:
        if len(folder_files) == len(bundle_issues):
            logger.info("Number matching failed, will use sequential assignment")
            use_sequential = True
        else:
            master_issue.status = "error"
            master_issue.error_message = f"Could not match {len(folder_files)} files to {len(bundle_issues)} issues"
            db.commit()
            return

    # Step 3: Download each file with its FINAL name (lock files protect from KCC)
    safe_title = "".join(c for c in comic.title if c.isalnum() or c in " -_")[:50]
    matched = 0

    if use_sequential:
        pairs = list(zip(
            sorted(bundle_issues, key=lambda x: int(x.issue_number) if x.issue_number and x.issue_number.isdigit() else 0),
            sorted(folder_files, key=lambda x: x["name"])
        ))
        download_plan = [(bi, ff) for bi, ff in pairs]
    else:
        download_plan = []
        for issue_num, bi in issue_map.items():
            if issue_num in file_map:
                download_plan.append((bi, file_map[issue_num]))
            else:
                logger.warning(f"No file found for issue #{issue_num}")
                bi.status = "error"
                bi.error_message = f"No matching file in folder for issue #{issue_num}"

    for bi, ff in download_plan:
        issue_num = bi.issue_number or "000"

        # Skip already-downloaded issues (differential download)
        if bi.downloaded_at:
            logger.info(f"Issue #{issue_num}: already downloaded, skipping")
            matched += 1
            continue

        # Detect extension from original filename
        orig_ext = Path(ff["name"]).suffix.lower() or ".cbr"
        final_filename = f"{safe_title} - Issue {issue_num}{orig_ext}"

        logger.info(f"Downloading issue #{issue_num}: {ff['name'][:60]} -> {final_filename}")

        try:
            # download_file_with_name: gets direct link + downloads with lock file
            result_path = await downloader.download_file_with_name(
                page_url=ff["url"],
                final_filename=final_filename
            )

            if result_path and result_path.exists():
                bi.status = "downloaded"
                bi.file_path = str(result_path)
                bi.file_size = result_path.stat().st_size
                bi.downloaded_at = datetime.utcnow()
                bi.error_message = None

                # Save metadata for KCC Worker (generates ComicInfo.xml)
                save_comic_metadata(comic, bi, result_path)

                matched += 1
                logger.info(f"Downloaded issue #{issue_num}: {result_path.stat().st_size / 1024 / 1024:.1f} MB")
            else:
                bi.status = "error"
                bi.error_message = f"Download failed for {ff['name'][:60]}"
                logger.error(f"Failed to download issue #{issue_num}")
        except Exception as e:
            bi.status = "error"
            bi.error_message = str(e)[:500]
            logger.error(f"Error downloading issue #{issue_num}: {e}")

    db.commit()
    logger.info(f"MediaFire folder bundle: {matched}/{len(bundle_issues)} issues downloaded")


async def _extract_mega_folder_from_page(page_url: str) -> Optional[str]:
    """
    Extract MEGA folder URL from a CBRComics (or similar WordPress) page.
    CBRComics uses "LinkContainer" WordPress plugin that stores links as
    base64(urlencode(url)) in data-link attributes on anchor tags.
    """
    import base64
    from urllib.parse import unquote

    try:
        from app.services.book_scrapers.playwright_scraper import get_playwright_scraper

        playwright_scraper = await get_playwright_scraper()
        page = await playwright_scraper._create_page()

        try:
            logger.info(f"CBRComics: Scraping page for MEGA folder: {page_url}")
            await page.goto(page_url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(2)

            # Method 1: Decode data-link attributes (LinkContainer plugin)
            data_links = await page.query_selector_all('[data-link]')
            for el in data_links:
                encoded = await el.get_attribute('data-link')
                if encoded:
                    try:
                        decoded = unquote(base64.b64decode(encoded).decode())
                        if 'mega.nz/folder/' in decoded:
                            logger.info(f"CBRComics: Decoded MEGA folder from data-link: {decoded}")
                            return decoded
                    except Exception:
                        pass

            # Method 2: Find MEGA folder links in href attributes
            links = await page.query_selector_all('a[href*="mega.nz/folder/"]')
            for link in links:
                href = await link.get_attribute('href')
                if href and 'mega.nz/folder/' in href:
                    logger.info(f"CBRComics: Found MEGA folder link in href: {href}")
                    return href

            # Method 3: Search page content with regex
            html_content = await page.content()
            mega_pattern = r'https?://mega\.nz/folder/[A-Za-z0-9_-]+#[A-Za-z0-9_-]+'
            matches = re.findall(mega_pattern, html_content)
            if matches:
                logger.info(f"CBRComics: Found MEGA folder link in HTML: {matches[0]}")
                return matches[0]

            logger.warning(f"CBRComics: No MEGA folder URL found in page")
            return None

        finally:
            await page.close()

    except Exception as e:
        logger.error(f"CBRComics page scraping error: {e}")
        return None


async def _download_mega_folder_bundle(
    master_issue: "ComicIssue",
    comic: "Comic",
    folder_url: str,
    downloader,
    download_dir: str,
    db
):
    """
    Download a MEGA shared folder bundle: list files via Playwright, match to issues,
    download each with megatools CLI + lock files.
    """
    from pathlib import Path
    from app.services.generic_downloader import list_mega_folder

    logger.info(f"MEGA folder bundle: {folder_url}")

    # Get all bundle issues
    bundle_issues = db.query(ComicIssue).filter(
        ComicIssue.bundle_id == master_issue.bundle_id
    ).order_by(ComicIssue.issue_number).all()

    logger.info(f"Bundle has {len(bundle_issues)} issues")

    # Step 1: List files in the MEGA folder (Playwright + M.d JS object)
    folder_result = await list_mega_folder(folder_url)
    if not folder_result.get("ok") or not folder_result.get("files"):
        master_issue.status = "error"
        master_issue.error_message = f"Could not list MEGA folder: {folder_result.get('error', 'unknown')}"
        master_issue.download_attempts = (master_issue.download_attempts or 0) + 1
        db.commit()
        return

    folder_files = folder_result["files"]
    logger.info(f"MEGA folder has {len(folder_files)} files")

    # Step 2: Match folder files to issues by number
    def extract_number(filename: str) -> int:
        """Extract issue number from filename. Prioritize #XX over VolX."""
        from app.services.comic_scrapers.title_parser import extract_issue_from_filename
        result = extract_issue_from_filename(filename)
        return result if result else 0

    # Build issue_number -> issue mapping
    issue_map = {}
    for bi in bundle_issues:
        try:
            num = int(bi.issue_number) if bi.issue_number and bi.issue_number.isdigit() else 0
        except (ValueError, TypeError):
            num = 0
        if num > 0:
            issue_map[num] = bi

    # Build file_number -> folder file mapping
    file_map = {}
    for ff in folder_files:
        num = extract_number(ff["name"])
        if num > 0:
            file_map[num] = ff

    logger.info(f"Issue numbers: {sorted(issue_map.keys())}")
    logger.info(f"File numbers: {sorted(file_map.keys())}")

    # If number matching fails, try sequential
    use_sequential = False
    if not file_map or len(set(issue_map.keys()) & set(file_map.keys())) == 0:
        if len(folder_files) == len(bundle_issues):
            logger.info("Number matching failed, will use sequential assignment")
            use_sequential = True
        else:
            master_issue.status = "error"
            master_issue.error_message = f"Could not match {len(folder_files)} files to {len(bundle_issues)} issues"
            db.commit()
            return

    # Step 3: Download each file with megatools + lock files
    safe_title = "".join(c for c in comic.title if c.isalnum() or c in " -_")[:50]
    matched = 0

    if use_sequential:
        pairs = list(zip(
            sorted(bundle_issues, key=lambda x: int(x.issue_number) if x.issue_number and x.issue_number.isdigit() else 0),
            sorted(folder_files, key=lambda x: x["name"])
        ))
        download_plan = [(bi, ff) for bi, ff in pairs]
    else:
        download_plan = []
        for issue_num, bi in issue_map.items():
            if issue_num in file_map:
                download_plan.append((bi, file_map[issue_num]))
            else:
                logger.warning(f"No file found for issue #{issue_num}")
                bi.status = "error"
                bi.error_message = f"No matching file in MEGA folder for issue #{issue_num}"

    for bi, ff in download_plan:
        issue_num = bi.issue_number or "000"

        # Skip already-downloaded issues (differential download)
        if bi.downloaded_at:
            logger.info(f"Issue #{issue_num}: already downloaded, skipping")
            matched += 1
            continue

        # Detect extension from original MEGA filename
        orig_ext = Path(ff["name"]).suffix.lower() or ".cbr"
        final_filename = f"{safe_title} - Issue {issue_num}{orig_ext}"

        logger.info(f"Downloading issue #{issue_num}: {ff['name'][:60]} -> {final_filename}")

        try:
            # Use megatools to download from shared folder
            result_path = await downloader._download_megatools(
                url=ff["url"],
                filename=final_filename
            )

            if result_path and result_path.exists():
                bi.status = "downloaded"
                bi.file_path = str(result_path)
                bi.file_size = result_path.stat().st_size
                bi.downloaded_at = datetime.utcnow()
                bi.error_message = None

                # Save metadata for KCC Worker
                save_comic_metadata(comic, bi, result_path)

                matched += 1
                logger.info(f"Downloaded issue #{issue_num}: {result_path.stat().st_size / 1024 / 1024:.1f} MB")
            else:
                bi.status = "error"
                bi.error_message = f"megatools download failed for {ff['name'][:60]}"
                logger.error(f"Failed to download issue #{issue_num}")
        except Exception as e:
            bi.status = "error"
            bi.error_message = str(e)[:500]
            logger.error(f"Error downloading issue #{issue_num}: {e}")

    db.commit()
    logger.info(f"MEGA folder bundle: {matched}/{len(bundle_issues)} issues downloaded")


# ============================================================================
# TITLE PARSING & MATCHING HELPERS
# ============================================================================

def translate_comic_title(spanish_title: str) -> str:
    """
    Translate common Spanish comic terms to English for ComicVine search.
    Includes Marvel/DC superheroes, Star Wars, Indies, and common Spanish terms.
    """
    # Phrase translations (longer matches first to avoid partial replacement)
    phrase_translations = {
        # Star Wars
        'caballeros de la antigua república': 'knights of the old republic',
        'la antigua república': 'the old republic',
        'guerras clon': 'clone wars',
        'el despertar de la fuerza': 'the force awakens',
        'el retorno del jedi': 'return of the jedi',
        'el imperio contraataca': 'the empire strikes back',
        'una nueva esperanza': 'a new hope',
        'la amenaza fantasma': 'the phantom menace',
        'el ataque de los clones': 'attack of the clones',
        'la venganza de los sith': 'revenge of the sith',
        'rogue one': 'rogue one',

        # DC heroes/titles
        'el caballero oscuro': 'the dark knight',
        'el regreso del caballero oscuro': 'the dark knight returns',
        'la broma asesina': 'the killing joke',
        'tierra de nadie': 'no mans land',
        'crisis en tierras infinitas': 'crisis on infinite earths',
        'crisis infinita': 'infinite crisis',
        'crisis final': 'final crisis',
        'la muerte de superman': 'the death of superman',
        'liga de la justicia': 'justice league',
        'mujer maravilla': 'wonder woman',
        'linterna verde': 'green lantern',
        'flecha verde': 'green arrow',
        'hombre halcón': 'hawkman',
        'hombre de acero': 'man of steel',
        'escuadrón suicida': 'suicide squad',
        'aves de presa': 'birds of prey',
        'titanes': 'titans',
        'nuevos titanes': 'new teen titans',
        'jóvenes titanes': 'teen titans',

        # Marvel heroes/titles
        'hombre araña': 'spider-man',
        'el asombroso hombre araña': 'the amazing spider-man',
        'el increíble hulk': 'the incredible hulk',
        'los cuatro fantásticos': 'fantastic four',
        'los vengadores': 'the avengers',
        'capitán américa': 'captain america',
        'hombre de hierro': 'iron man',
        'patrulla x': 'x-men',
        'la patrulla x': 'x-men',
        'guerras secretas': 'secret wars',
        'invasión secreta': 'secret invasion',
        'guerra civil': 'civil war',
        'edad de ultron': 'age of ultron',
        'infinity war': 'infinity war',
        'pantera negra': 'black panther',
        'viuda negra': 'black widow',
        'ojo de halcón': 'hawkeye',
        'puño de hierro': 'iron fist',
        'los eternos': 'eternals',
        'los inhumanos': 'inhumans',
        'caballero luna': 'moon knight',

        # Indie/other
        'los muertos vivientes': 'the walking dead',
        'las tortugas ninja': 'teenage mutant ninja turtles',
        'saga de la ciénaga': 'swamp thing',
        'el hombre cosa': 'man-thing',
    }

    # Word-level translations
    word_translations = {
        # Star Wars
        'caballeros': 'knights',
        'imperio': 'empire',
        'república': 'republic',
        'antigua': 'old',
        'amanecer': 'dawn',
        'ascenso': 'rise',

        # DC
        'batman': 'batman',
        'superman': 'superman',
        'aquaman': 'aquaman',
        'supergirl': 'supergirl',
        'batgirl': 'batgirl',
        'nightwing': 'nightwing',
        'deathstroke': 'deathstroke',

        # Marvel
        'deadpool': 'deadpool',
        'wolverine': 'wolverine',
        'daredevil': 'daredevil',
        'thor': 'thor',
        'loki': 'loki',
        'venom': 'venom',
        'carnage': 'carnage',
        'thanos': 'thanos',

        # Common comic terms
        'volumen': 'volume',
        'tomo': 'volume',
        'tomos': 'volumes',
        'completo': 'complete',
        'completa': 'complete',
        'colección': 'collection',
        'saga': 'saga',
        'serie': 'series',

        # Words to remove
        'español': '',
        'castellano': '',
        'descargar': '',
    }

    title_lower = spanish_title.lower()

    # Remove bracketed info like [9 Tomos]
    title_lower = re.sub(r'\[.*?\]', '', title_lower)

    # Apply phrase translations first (longer matches)
    for spanish, english in phrase_translations.items():
        if spanish in title_lower:
            title_lower = title_lower.replace(spanish, english)

    # Apply word translations
    for spanish, english in word_translations.items():
        if spanish in title_lower:
            title_lower = title_lower.replace(spanish, english)

    # Clean up extra spaces
    title_lower = ' '.join(title_lower.split())

    logger.debug(f"Translation: '{spanish_title}' → '{title_lower}'")
    return title_lower.title()  # Capitalize first letter of each word


async def verify_link_active(url: str) -> bool:
    """Check if a download link is still active (not 404)"""
    import aiohttp

    logger.debug(f"_verify_link_active() called for: {url[:60]}...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, timeout=aiohttp.ClientTimeout(total=10), allow_redirects=True) as response:
                logger.debug(f"HEAD {url[:60]} → {response.status}")
                if response.status < 400:
                    return True
                # Some hosts return 403 but file is still downloadable
                if response.status == 403:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10), allow_redirects=True) as get_resp:
                        logger.debug(f"GET fallback {url[:60]} → {get_resp.status}")
                        return get_resp.status < 400
                logger.warning(f"Link check failed {response.status}: {url[:60]}")
                return False
    except Exception as e:
        logger.debug(f"Link verification error (assuming OK): {e}")
        return True


def normalize_title(title: str) -> str:
    """Normalize title for comparison"""
    from app.services.comic_scrapers.title_parser import normalize_title as _normalize
    return _normalize(title)


def title_matches(search_title: str, result_title: str) -> bool:
    """Check if result title is a good match for search title"""
    search_norm = normalize_title(search_title)
    result_norm = normalize_title(result_title)

    # Exact match
    if search_norm == result_norm:
        return True

    # Result starts with search title (most reliable)
    if result_norm.startswith(search_norm + " ") or result_norm.startswith(search_norm + "-"):
        return True

    # For short titles (like "300"), be more strict
    if len(search_norm) <= 5:
        if result_norm.startswith(search_norm + " "):
            return True

        # Check for issue ranges like "#1-300" - should NOT match "300"
        issue_range_pattern = r'#\s*\d+\s*[-–]\s*' + re.escape(search_norm)
        if re.search(issue_range_pattern, result_norm):
            logger.debug(f"Skipping issue range match: {result_norm}")
            return False

        # Check if it's just an issue number
        issue_number_pattern = r'\w+\s+#?\s*' + re.escape(search_norm) + r'\s*(\(|$|\s)'
        if re.search(issue_number_pattern, result_norm):
            logger.debug(f"Skipping issue number match: {result_norm}")
            return False

        # Use word boundary matching
        pattern = r'(^|\s)' + re.escape(search_norm) + r'(\s|$|[:\-])'
        if re.search(pattern, result_norm):
            return True

        return False

    # Search title is contained in result (for longer titles)
    if search_norm in result_norm:
        return True

    # Check word overlap
    search_words = set(search_norm.split())
    result_words = set(result_norm.split())
    if search_words and len(search_words) >= 2 and search_words.issubset(result_words):
        return True

    return False


def extract_volume_info(title: str) -> Optional[dict]:
    """
    Extract volume information from a comic title

    Returns:
        {"volume_number": 3, "base_title": "The Invaders", "has_volume": True} or None
    """
    from app.services.comic_scrapers.title_parser import extract_volume_number, VOLUME_PATTERNS

    vol_num = extract_volume_number(title)
    if vol_num is not None:
        # Extract base title (remove volume part and extra info)
        base_title = title
        for pattern in VOLUME_PATTERNS:
            base_title = re.sub(pattern, '', base_title, flags=re.IGNORECASE)
        base_title = re.sub(r'\[.*?\]', '', base_title)
        base_title = re.sub(r'español', '', base_title, flags=re.IGNORECASE)
        base_title = base_title.strip()

        return {
            "volume_number": vol_num,
            "base_title": base_title,
            "has_volume": True
        }

    return None


def detect_bundle(title: str, description: str = "", count_of_issues: int = 0) -> Optional[dict]:
    """
    Detect if a comic result is a bundle/collection that covers multiple issues

    Returns:
        {"type": "complete|tpb|hc|range", "range": "#1-30", "issues": [1, 2, ...]} or None
    """
    title_lower = title.lower()
    desc_lower = description.lower() if description else ""
    combined = f"{title_lower} {desc_lower}"

    # Pattern 1: Explicit issue range
    range_patterns = [
        r'#(\d+)-#?(\d+)',  # #1-30 or #1-#30
        r'issues?\s*#?(\d+)\s*-\s*#?(\d+)',  # "issues 1-30"
        r'#(\d+)\s*–\s*#?(\d+)',  # Using en-dash
        r'\[(\d+)/(\d+)\?*\]',  # [12/12], [8/8?], [8/8??]
        r'\[(\d+)\s+de\s+(\d+)\]',  # [5 de 5]
        r'\[(\d+)\s+tomos?\]',  # [9 Tomos]
        r'\[(\d+)\s+n[uú]meros?\]',  # [80 números]
        r'\[(\d+)\s+vol[uú]menes?\]',  # [15 volúmenes]
    ]

    for pattern in range_patterns:
        match = re.search(pattern, combined)
        if match:
            # Special case for single-count patterns
            if 'tomos' in pattern or 'meros' in pattern or 'menes' in pattern:
                total = int(match.group(1))
                logger.info(f"Bundle detected via pattern '{pattern}': #1-{total}")
                return {
                    "type": "complete",
                    "range": f"#1-{total}",
                    "issues": list(range(1, total + 1))
                }

            start = int(match.group(1))
            end = int(match.group(2))

            # Special case for [X de X] and [X/X] formats
            if ('de' in pattern or '/' in pattern) and start == end:
                logger.info(f"Bundle detected via [X de X] or [X/X] pattern: #1-{end}")
                return {
                    "type": "range",
                    "range": f"#1-{end}",
                    "issues": list(range(1, end + 1))
                }

            if start < end and (end - start) <= 1000:
                logger.info(f"Bundle detected via range pattern: #{start}-{end}")
                return {
                    "type": "range",
                    "range": f"#{start}-{end}",
                    "issues": list(range(start, end + 1))
                }

    # Pattern 2: "Complete" collections (Spanish + English)
    from app.services.comic_scrapers.title_parser import is_complete as _is_complete, extract_total_issues
    if _is_complete(combined) or any(word in combined for word in ["complete collection", "full series", "complete story"]):
        total = extract_total_issues(combined)
        if total:
            logger.info(f"Bundle detected via 'complete' + {total} issues")
            return {
                "type": "complete",
                "range": f"#1-{total}",
                "issues": list(range(1, total + 1))
            }
        elif count_of_issues > 0:
            logger.info(f"Bundle detected via 'complete' + ComicVine count ({count_of_issues})")
            return {
                "type": "complete",
                "range": f"#1-{count_of_issues}",
                "issues": list(range(1, count_of_issues + 1))
            }

    # Pattern 3: "Collects" statement
    collects_match = re.search(r'collects?\s*(?:issues?\s*)?#?(\d+)\s*-\s*#?(\d+)', combined)
    if collects_match:
        start = int(collects_match.group(1))
        end = int(collects_match.group(2))
        if start < end:
            logger.info(f"Bundle detected via 'collects' statement: #{start}-{end}")
            return {
                "type": "collects",
                "range": f"#{start}-{end}",
                "issues": list(range(start, end + 1))
            }

    # Pattern 4: Volume/Book numbers (TPB/HC)
    vol_match = re.search(r'vol(?:ume)?\.?\s*(\d+)', title_lower)
    book_match = re.search(r'book\s+(\w+)', title_lower)

    if (vol_match or book_match) and any(word in combined for word in ["tpb", "tp", "trade paperback", "hardcover", "hc"]):
        desc_range_match = re.search(r'#?(\d+)\s*-\s*#?(\d+)', desc_lower)
        if desc_range_match:
            start = int(desc_range_match.group(1))
            end = int(desc_range_match.group(2))
            logger.info(f"Bundle detected via TPB/HC with range in description: #{start}-{end}")
            return {
                "type": "tpb" if "tpb" in combined or "trade" in combined else "hc",
                "range": f"#{start}-{end}",
                "issues": list(range(start, end + 1))
            }

        logger.debug(f"TPB/HC detected but no explicit range found: {title}")

    return None


# ============================================================================
# SCRAPER SEARCH FUNCTIONS
# ============================================================================

async def search_scrapers_directly(query: str) -> List[dict]:
    """
    Search scrapers directly with user's query (for Spanish searches)
    Returns list of volumes found: [{"number": 0, "title": "...", "source": "...", ...}]
    """
    from app.services.comic_scrapers import ZonaComicsScraper, MegaComicsScraper, CBRComicsScraper

    scrapers = [
        CBRComicsScraper(),
        ZonaComicsScraper(),
        MegaComicsScraper(),
    ]

    found_volumes = []
    seen_urls = set()

    # Extract query keywords for relevance filtering
    query_lower = query.lower()
    query_keywords = set()
    for word in query_lower.split():
        if word not in ['the', 'a', 'an', 'of', 'and', 'or', 'de', 'la', 'el', 'los', 'las']:
            clean_word = word.strip('":,.-!?[]')
            if len(clean_word) > 2:
                query_keywords.add(clean_word)

    # Search in parallel
    search_tasks = []
    for scraper in scrapers:
        task = asyncio.create_task(scraper.search(query, page=1))
        search_tasks.append((scraper.name, task))

    for scraper_name, task in search_tasks:
        try:
            results = await asyncio.wait_for(task, timeout=30.0)

            for result in results[:5]:  # First 5 results per scraper
                url = result.get("url")
                title = result.get("title", "")
                full_title = result.get("full_title", title)

                # Filter: only include if result title contains query keywords
                title_lower = title.lower()
                title_keywords = set()
                for word in title_lower.split():
                    if word not in ['the', 'a', 'an', 'of', 'and', 'or', 'de', 'la', 'el', 'los', 'las']:
                        clean_word = word.strip('":,.-!?[]')
                        if len(clean_word) > 2:
                            title_keywords.add(clean_word)

                # Require at least 50% keyword match
                common_keywords = query_keywords & title_keywords
                if len(common_keywords) < max(1, len(query_keywords) * 0.5):
                    continue  # Skip irrelevant results

                if url and url not in seen_urls:
                    seen_urls.add(url)

                    # Use full_title (with brackets) for bundle detection
                    bundle_info = detect_bundle(full_title, "", 0)
                    vol_info = extract_volume_info(full_title)

                    if vol_info:
                        issue_count = len(bundle_info["issues"]) if bundle_info else 0
                        found_volumes.append({
                            "number": vol_info["volume_number"],
                            "title": title,
                            "source": scraper_name,
                            "issues": issue_count,
                            "cover": result.get("cover"),
                            "url": url
                        })
                    elif bundle_info:
                        found_volumes.append({
                            "number": 0,
                            "title": title,
                            "source": scraper_name,
                            "issues": len(bundle_info["issues"]),
                            "cover": result.get("cover"),
                            "url": url
                        })
                    else:
                        found_volumes.append({
                            "number": 0,
                            "title": title,
                            "source": scraper_name,
                            "issues": 0,
                            "cover": result.get("cover"),
                            "url": url
                        })
        except Exception as e:
            logger.debug(f"Direct scraper search error for {scraper_name}: {e}")
            continue

    return found_volumes


async def quick_check_availability(title: str, publisher: str = "", count_of_issues: int = 0) -> dict:
    """
    Quick check if scrapers have sources for this comic (WITHOUT full scraping)
    Returns: {"has_sources": bool, "sources": [...], "score": int, "volumes": [...]}
    """
    from app.services.comic_scrapers import ZonaComicsScraper, MegaComicsScraper, CBRComicsScraper

    scrapers = [
        CBRComicsScraper(),
        ZonaComicsScraper(),
        MegaComicsScraper(),
    ]

    available_sources = []
    detected_volumes = []

    # Extract franchise/main keywords for fallback search
    franchise_keywords = []
    title_parts = title.split(':')
    if len(title_parts) > 1:
        franchise = title_parts[0].strip()
        franchise_keywords.append(franchise)

    words = [w.strip() for w in title.split() if w.lower() not in ['the', 'a', 'an']]
    if len(words) >= 2:
        franchise_keywords.append(f"{words[0]} {words[1]}")

    # Try quick searches in parallel with timeout
    search_tasks = []
    for scraper in scrapers:
        task = asyncio.create_task(scraper.search(title, page=1))
        search_tasks.append((scraper.name, task, title))

        for keyword in franchise_keywords[:1]:
            if keyword and keyword != title:
                fallback_task = asyncio.create_task(scraper.search(keyword, page=1))
                search_tasks.append((scraper.name, fallback_task, keyword))

    for scraper_name, task, search_query in search_tasks:
        try:
            results = await asyncio.wait_for(task, timeout=30.0)
            if results and len(results) > 0:
                title_lower = title.lower()

                # Extract main keywords for flexible matching
                title_keywords = set()
                for word in title_lower.split():
                    if word not in ['the', 'a', 'an', 'of', 'and', 'or', 'vol', 'vol.', 'volume']:
                        clean_word = word.strip('":,.-!?')
                        if len(clean_word) > 2:
                            title_keywords.add(clean_word)

                for result in results[:10]:
                    result_title = result.get("title", "").lower()

                    # Method 1: Exact match (contains)
                    exact_match = title_lower in result_title or result_title in title_lower

                    # Method 2: Keyword matching
                    result_keywords = set()
                    for word in result_title.split():
                        if word not in ['the', 'a', 'an', 'of', 'and', 'or', 'vol', 'vol.', 'volume']:
                            clean_word = word.strip('":,.-!?[]')
                            if len(clean_word) > 2:
                                result_keywords.add(clean_word)

                    common_keywords = title_keywords & result_keywords

                    keyword_match = False
                    if ':' in title_lower:
                        title_franchise = title_lower.split(':', 1)[0].strip()
                        title_subtitle = title_lower.split(':', 1)[1].strip()

                        franchise_keywords_set = set()
                        for word in title_franchise.split():
                            if word not in ['the', 'a', 'an', 'of', 'and', 'or']:
                                clean_word = word.strip('":,.-!?[]')
                                if len(clean_word) > 2:
                                    franchise_keywords_set.add(clean_word)

                        title_subtitle_keywords = set()
                        for word in title_subtitle.split():
                            if word not in ['the', 'a', 'an', 'of', 'and', 'or', 'vol', 'vol.', 'volume', 'de', 'la', 'el', 'los', 'las']:
                                clean_word = word.strip('":,.-!?[]')
                                if len(clean_word) > 2 and clean_word not in franchise_keywords_set:
                                    title_subtitle_keywords.add(clean_word)

                        if len(title_subtitle_keywords) > 0:
                            common_subtitle = title_subtitle_keywords & result_keywords
                            if len(common_subtitle) >= 1:
                                keyword_match = True
                            else:
                                franchise_match = len(franchise_keywords_set & result_keywords) >= len(franchise_keywords_set)
                                keyword_match = franchise_match
                        else:
                            keyword_match = len(common_keywords) >= 2
                    else:
                        keyword_match = len(common_keywords) >= min(2, len(title_keywords) * 0.5)

                    if exact_match or keyword_match:
                        if scraper_name not in available_sources:
                            available_sources.append(scraper_name)

                        detect_title = result.get("full_title", result.get("title", ""))
                        vol_info = extract_volume_info(detect_title)
                        bundle_info = detect_bundle(detect_title, result.get("description", ""), count_of_issues)

                        if vol_info:
                            issue_count = len(bundle_info["issues"]) if bundle_info else 0
                            existing = next((v for v in detected_volumes if v["number"] == vol_info["volume_number"] and v["url"] == result.get("url")), None)
                            if not existing:
                                detected_volumes.append({
                                    "number": vol_info["volume_number"],
                                    "title": result.get("title", ""),
                                    "source": scraper_name,
                                    "issues": issue_count,
                                    "cover": result.get("cover"),
                                    "url": result.get("url")
                                })
                        elif bundle_info:
                            issue_count = len(bundle_info["issues"])
                            existing = next((v for v in detected_volumes if v["url"] == result.get("url")), None)
                            if not existing:
                                detected_volumes.append({
                                    "number": 0,
                                    "title": result.get("title", ""),
                                    "source": scraper_name,
                                    "issues": issue_count,
                                    "cover": result.get("cover"),
                                    "url": result.get("url")
                                })
                        else:
                            existing = next((v for v in detected_volumes if v["url"] == result.get("url")), None)
                            if not existing:
                                detected_volumes.append({
                                    "number": 0,
                                    "title": result.get("title", ""),
                                    "source": scraper_name,
                                    "issues": 0,
                                    "cover": result.get("cover"),
                                    "url": result.get("url")
                                })
        except asyncio.TimeoutError:
            logger.debug(f"Quick check timeout for {scraper_name}")
            continue
        except Exception as e:
            logger.debug(f"Quick check error for {scraper_name}: {e}")
            continue

    # Calculate relevance score
    score = 100
    if any(keyword in title.lower() for keyword in ["french", "spanish", "italian", "german", "translation"]):
        score -= 30
    if any(keyword in publisher.lower() for keyword in ["urban comics", "planeta", "panini"]):
        score -= 20
    if publisher.lower() in ["image", "dc comics", "marvel", "dark horse", "idw"]:
        score += 20
    if count_of_issues >= 20:
        score += 15
    elif count_of_issues >= 10:
        score += 10
    if count_of_issues <= 10:
        if any(keyword in title.lower() for keyword in ["tpb", "hardcover", "deluxe", "complete"]):
            score += 5
    if available_sources:
        score += 30

    detected_volumes.sort(key=lambda v: v["number"])

    return {
        "has_sources": len(available_sources) > 0,
        "sources": available_sources,
        "score": max(0, score),
        "volumes": detected_volumes
    }


async def search_scrapers_for_comic(comic_id: int, title: str):
    """Background task to search scrapers for comic download links"""
    from app.database import SessionLocal
    from app.services.comic_scrapers import ZonaComicsScraper, MegaComicsScraper, CBRComicsScraper

    db = SessionLocal()
    try:
        comic = db.query(Comic).filter(Comic.id == comic_id).first()
        if not comic:
            return

        # Get issues without download URLs
        issues = db.query(ComicIssue).filter(
            ComicIssue.comic_id == comic_id,
            ComicIssue.download_url == None
        ).all()

        if not issues:
            logger.info(f"All issues for comic {comic_id} already have download URLs")
            return

        # Initialize scrapers (multiple sources for redundancy)
        scrapers = [
            CBRComicsScraper(),
            ZonaComicsScraper(),
            MegaComicsScraper(),
        ]
        total_issues = len(issues)

        logger.info(f"Searching sources for '{title}' ({total_issues} issues without links)")

        # Get publisher and writers for better search
        publisher = comic.publisher or ""
        publisher_short = publisher.split()[0] if publisher else ""
        writers = comic.writers or []
        main_writer = writers[0] if writers else ""
        writer_name = main_writer.split()[-1] if main_writer else ""

        # Strategy 1: For short/medium series (<=50 issues), search for complete/TPB first
        if total_issues <= 50:
            collection_queries = []

            if len(title) <= 5:
                if main_writer:
                    collection_queries.extend([
                        f"{title} {main_writer}",
                        f"{title} {writer_name}",
                    ])
                if publisher_short:
                    collection_queries.extend([
                        f"{title} {publisher_short}",
                    ])

            collection_queries.extend([
                f"{title} TPB",
                f"{title} HC",
                f"{title} complete collection",
                f'"{title}"',
                f"{title}",
            ])

            for query in collection_queries:
                logger.info(f"Trying collection search: '{query}'")

                for scraper in scrapers:
                    logger.info(f"Trying {scraper.name} scraper...")
                    results = await scraper.search(query)

                    for result in results:
                        result_title = result.get("title", "")
                        if not title_matches(title, result_title):
                            logger.debug(f"Skipping non-matching result: {result_title}")
                            continue

                        logger.info(f"Found potential match on {scraper.name}: {result_title}")

                        scrape_result = await scraper.get_download_links(result["url"])
                        if scrape_result.success and scrape_result.best_link:
                            link_url = scrape_result.best_link.url
                            is_shortener = scrape_result.best_link.link_status in ('shortener', 'needs_captcha')
                            is_active = True if is_shortener else await verify_link_active(link_url)
                            if is_active:
                                bundle_info = detect_bundle(
                                    result_title,
                                    result.get("description", ""),
                                    total_issues
                                )

                                if bundle_info:
                                    bundle_id = hashlib.md5(result["url"].encode()).hexdigest()[:16]
                                    issues_covered = bundle_info["issues"]
                                    assigned_count = 0
                                    first_assigned = True

                                    for issue_num in issues_covered:
                                        issue = next((i for i in issues if i.issue_number == str(issue_num)), None)
                                        if issue and not issue.download_url:
                                            issue.bundle_id = bundle_id
                                            issue.bundle_title = result_title
                                            issue.bundle_range = bundle_info["range"]
                                            issue.is_bundle_master = first_assigned
                                            issue.download_url = link_url
                                            issue.source = f"{scraper.name} (bundle)"
                                            issue.link_status = scrape_result.best_link.link_status

                                            if scrape_result.backup_link and issue.is_bundle_master:
                                                backup_url = scrape_result.backup_link.url
                                                backup_is_shortener = scrape_result.backup_link.link_status in ('shortener', 'needs_captcha')
                                                if backup_is_shortener or await verify_link_active(backup_url):
                                                    issue.backup_url = backup_url

                                            assigned_count += 1
                                            first_assigned = False

                                    logger.info(f"BUNDLE: '{result_title}' covers {assigned_count} issues ({bundle_info['range']})")
                                    db.commit()

                                    if assigned_count == len(issues):
                                        logger.info(f"Bundle covers all issues, search complete!")
                                        if not comic.source_urls:
                                            comic.source_urls = {}
                                        comic.source_urls[scraper.name] = result["url"]
                                        comic.last_check = datetime.utcnow()
                                        db.commit()
                                        return
                                    else:
                                        logger.info(f"Bundle covers {assigned_count}/{len(issues)} issues, continuing search...")
                                        issues = db.query(ComicIssue).filter(
                                            ComicIssue.comic_id == comic_id,
                                            ComicIssue.download_url == None
                                        ).all()
                                        if not issues:
                                            logger.info("All issues now have URLs!")
                                            return
                                        continue

                                else:
                                    first_issue = issues[0]
                                    first_issue.download_url = link_url
                                    first_issue.source = f"{scraper.name} (collection)"
                                    first_issue.link_status = scrape_result.best_link.link_status

                                    if scrape_result.backup_link:
                                        backup_url = scrape_result.backup_link.url
                                        backup_is_shortener = scrape_result.backup_link.link_status in ('shortener', 'needs_captcha')
                                        if backup_is_shortener or await verify_link_active(backup_url):
                                            first_issue.backup_url = backup_url

                                    logger.info(f"Found verified collection link for '{title}': {result_title}")
                                    db.commit()

                                    if not comic.source_urls:
                                        comic.source_urls = {}
                                    comic.source_urls[scraper.name] = result["url"]
                                    comic.last_check = datetime.utcnow()
                                    db.commit()
                                    return
                            else:
                                logger.warning(f"Link inactive/dead: {link_url[:50]}...")

                await asyncio.sleep(1)

        # Strategy 2: Search for individual issues
        logger.info(f"Searching individual issues for '{title}' using all {len(scrapers)} scrapers")
        for issue in issues:
            try:
                issue_num = issue.issue_number or "1"
                found_link = False

                for scraper in scrapers:
                    if found_link:
                        break

                    logger.info(f"Trying {scraper.name} for issue #{issue_num}")

                    search_patterns = [
                        f"{title} #{issue_num}",
                        f"{title} {issue_num}",
                    ]

                    for pattern in search_patterns:
                        if found_link:
                            break

                        if not hasattr(scraper, 'search_for_issue'):
                            logger.debug(f"{scraper.name} doesn't support issue-specific search, skipping")
                            break

                        logger.info(f"Searching: '{pattern}'")
                        result = await scraper.search_for_issue(title, f"#{issue_num}")

                        if result and result.get("url"):
                            result_title = result.get("title", "")

                            if not title_matches(title, result_title):
                                logger.warning(f"Skipping non-matching result for '{pattern}': {result_title}")
                                continue

                            scrape_result = await scraper.get_download_links(result["url"])

                            if scrape_result.success and scrape_result.best_link:
                                link_url = scrape_result.best_link.url
                                logger.debug(f"Found best_link URL for issue {issue.id} (#{issue_num}): {link_url[:80]}")

                                is_shortener = scrape_result.best_link.link_status in ('shortener', 'needs_captcha')

                                if is_shortener:
                                    logger.info(f"URL shortener detected, skipping verification: {link_url[:60]}...")
                                    is_active = True
                                else:
                                    is_active = await verify_link_active(link_url)
                                    logger.debug(f"Link verification: {is_active} for {link_url[:60]}")

                                if is_active:
                                    logger.debug(f"Assigning URL to issue {issue.id} (#{issue_num}): {link_url[:60]}")
                                    issue.download_url = link_url
                                    issue.source = scraper.name
                                    issue.link_status = scrape_result.best_link.link_status

                                    if scrape_result.backup_link:
                                        backup_url = scrape_result.backup_link.url
                                        backup_is_shortener = scrape_result.backup_link.link_status in ('shortener', 'needs_captcha')
                                        if backup_is_shortener or await verify_link_active(backup_url):
                                            issue.backup_url = backup_url
                                            logger.debug(f"Backup URL assigned for issue {issue.id}")

                                    logger.info(f"Found verified link for {title} #{issue_num} on {scraper.name}")
                                    db.commit()
                                    found_link = True
                                    break
                                else:
                                    logger.warning(f"Link inactive for {title} #{issue_num} on {scraper.name}")

                    await asyncio.sleep(1)

                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"Error searching for {title} #{issue.issue_number}: {e}")
                continue

        # POST-PROCESSING: Detect bundles from duplicate download URLs
        all_issues = db.query(ComicIssue).filter(
            ComicIssue.comic_id == comic_id,
            ComicIssue.download_url != None,
            ComicIssue.bundle_id == None
        ).order_by(ComicIssue.issue_number).all()

        url_groups = {}
        for issue in all_issues:
            if issue.download_url not in url_groups:
                url_groups[issue.download_url] = []
            url_groups[issue.download_url].append(issue)

        for url, group_issues in url_groups.items():
            if len(group_issues) >= 2:
                bundle_id = hashlib.md5(url.encode()).hexdigest()[:16]
                issue_nums = [i.issue_number for i in group_issues]
                bundle_range = f"#{issue_nums[0]}-{issue_nums[-1]}"
                bundle_title = f"{title} ({bundle_range})"

                logger.info(f"Bundle detected: {len(group_issues)} issues share URL {url[:60]}...")
                for idx, issue in enumerate(group_issues):
                    issue.bundle_id = bundle_id
                    issue.bundle_title = bundle_title
                    issue.bundle_range = bundle_range
                    issue.is_bundle_master = (idx == 0)
                    issue.source = f"{issue.source} (bundle)" if issue.source and "(bundle)" not in issue.source else issue.source

                logger.info(f"Created bundle: {bundle_title} - master: issue #{group_issues[0].issue_number}")

        # Update source_urls on comic
        if not comic.source_urls:
            comic.source_urls = {}
        comic.source_urls["scrapers"] = f"searched:{title}"
        comic.last_check = datetime.utcnow()

        issues_with_urls = sum(1 for i in all_issues if i.download_url is not None)
        logger.info(f"{issues_with_urls}/{len(all_issues)} issues have download URLs")

        db.commit()
        logger.info(f"Finished searching sources for comic {comic_id}")

    except Exception as e:
        logger.error(f"Error searching scrapers for comic {comic_id}: {e}")
    finally:
        db.close()
