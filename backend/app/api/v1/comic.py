"""
Comic API Endpoints
American comics library management with ComicVine integration
"""

import asyncio
import hashlib
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from slugify import slugify

from app.database import get_db
from app.models.comic import Comic, ComicIssue
from app.models.download import DownloadQueue
from app.services.comicvine import get_comicvine_service
from app.schemas.comic import (
    VolumeInfo,
    ComicSearchResult,
    ComicSearchResponse,
    VolumeToAdd,
    ComicCreate,
    ComicResponse,
    ComicDetailResponse,
    IssueResponse,
    ComicUpdate,
    ComicStats,
    ComicIssueStats,
    IssueDownloadRequest,
)
from app.services.comic_service import (
    fetch_comic_issues,
    fetch_issues_and_search_sources,
    fetch_volume_from_scraper,
    refresh_comic_metadata,
    translate_comic_title,
    search_scrapers_directly,
    quick_check_availability,
    search_scrapers_for_comic,
)
from app.models.user import User
from app.core.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/comics", tags=["comics"])


# ============================================================================
# SEARCH - ComicVine Integration
# ============================================================================

@router.get("/search", response_model=ComicSearchResponse)
async def search_comics(
    q: str = Query(..., min_length=2, description="Search query"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    check_availability: bool = Query(True, description="Check if sources are available (slower but filters results)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Search comics on ComicVine with optional source availability checking

    When check_availability=True:
    - Checks if download sources exist for each comic
    - Filters and ranks results by relevance
    - Shows only comics with available sources first
    - Slightly slower but much more useful
    """
    comicvine = get_comicvine_service()
    search_result = await comicvine.search_volumes(q, page=page, per_page=limit)

    if search_result.get('error'):
        raise HTTPException(status_code=503, detail=search_result['error'])

    results = []

    # Prepare results with basic info
    for item in search_result.get('results', []):
        # Check if in library
        in_library = db.query(Comic).filter(Comic.comicvine_id == item['comicvine_id'], Comic.user_id == current_user.id).first()

        # Clean start_year - ComicVine sometimes returns strings like ' 1999'
        start_year = item.get('start_year')
        if start_year is not None:
            if isinstance(start_year, str):
                start_year = start_year.strip()
                start_year = int(start_year) if start_year.isdigit() else None
            elif not isinstance(start_year, int):
                start_year = None

        # Clean count_of_issues
        count_of_issues = item.get('count_of_issues')
        if count_of_issues is not None:
            if isinstance(count_of_issues, str):
                count_of_issues = count_of_issues.strip()
                count_of_issues = int(count_of_issues) if count_of_issues.isdigit() else None
            elif not isinstance(count_of_issues, int):
                count_of_issues = None

        result = ComicSearchResult(
            comicvine_id=item['comicvine_id'],
            title=item['title'],
            description=item.get('description', '')[:300] + '...' if item.get('description') and len(item.get('description', '')) > 300 else item.get('description'),
            cover_image=item.get('cover_image'),
            publisher=item.get('publisher'),
            start_year=start_year,
            count_of_issues=count_of_issues,
            comicvine_url=item.get('comicvine_url'),
            in_library=bool(in_library),
            library_id=in_library.id if in_library else None
        )
        results.append((result, item))  # Keep original item for availability check

    # Check availability if requested
    if check_availability:
        logger.info(f"Checking availability for {len(results)} comic results...")
        availability_tasks = []
        for result, item in results:
            task = quick_check_availability(
                title=item['title'],
                publisher=item.get('publisher', ''),
                count_of_issues=result.count_of_issues or 0
            )
            availability_tasks.append(task)

        # Wait for all availability checks
        availability_results = await asyncio.gather(*availability_tasks, return_exceptions=True)

        # Update results with availability info
        for i, avail in enumerate(availability_results):
            if isinstance(avail, Exception):
                logger.warning(f"Availability check failed: {avail}")
                continue

            results[i][0].has_sources = avail['has_sources']
            results[i][0].available_sources = avail['sources']
            results[i][0].relevance_score = avail['score']
            results[i][0].volumes = [VolumeInfo(**v) for v in avail.get('volumes', [])]

        # Sort by relevance score (highest first)
        results.sort(key=lambda x: x[0].relevance_score, reverse=True)

        logger.info(f"Availability check complete. Scores: {[r[0].relevance_score for r in results]}")

        # ALWAYS try direct scraper search to find Spanish titles
        # This helps when users search in Spanish but ComicVine returns English results
        if True:  # Always search for better Spanish matches
            logger.info(f"Searching scrapers directly for Spanish results: '{q}'")
            direct_volumes = await search_scrapers_directly(q)

            if direct_volumes:
                # Create a virtual "Search Results" comic with these volumes
                virtual_comic = ComicSearchResult(
                    comicvine_id=0,  # Virtual ID
                    title=f"Resultados para '{q}'",
                    description="Resultados encontrados directamente en sitios de descarga",
                    cover_image=direct_volumes[0].get('cover') if direct_volumes else None,
                    publisher="Resultados de búsqueda",
                    start_year=None,
                    count_of_issues=sum(v.get('issues', 0) for v in direct_volumes),
                    comicvine_url=None,
                    in_library=False,
                    library_id=None,
                    has_sources=True,
                    available_sources=list(set(v.get('source') for v in direct_volumes)),
                    relevance_score=200,  # Higher than normal to show first
                    volumes=[VolumeInfo(**v) for v in direct_volumes]
                )
                results.insert(0, (virtual_comic, {}))
                logger.info(f"Added virtual comic with {len(direct_volumes)} direct volumes")

    # Extract just the results (without original items)
    final_results = [r[0] for r in results]

    return ComicSearchResponse(
        results=final_results,
        total=search_result.get('total', 0),
        page=page,
        per_page=limit
    )


@router.get("/comicvine/{comicvine_id}")
async def get_comicvine_details(
    comicvine_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed comic info from ComicVine (preview before adding)
    """
    comicvine = get_comicvine_service()
    details = await comicvine.get_volume(comicvine_id)

    if not details:
        raise HTTPException(status_code=404, detail="Comic not found on ComicVine")

    # Check if in library
    in_library = db.query(Comic).filter(Comic.comicvine_id == comicvine_id, Comic.user_id == current_user.id).first()
    
    return {
        **details,
        'in_library': bool(in_library),
        'library_id': in_library.id if in_library else None
    }


# ============================================================================
# LIBRARY MANAGEMENT
# ============================================================================

@router.get("/", response_model=List[ComicResponse])
async def get_library(
    monitored: Optional[bool] = None,
    publisher: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = Query("title", regex="^(title|created_at|start_year)$"),
    order: str = Query("asc", regex="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get comics library with filters
    """
    query = db.query(Comic).filter(Comic.user_id == current_user.id)
    
    # Filters
    if monitored is not None:
        query = query.filter(Comic.monitored == monitored)
    
    if publisher:
        query = query.filter(Comic.publisher.ilike(f"%{publisher}%"))
    
    if search:
        query = query.filter(
            or_(
                Comic.title.ilike(f"%{search}%"),
                Comic.publisher.ilike(f"%{search}%")
            )
        )
    
    # Sorting
    sort_column = getattr(Comic, sort, Comic.title)
    if order == "desc":
        sort_column = sort_column.desc()
    query = query.order_by(sort_column)
    
    # Pagination
    total = query.count()
    comics = query.offset((page - 1) * limit).limit(limit).all()
    
    # Build response
    result = []
    for comic in comics:
        result.append(ComicResponse(
            id=comic.id,
            title=comic.title,
            slug=comic.slug,
            comicvine_id=comic.comicvine_id,
            description=comic.description,
            cover_image=comic.cover_image,
            publisher=comic.publisher,
            start_year=comic.start_year,
            count_of_issues=comic.count_of_issues,
            writers=comic.writers,
            artists=comic.artists,
            comicvine_url=comic.comicvine_url,
            monitored=comic.monitored,
            total_issues=comic.total_issues,
            downloaded_issues=comic.downloaded_issues
        ))
    
    return result


@router.post("/from-url", response_model=ComicResponse)
async def add_comic_from_url(
    title: str,
    url: str,
    source: str,
    issues: int = 0,
    cover: str = None,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Add comic directly from scraper URL (for Spanish search results)
    Tries to find metadata from ComicVine by translating common terms
    """
    import re as _re

    # If issues=0, try to extract from title patterns like [80 números] or [15 volúmenes]
    if issues == 0:
        num_match = _re.search(r'\[(\d+)\s+n[uú]meros?\]', title, _re.IGNORECASE)
        if num_match:
            issues = int(num_match.group(1))
            logger.info(f"Extracted {issues} issues from title pattern [X números]")
        else:
            vol_match = _re.search(r'\[(\d+)\s+(?:vol[uú]menes?|tomos?)\]', title, _re.IGNORECASE)
            if vol_match:
                issues = int(vol_match.group(1))
                logger.info(f"Extracted {issues} issues from title pattern [X volúmenes/tomos]")

    slug = slugify(title)

    # Check if already exists for this user
    existing = db.query(Comic).filter(Comic.slug == slug, Comic.user_id == current_user.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Comic already in library")

    # Try to find in ComicVine — always attempt, even if title doesn't change after translation
    comicvine_details = None
    translated_title = translate_comic_title(title)
    comicvine = get_comicvine_service()

    # Search queries to try (in order): translated title, original title, first 2-3 words
    search_queries = []
    if translated_title.lower() != title.lower():
        search_queries.append(translated_title)
    search_queries.append(title)

    # Fuzzy fallback: first 2-3 significant words (skip articles)
    skip_words = {'el', 'la', 'los', 'las', 'de', 'del', 'the', 'a', 'an', 'of', 'en', 'y', 'and'}
    significant_words = [w for w in translated_title.split() if w.lower() not in skip_words]
    if len(significant_words) >= 2:
        fuzzy_query = ' '.join(significant_words[:3])
        if fuzzy_query.lower() not in [q.lower() for q in search_queries]:
            search_queries.append(fuzzy_query)

    for query in search_queries:
        logger.info(f"Searching ComicVine for: '{query}'")
        search_result = await comicvine.search_volumes(query, page=1, per_page=5)

        if search_result.get('results'):
            for result in search_result['results'][:3]:
                details = await comicvine.get_volume(result['comicvine_id'])
                if details:
                    comicvine_details = details
                    logger.info(f"Found ComicVine match: {details['title']} (ID: {details['comicvine_id']})")
                    break
        if comicvine_details:
            break

    # Create comic with ComicVine metadata if found, otherwise basic info
    if comicvine_details:
        comic = Comic(
            title=title,  # Keep Spanish title
            slug=slug,
            comicvine_id=comicvine_details['comicvine_id'],
            title_original=comicvine_details['title'],  # English title
            description=comicvine_details.get('description'),
            cover_image=cover or comicvine_details.get('cover_image'),
            publisher=comicvine_details.get('publisher'),
            start_year=comicvine_details.get('start_year'),
            writers=comicvine_details.get('writers'),
            artists=comicvine_details.get('artists'),
            comicvine_url=comicvine_details.get('comicvine_url'),
            comicvine_search_attempted=True,
            monitored=True,
            user_id=current_user.id
        )
        logger.info(f"Created comic with ComicVine metadata")
    else:
        comic = Comic(
            title=title,
            slug=slug,
            comicvine_id=None,
            description=f"Comic añadido directamente desde {source}",
            cover_image=cover,
            comicvine_search_attempted=True,
            publisher="Unknown",
            monitored=True,
            user_id=current_user.id
        )
        logger.info(f"Created comic without ComicVine metadata")
    db.add(comic)
    db.flush()  # Get comic ID

    # Create issues based on count
    for i in range(1, issues + 1):
        issue = ComicIssue(
            comic_id=comic.id,
            issue_number=str(i),
            status="pending"
        )
        db.add(issue)

    # Flush to make issues visible to subsequent queries (autoflush=False)
    if issues > 0:
        db.flush()

    # Save the scraper page URL as source reference (NOT as download_url)
    # The actual download links (mega, mediafire, etc.) will be resolved by
    # fetch_volume_from_scraper which calls get_download_links() on the scraper
    if not comic.source_urls:
        comic.source_urls = {}
    comic.source_urls[source] = url

    db.commit()
    db.refresh(comic)

    # Launch background task to resolve actual download links from the scraper page
    if issues > 0 and background_tasks:
        background_tasks.add_task(
            fetch_volume_from_scraper,
            comic.id,
            url,      # scraper page URL — get_download_links() resolves the real links
            source,
            issues
        )

    logger.info(f"Added comic from scraper: {title} ({issues} issues) from {source}")

    return ComicResponse(
        id=comic.id,
        title=comic.title,
        slug=comic.slug,
        comicvine_id=comic.comicvine_id,
        description=comic.description,
        cover_image=comic.cover_image,
        publisher=comic.publisher,
        monitored=comic.monitored,
        total_issues=issues,
        downloaded_issues=0
    )


@router.post("/", response_model=ComicResponse)
async def add_comic(
    data: ComicCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    force: bool = Query(False, description="Skip duplicate check")
):
    """
    Add comic to library from ComicVine

    If volume_to_add is provided, creates a separate comic for that specific volume
    """
    # Fetch details from ComicVine
    comicvine = get_comicvine_service()
    details = await comicvine.get_volume(data.comicvine_id)

    if not details:
        raise HTTPException(status_code=404, detail="Comic not found on ComicVine")

    # If adding a specific volume, modify title and issue count
    if data.volume_to_add:
        title = f"{details['title']} Vol {data.volume_to_add.number}"
        slug = slugify(title)
        count_of_issues = data.volume_to_add.issues

        # Check if this specific volume already exists for this user
        existing = db.query(Comic).filter(Comic.slug == slug, Comic.user_id == current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Vol {data.volume_to_add.number} already in library")
    else:
        title = details['title']
        slug = slugify(title)
        count_of_issues = details.get('count_of_issues')

        # Check if already exists for this user
        existing = db.query(Comic).filter(Comic.comicvine_id == data.comicvine_id, Comic.user_id == current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Comic already in library")

    # Feature 6: Fuzzy duplicate check (skip if force=True)
    if not force:
        from app.services.content_matcher import ContentMatcher
        matcher = ContentMatcher()
        duplicate = matcher.find_duplicate(db, title, 'comic', current_user.id)
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail={"message": "Posible duplicado encontrado", "matched_id": duplicate.id, "matched_title": duplicate.title}
            )

    # Create comic
    comic = Comic(
        title=title,
        slug=slug,
        comicvine_id=details['comicvine_id'] if not data.volume_to_add else None,  # Only set for base comic
        title_original=details['title'],
        aliases=details.get('aliases'),
        description=details.get('description'),
        cover_image=details.get('cover_image'),
        publisher=details.get('publisher'),
        start_year=details.get('start_year'),
        count_of_issues=count_of_issues,
        writers=details.get('writers'),
        artists=details.get('artists'),
        colorists=details.get('colorists'),
        characters=details.get('characters'),
        comicvine_url=details.get('comicvine_url'),
        monitored=True,
        auto_download=True,
        user_id=current_user.id,
        created_at=datetime.utcnow()
    )

    db.add(comic)
    db.commit()
    db.refresh(comic)

    # If adding a specific volume, fetch from scraper directly
    if data.volume_to_add:
        background_tasks.add_task(
            fetch_volume_from_scraper,
            comic.id,
            data.volume_to_add.url,
            data.volume_to_add.source,
            data.volume_to_add.issues
        )
        logger.info(f"Added volume to library: {comic.title} ({data.volume_to_add.issues} issues)")
    else:
        # Fetch issues from ComicVine + search scrapers + auto-queue downloads
        background_tasks.add_task(fetch_issues_and_search_sources, comic.id, data.comicvine_id)
        logger.info(f"Added comic to library: {comic.title} (will auto-search sources)")

    return ComicResponse(
        id=comic.id,
        title=comic.title,
        slug=comic.slug,
        comicvine_id=comic.comicvine_id,
        description=comic.description,
        cover_image=comic.cover_image,
        publisher=comic.publisher,
        start_year=comic.start_year,
        count_of_issues=comic.count_of_issues,
        writers=comic.writers,
        artists=comic.artists,
        comicvine_url=comic.comicvine_url,
        monitored=comic.monitored,
        total_issues=0,
        downloaded_issues=0
    )


@router.get("/stats", response_model=ComicStats)
async def get_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Get comic library statistics
    """
    user_comic_ids = db.query(Comic.id).filter(Comic.user_id == current_user.id).subquery()
    total_comics = db.query(func.count(Comic.id)).filter(Comic.user_id == current_user.id).scalar()
    monitored_comics = db.query(func.count(Comic.id)).filter(Comic.user_id == current_user.id, Comic.monitored == True).scalar()
    total_issues = db.query(func.count(ComicIssue.id)).filter(ComicIssue.comic_id.in_(user_comic_ids)).scalar()
    downloaded_issues = db.query(func.count(ComicIssue.id)).filter(ComicIssue.comic_id.in_(user_comic_ids), ComicIssue.status == "downloaded").scalar()
    
    return ComicStats(
        total_comics=total_comics or 0,
        monitored_comics=monitored_comics or 0,
        total_issues=total_issues or 0,
        downloaded_issues=downloaded_issues or 0
    )


@router.get("/{comic_id}", response_model=ComicDetailResponse)
async def get_comic(
    comic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get comic details with issues
    """
    comic = db.query(Comic).filter(Comic.id == comic_id, Comic.user_id == current_user.id).first()
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")
    
    # Get issues
    issues = db.query(ComicIssue).filter(
        ComicIssue.comic_id == comic_id
    ).order_by(ComicIssue.issue_number).all()
    
    issues_data = [
        {
            'id': issue.id,
            'issue_number': issue.issue_number,
            'title': issue.title,
            'cover_image': issue.cover_image,
            'release_date': issue.release_date,
            'status': issue.status,
            'file_path': issue.file_path,
            'converted_path': issue.converted_path,
            'converted_at': issue.converted_at.isoformat() if issue.converted_at else None,
            'download_url': issue.download_url,
            'backup_url': issue.backup_url,
            'source': issue.source,
            'sent_at': issue.sent_at.isoformat() if issue.sent_at else None,
            'file_size': issue.file_size,
            'bundle_id': issue.bundle_id,
            'bundle_title': issue.bundle_title,
            'bundle_range': issue.bundle_range,
            'is_bundle_master': issue.is_bundle_master
        }
        for issue in issues
    ]
    
    return ComicDetailResponse(
        id=comic.id,
        title=comic.title,
        slug=comic.slug,
        comicvine_id=comic.comicvine_id,
        description=comic.description,
        cover_image=comic.cover_image,
        publisher=comic.publisher,
        start_year=comic.start_year,
        count_of_issues=comic.count_of_issues,
        writers=comic.writers,
        artists=comic.artists,
        colorists=comic.colorists,
        characters=comic.characters,
        aliases=comic.aliases,
        comicvine_url=comic.comicvine_url,
        source_urls=comic.source_urls,
        monitored=comic.monitored,
        total_issues=comic.total_issues,
        downloaded_issues=comic.downloaded_issues,
        issues=issues_data
    )


@router.patch("/{comic_id}", response_model=ComicResponse)
async def update_comic(
    comic_id: int,
    data: ComicUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update comic settings
    """
    comic = db.query(Comic).filter(Comic.id == comic_id, Comic.user_id == current_user.id).first()
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")
    
    if data.monitored is not None:
        comic.monitored = data.monitored
    if data.auto_download is not None:
        comic.auto_download = data.auto_download
    if data.preferred_source is not None:
        comic.preferred_source = data.preferred_source
    
    comic.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(comic)
    
    return ComicResponse(
        id=comic.id,
        title=comic.title,
        slug=comic.slug,
        comicvine_id=comic.comicvine_id,
        description=comic.description,
        cover_image=comic.cover_image,
        publisher=comic.publisher,
        start_year=comic.start_year,
        count_of_issues=comic.count_of_issues,
        writers=comic.writers,
        artists=comic.artists,
        comicvine_url=comic.comicvine_url,
        monitored=comic.monitored,
        total_issues=comic.total_issues,
        downloaded_issues=comic.downloaded_issues
    )


@router.delete("/{comic_id}")
async def delete_comic(
    comic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Remove comic from library
    """
    comic = db.query(Comic).filter(Comic.id == comic_id, Comic.user_id == current_user.id).first()
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")
    
    title = comic.title
    db.delete(comic)
    db.commit()
    
    logger.info(f"Removed comic from library: {title}")
    
    return {"message": f"Removed '{title}' from library"}


@router.post("/{comic_id}/refresh")
async def refresh_comic(
    comic_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Refresh comic metadata and issues from ComicVine
    """
    comic = db.query(Comic).filter(Comic.id == comic_id, Comic.user_id == current_user.id).first()
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")
    
    if not comic.comicvine_id:
        raise HTTPException(status_code=400, detail="Comic has no ComicVine ID")
    
    # Refresh in background
    background_tasks.add_task(refresh_comic_metadata, comic_id, comic.comicvine_id)
    
    return {"message": "Refresh started"}


# ============================================================================
# ISSUES
# ============================================================================

@router.get("/{comic_id}/issues", response_model=List[IssueResponse])
async def get_issues(
    comic_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all issues for a comic
    """
    query = db.query(ComicIssue).filter(ComicIssue.comic_id == comic_id)
    
    if status:
        query = query.filter(ComicIssue.status == status)
    
    issues = query.order_by(ComicIssue.issue_number).all()
    
    return [IssueResponse(
        id=issue.id,
        comic_id=issue.comic_id,
        issue_number=issue.issue_number,
        title=issue.title,
        cover_image=issue.cover_image,
        release_date=issue.release_date,
        status=issue.status,
        file_path=issue.file_path,
        converted_path=issue.converted_path,
        converted_at=issue.converted_at.isoformat() if issue.converted_at else None,
        download_url=issue.download_url,
        backup_url=issue.backup_url,
        source=issue.source,
        sent_at=issue.sent_at.isoformat() if issue.sent_at else None,
        file_size=issue.file_size
    ) for issue in issues]


# ============================================================================
# DOWNLOAD & SCRAPER ENDPOINTS
# ============================================================================

@router.get("/{comic_id}/stats", response_model=ComicIssueStats)
async def get_comic_stats(
    comic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get download statistics for a specific comic"""
    comic = db.query(Comic).filter(Comic.id == comic_id, Comic.user_id == current_user.id).first()
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")

    issues = db.query(ComicIssue).filter(ComicIssue.comic_id == comic_id).all()

    return ComicIssueStats(
        total_issues=len(issues),
        downloaded=sum(1 for i in issues if i.status in ["downloaded", "converted"]),
        downloading=sum(1 for i in issues if i.status == "downloading"),
        pending=sum(1 for i in issues if i.status == "pending"),
        failed=sum(1 for i in issues if i.status == "error"),
        sent_to_kindle=sum(1 for i in issues if i.status == "sent")
    )


@router.post("/{comic_id}/issues/download")
async def download_issues(
    comic_id: int,
    data: IssueDownloadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Queue selected issues for download via DownloadQueue"""
    comic = db.query(Comic).filter(Comic.id == comic_id, Comic.user_id == current_user.id).first()
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")

    # Get issues to download
    issues = db.query(ComicIssue).filter(
        ComicIssue.id.in_(data.issue_ids),
        ComicIssue.comic_id == comic_id
    ).all()

    if not issues:
        raise HTTPException(status_code=404, detail="No issues found")

    # AUTO-BUNDLE DETECTION: If multiple issues share the same download URL
    # and don't have a bundle_id yet, create a bundle automatically
    url_groups = {}
    for issue in issues:
        if issue.download_url and not issue.bundle_id:
            if issue.download_url not in url_groups:
                url_groups[issue.download_url] = []
            url_groups[issue.download_url].append(issue)

    for url, group in url_groups.items():
        if len(group) >= 2:
            bundle_id = hashlib.md5(url.encode()).hexdigest()[:16]
            issue_nums = sorted([i.issue_number for i in group], key=lambda x: int(x) if x.isdigit() else 0)
            bundle_range = f"#{issue_nums[0]}-{issue_nums[-1]}"
            bundle_title = f"{comic.title} ({bundle_range})"

            # Also check if there are MORE issues with same URL not in the selection
            all_same_url = db.query(ComicIssue).filter(
                ComicIssue.comic_id == comic_id,
                ComicIssue.download_url == url,
                ComicIssue.bundle_id == None
            ).order_by(ComicIssue.issue_number).all()

            if len(all_same_url) >= 2:
                all_nums = sorted([i.issue_number for i in all_same_url], key=lambda x: int(x) if x.isdigit() else 0)
                bundle_range = f"#{all_nums[0]}-{all_nums[-1]}"
                bundle_title = f"{comic.title} ({bundle_range})"

                for idx, bi in enumerate(all_same_url):
                    bi.bundle_id = bundle_id
                    bi.bundle_title = bundle_title
                    bi.bundle_range = bundle_range
                    bi.is_bundle_master = (idx == 0)
                    if "(bundle)" not in (bi.source or ""):
                        bi.source = f"{bi.source} (bundle)" if bi.source else "bundle"

                logger.info(f"Auto-detected bundle: {bundle_title} ({len(all_same_url)} issues, master: #{all_same_url[0].issue_number})")

            db.commit()
            # Refresh issues list after bundle assignment
            issues = db.query(ComicIssue).filter(
                ComicIssue.id.in_(data.issue_ids),
                ComicIssue.comic_id == comic_id
            ).all()

    queued = 0
    for issue in issues:
        if not issue.download_url:
            logger.warning(f"Issue {issue.id} has no download URL")
            continue

        if issue.status in ["downloading", "downloaded"]:
            logger.info(f"Issue {issue.id} already downloaded/downloading")
            continue

        # BUNDLE: Skip non-master issues (master will handle them)
        if issue.bundle_id and not issue.is_bundle_master:
            logger.info(f"Issue #{issue.issue_number} is part of bundle - master will download")
            continue

        # Check if already in queue
        existing_queue = db.query(DownloadQueue).filter(
            DownloadQueue.comic_issue_id == issue.id,
            DownloadQueue.status.in_(['queued', 'downloading'])
        ).first()

        if existing_queue:
            logger.info(f"Issue {issue.id} already in download queue")
            continue

        # Mark issue as downloading
        issue.status = "downloading"
        issue.error_message = None

        # Create DownloadQueue item (scheduler will process it)
        queue_item = DownloadQueue(
            comic_issue_id=issue.id,
            content_type='comic',
            status='queued',
            priority=0
        )
        db.add(queue_item)
        queued += 1

    db.commit()

    return {"message": f"Queued {queued} issues for download", "queued": queued}


@router.post("/{comic_id}/search-sources")
async def search_sources(
    comic_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Search scrapers for download links"""
    comic = db.query(Comic).filter(Comic.id == comic_id, Comic.user_id == current_user.id).first()
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")

    # If we have a known scraper page URL, resolve links directly
    if comic.source_urls:
        for src_name, src_url in comic.source_urls.items():
            issue_count = db.query(ComicIssue).filter(
                ComicIssue.comic_id == comic_id
            ).count()
            background_tasks.add_task(
                fetch_volume_from_scraper,
                comic.id, src_url, src_name, issue_count
            )
            break  # Only use first source
    else:
        background_tasks.add_task(search_scrapers_for_comic, comic.id, comic.title)

    return {"message": "Source search started"}


@router.post("/{comic_id}/issues/{issue_id}/send-to-kindle")
async def send_issue_to_kindle(
    comic_id: int,
    issue_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Send a downloaded/converted issue to Kindle via STK.
    Prefers converted EPUB over original CBZ.
    Supports sending multiple parts if file was split due to 200MB limit.
    """
    from app.services.stk_kindle_sender import get_stk_service
    from pathlib import Path

    comic = db.query(Comic).filter(Comic.id == comic_id, Comic.user_id == current_user.id).first()
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")

    issue = db.query(ComicIssue).filter(
        ComicIssue.id == issue_id,
        ComicIssue.comic_id == comic_id
    ).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    # Determine which file(s) to send - prefer converted over original
    file_paths = []

    if issue.converted_path:
        # Use converted file(s) - may be multiple parts separated by '|'
        for path_str in issue.converted_path.split('|'):
            if path_str.strip():
                file_path = Path(path_str.strip())
                if file_path.exists():
                    file_paths.append(file_path)
                else:
                    logger.warning(f"Converted file not found: {path_str}")

    # Fallback to original file if no converted files found
    if not file_paths and issue.file_path:
        original_path = Path(issue.file_path)
        if original_path.exists():
            file_paths.append(original_path)

    if not file_paths:
        raise HTTPException(status_code=400, detail="No files available to send")

    # Get STK service
    stk = await get_stk_service()
    if not stk or not stk.is_authenticated:
        raise HTTPException(status_code=400, detail="STK not configured")

    # Send to Kindle
    try:
        title = f"{comic.title} - Issue #{issue.issue_number or '?'}"
        author = ", ".join(comic.writers[:2]) if comic.writers else "Unknown"

        all_success = True
        sent_files = []

        for idx, file_path in enumerate(file_paths):
            part_info = f" (Part {idx + 1}/{len(file_paths)})" if len(file_paths) > 1 else ""
            file_title = f"{title}{part_info}"

            logger.info(f"Sending to Kindle: {file_path.name}{part_info}")

            result = await stk.send_file(
                file_path=str(file_path),
                title=file_title,
                author=author
            )

            if result.get("success"):
                sent_files.append(file_path.name)
                logger.info(f"Sent: {file_path.name}")
            else:
                logger.error(f"Failed to send: {file_path.name} - {result.get('error')}")
                all_success = False

        if all_success:
            issue.status = "sent"
            issue.sent_at = datetime.utcnow()
            db.commit()

            parts_msg = f" ({len(file_paths)} partes)" if len(file_paths) > 1 else ""
            return {
                "success": True,
                "message": f"Enviado a Kindle correctamente{parts_msg}",
                "files_sent": sent_files
            }
        else:
            return {
                "success": False,
                "message": f"Algunos archivos fallaron al enviar",
                "files_sent": sent_files
            }

    except Exception as e:
        logger.error(f"Error sending to Kindle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{comic_id}/issues/{issue_id}/mark-read")
async def mark_issue_read(
    comic_id: int,
    issue_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark a comic issue as read"""
    comic = db.query(Comic).filter(Comic.id == comic_id, Comic.user_id == current_user.id).first()
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")

    issue = db.query(ComicIssue).filter(ComicIssue.id == issue_id, ComicIssue.comic_id == comic_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    issue.read_at = datetime.utcnow()
    comic.last_read_issue = issue.issue_number

    total_sent = db.query(ComicIssue).filter(
        ComicIssue.comic_id == comic_id,
        ComicIssue.status.in_(['sent', 'converted', 'downloaded'])
    ).count()
    total_read = db.query(ComicIssue).filter(
        ComicIssue.comic_id == comic_id,
        ComicIssue.read_at.isnot(None)
    ).count() + 1
    comic.reading_status = 'completed' if total_read >= total_sent and total_sent > 0 else 'reading'

    db.commit()
    return {"id": issue_id, "read_at": issue.read_at.isoformat()}


@router.post("/{comic_id}/mark-all-read")
async def mark_all_issues_read(
    comic_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark all sent/downloaded issues as read"""
    comic = db.query(Comic).filter(Comic.id == comic_id, Comic.user_id == current_user.id).first()
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")

    now = datetime.utcnow()
    issues = db.query(ComicIssue).filter(
        ComicIssue.comic_id == comic_id,
        ComicIssue.status.in_(['sent', 'converted', 'downloaded']),
        ComicIssue.read_at.is_(None)
    ).all()

    for iss in issues:
        iss.read_at = now

    if issues:
        comic.last_read_issue = issues[-1].issue_number
        comic.reading_status = 'completed'

    db.commit()
    return {"marked_read": len(issues)}
