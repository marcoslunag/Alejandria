"""
Comic API Endpoints
American comics library management with ComicVine integration
"""

import asyncio
import hashlib
import logging
from datetime import datetime
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from pydantic import BaseModel
from slugify import slugify

from app.database import get_db
from app.models.comic import Comic, ComicIssue
from app.services.comicvine import get_comicvine_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/comics", tags=["comics"])


# ============================================================================
# Pydantic Schemas
# ============================================================================

class VolumeInfo(BaseModel):
    """Information about a specific volume detected in scrapers"""
    number: int
    title: str
    source: str
    issues: int
    cover: Optional[str] = None
    url: Optional[str] = None

class ComicSearchResult(BaseModel):
    comicvine_id: int
    title: str
    description: Optional[str] = None
    cover_image: Optional[str] = None
    publisher: Optional[str] = None
    start_year: Optional[int] = None
    count_of_issues: Optional[int] = None
    comicvine_url: Optional[str] = None
    in_library: bool = False
    library_id: Optional[int] = None
    # Availability info from scrapers
    has_sources: bool = False
    available_sources: List[str] = []
    relevance_score: int = 0  # Higher = more relevant (original series > translations)
    volumes: List[VolumeInfo] = []  # Detected volumes from scrapers

class ComicSearchResponse(BaseModel):
    results: List[ComicSearchResult]
    total: int
    page: int
    per_page: int

class VolumeToAdd(BaseModel):
    """Volume information when adding a specific volume"""
    number: int
    title: str
    source: str
    issues: int
    url: str

class ComicCreate(BaseModel):
    comicvine_id: int
    volume_to_add: Optional[VolumeToAdd] = None  # If adding a specific volume

class ComicResponse(BaseModel):
    id: int
    title: str
    slug: Optional[str] = None
    comicvine_id: Optional[int] = None
    description: Optional[str] = None
    cover_image: Optional[str] = None
    publisher: Optional[str] = None
    start_year: Optional[int] = None
    count_of_issues: Optional[int] = None
    writers: Optional[List[str]] = None
    artists: Optional[List[str]] = None
    comicvine_url: Optional[str] = None
    monitored: bool = True
    total_issues: int = 0
    downloaded_issues: int = 0
    
    class Config:
        from_attributes = True

class ComicDetailResponse(ComicResponse):
    aliases: Optional[List[str]] = None
    characters: Optional[List[str]] = None
    colorists: Optional[List[str]] = None
    source_urls: Optional[dict] = None
    issues: List[dict] = []

class IssueResponse(BaseModel):
    id: int
    comic_id: int
    issue_number: Optional[str] = None
    title: Optional[str] = None
    cover_image: Optional[str] = None
    release_date: Optional[str] = None
    status: str = "pending"
    file_path: Optional[str] = None
    converted_path: Optional[str] = None  # Path(s) to converted EPUB, separated by '|' if multiple parts
    converted_at: Optional[str] = None
    download_url: Optional[str] = None
    backup_url: Optional[str] = None
    source: Optional[str] = None
    sent_at: Optional[str] = None
    file_size: Optional[int] = None

    class Config:
        from_attributes = True

class ComicUpdate(BaseModel):
    monitored: Optional[bool] = None
    auto_download: Optional[bool] = None
    preferred_source: Optional[str] = None

class ComicStats(BaseModel):
    total_comics: int
    monitored_comics: int
    total_issues: int
    downloaded_issues: int


# ============================================================================
# SEARCH - ComicVine Integration
# ============================================================================

@router.get("/search", response_model=ComicSearchResponse)
async def search_comics(
    q: str = Query(..., min_length=2, description="Search query"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    check_availability: bool = Query(True, description="Check if sources are available (slower but filters results)"),
    db: Session = Depends(get_db)
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
        in_library = db.query(Comic).filter(Comic.comicvine_id == item['comicvine_id']).first()

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
            task = _quick_check_availability(
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
            direct_volumes = await _search_scrapers_directly(q)

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
    db: Session = Depends(get_db)
):
    """
    Get detailed comic info from ComicVine (preview before adding)
    """
    comicvine = get_comicvine_service()
    details = await comicvine.get_volume(comicvine_id)
    
    if not details:
        raise HTTPException(status_code=404, detail="Comic not found on ComicVine")
    
    # Check if in library
    in_library = db.query(Comic).filter(Comic.comicvine_id == comicvine_id).first()
    
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
    db: Session = Depends(get_db)
):
    """
    Get comics library with filters
    """
    query = db.query(Comic)
    
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
    db: Session = Depends(get_db)
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

    # Check if already exists
    existing = db.query(Comic).filter(Comic.slug == slug).first()
    if existing:
        raise HTTPException(status_code=400, detail="Comic already in library")

    # Try to find in ComicVine by translating common Spanish terms
    comicvine_details = None
    translated_title = _translate_comic_title(title)

    if translated_title != title:
        logger.info(f"Translated '{title}' → '{translated_title}', searching ComicVine...")
        comicvine = get_comicvine_service()
        search_result = await comicvine.search_volumes(translated_title, page=1, per_page=5)

        if search_result.get('results'):
            # Take first result that seems like a match
            for result in search_result['results'][:3]:
                # Fetch full details
                details = await comicvine.get_volume(result['comicvine_id'])
                if details:
                    comicvine_details = details
                    logger.info(f"Found ComicVine match: {details['title']} (ID: {details['comicvine_id']})")
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
            monitored=True
        )
        logger.info(f"Created comic with ComicVine metadata")
    else:
        comic = Comic(
            title=title,
            slug=slug,
            comicvine_id=None,
            description=f"Comic añadido directamente desde {source}",
            cover_image=cover,
            publisher="Unknown",
            monitored=True
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

    # Create a bundle for all issues pointing to the scraper URL
    if issues > 0:
        bundle_id = hashlib.md5(url.encode()).hexdigest()[:16]
        bundle_title = title
        bundle_range = f"#1-{issues}" if issues > 1 else "#1"

        # Update all issues with bundle info
        issue_list = db.query(ComicIssue).filter(ComicIssue.comic_id == comic.id).all()
        for idx, issue in enumerate(issue_list):
            issue.download_url = url
            issue.source = source
            issue.bundle_id = bundle_id
            issue.bundle_title = bundle_title
            issue.bundle_range = bundle_range
            issue.is_bundle_master = (idx == 0)  # First issue downloads for all

    db.commit()
    db.refresh(comic)

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
    db: Session = Depends(get_db)
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

        # Check if this specific volume already exists (by slug)
        existing = db.query(Comic).filter(Comic.slug == slug).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Vol {data.volume_to_add.number} already in library")
    else:
        title = details['title']
        slug = slugify(title)
        count_of_issues = details.get('count_of_issues')

        # Check if already exists
        existing = db.query(Comic).filter(Comic.comicvine_id == data.comicvine_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Comic already in library")

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
        # Fetch issues from ComicVine in background
        background_tasks.add_task(fetch_comic_issues, comic.id, data.comicvine_id)
        logger.info(f"Added comic to library: {comic.title}")

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
async def get_stats(db: Session = Depends(get_db)):
    """
    Get comic library statistics
    """
    total_comics = db.query(func.count(Comic.id)).scalar()
    monitored_comics = db.query(func.count(Comic.id)).filter(Comic.monitored == True).scalar()
    total_issues = db.query(func.count(ComicIssue.id)).scalar()
    downloaded_issues = db.query(func.count(ComicIssue.id)).filter(ComicIssue.status == "downloaded").scalar()
    
    return ComicStats(
        total_comics=total_comics or 0,
        monitored_comics=monitored_comics or 0,
        total_issues=total_issues or 0,
        downloaded_issues=downloaded_issues or 0
    )


@router.get("/{comic_id}", response_model=ComicDetailResponse)
async def get_comic(
    comic_id: int,
    db: Session = Depends(get_db)
):
    """
    Get comic details with issues
    """
    comic = db.query(Comic).filter(Comic.id == comic_id).first()
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
    db: Session = Depends(get_db)
):
    """
    Update comic settings
    """
    comic = db.query(Comic).filter(Comic.id == comic_id).first()
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
    db: Session = Depends(get_db)
):
    """
    Remove comic from library
    """
    comic = db.query(Comic).filter(Comic.id == comic_id).first()
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
    db: Session = Depends(get_db)
):
    """
    Refresh comic metadata and issues from ComicVine
    """
    comic = db.query(Comic).filter(Comic.id == comic_id).first()
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
    db: Session = Depends(get_db)
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

class IssueDownloadRequest(BaseModel):
    issue_ids: List[int]


class ComicIssueStats(BaseModel):
    total_issues: int
    downloaded: int
    downloading: int
    pending: int
    failed: int
    sent_to_kindle: int


@router.get("/{comic_id}/stats", response_model=ComicIssueStats)
async def get_comic_stats(
    comic_id: int,
    db: Session = Depends(get_db)
):
    """Get download statistics for a specific comic"""
    comic = db.query(Comic).filter(Comic.id == comic_id).first()
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
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Queue selected issues for download"""
    comic = db.query(Comic).filter(Comic.id == comic_id).first()
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
    import hashlib
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

                logger.info(f"📦 Auto-detected bundle: {bundle_title} ({len(all_same_url)} issues, master: #{all_same_url[0].issue_number})")

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

        # Mark as downloading
        issue.status = "downloading"
        issue.error_message = None

        # Add to background queue
        background_tasks.add_task(_download_comic_issue, issue.id)
        queued += 1

    db.commit()

    return {"message": f"Queued {queued} issues for download", "queued": queued}


@router.post("/{comic_id}/search-sources")
async def search_sources(
    comic_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Search scrapers for download links"""
    comic = db.query(Comic).filter(Comic.id == comic_id).first()
    if not comic:
        raise HTTPException(status_code=404, detail="Comic not found")

    background_tasks.add_task(_search_scrapers_for_comic, comic.id, comic.title)

    return {"message": "Source search started"}


@router.post("/{comic_id}/issues/{issue_id}/send-to-kindle")
async def send_issue_to_kindle(
    comic_id: int,
    issue_id: int,
    db: Session = Depends(get_db)
):
    """
    Send a downloaded/converted issue to Kindle via STK.
    Prefers converted EPUB over original CBZ.
    Supports sending multiple parts if file was split due to 200MB limit.
    """
    from app.services.stk_kindle_sender import get_stk_service
    from pathlib import Path

    comic = db.query(Comic).filter(Comic.id == comic_id).first()
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


# ============================================================================
# BACKGROUND TASKS
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
    import hashlib

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

        # Get download links from scraper
        logger.info(f"Fetching download links for volume from {source}: {volume_url}")
        scrape_result = await scraper.get_download_links(volume_url)

        if scrape_result.success and scrape_result.download_links:
            issues = db.query(ComicIssue).filter(
                ComicIssue.comic_id == comic_id
            ).order_by(ComicIssue.issue_number).all()

            # Filter to only resolved/real host links (not shorteners)
            resolved_links = [
                dl for dl in scrape_result.download_links
                if 'ouo.io' not in dl.url and 'ouo.press' not in dl.url
                and 'uii.io' not in dl.url
            ]
            # Sort by quality (best first)
            resolved_links.sort(key=lambda x: x.quality_score, reverse=True)

            if len(resolved_links) >= max(2, len(issues) * 0.5):
                # Multiple resolved links available: assign individually per issue
                # Threshold: at least 50% of issues have links (handles grouped issues like #1-#2)
                logger.info(f"Assigning {len(resolved_links)} individual links to {len(issues)} issues")
                for idx, issue in enumerate(issues):
                    if idx < len(resolved_links):
                        issue.download_url = resolved_links[idx].url
                        issue.source = source
                        logger.info(f"  Issue #{issue.issue_number}: {resolved_links[idx].host.value} link assigned")

                db.commit()
                logger.info(f"✅ Assigned individual links to {len(issues)} issues from {source}")

            elif len(resolved_links) >= 1:
                # Some resolved links but fewer than issues: bundle with best link
                bundle_id = hashlib.md5(volume_url.encode()).hexdigest()[:16]
                bundle_title = scrape_result.title
                bundle_range = f"#1-{issue_count}"

                for idx, issue in enumerate(issues):
                    issue.bundle_id = bundle_id
                    issue.bundle_title = bundle_title
                    issue.bundle_range = bundle_range
                    issue.is_bundle_master = (idx == 0)
                    issue.download_url = resolved_links[0].url
                    issue.source = f"{source} (bundle)"

                    if issue.is_bundle_master and len(resolved_links) > 1:
                        issue.backup_url = resolved_links[1].url

                db.commit()
                logger.info(f"✅ Volume bundle created: {bundle_title} with {len(issues)} issues")

            else:
                # No resolved links, use best available (including shorteners)
                best = scrape_result.best_link
                if best:
                    bundle_id = hashlib.md5(volume_url.encode()).hexdigest()[:16]
                    bundle_title = scrape_result.title
                    bundle_range = f"#1-{issue_count}"

                    for idx, issue in enumerate(issues):
                        issue.bundle_id = bundle_id
                        issue.bundle_title = bundle_title
                        issue.bundle_range = bundle_range
                        issue.is_bundle_master = (idx == 0)
                        issue.download_url = best.url
                        issue.source = f"{source} (bundle)"

                    db.commit()
                    logger.info(f"✅ Volume bundle (shortener) created: {bundle_title} with {len(issues)} issues")
        else:
            logger.warning(f"No download links found for volume: {volume_url}")

    except Exception as e:
        logger.error(f"Error fetching volume from scraper: {e}")
        import traceback
        traceback.print_exc()
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


def _save_comic_metadata(comic: Comic, issue: ComicIssue, file_path):
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


async def _download_comic_issue(issue_id: int):
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
            _save_comic_metadata(comic, issue, result)

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
    downloader: "ComicDownloader",
    download_dir: str,
    db: "Session"
):
    """
    Download a MediaFire folder bundle: list files, match to issues, download each.
    Uses lock files (.downloading) like manga to prevent KCC from processing prematurely.
    Each file downloads directly with its final name - no staging/renaming needed.
    """
    import re
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
        patterns = [
            r'[Tt]omo\s*(\d+)',
            r'[Vv]ol(?:ume|umen)?\s*\.?\s*(\d+)',
            r'#\s*(\d+)',
            r'[Ii]ssue\s*(\d+)',
            r'[-_\s](\d{2,3})[\[\(\s._-]',
        ]
        for pattern in patterns:
            match = re.search(pattern, filename)
            if match:
                return int(match.group(1))
        return 0

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
        # Detect extension from original filename
        orig_ext = Path(ff["name"]).suffix.lower() or ".cbr"
        final_filename = f"{safe_title} - Issue {issue_num}{orig_ext}"

        logger.info(f"Downloading issue #{issue_num}: {ff['name'][:60]} -> {final_filename}")

        try:
            # download_file_with_name: gets direct link + downloads with lock file
            # Lock file (.downloading) prevents KCC from touching it until done
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
                _save_comic_metadata(comic, bi, result_path)

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

    Args:
        page_url: URL of the page to scrape (e.g., cbrcomicsweb.space)

    Returns:
        MEGA folder URL or None
    """
    import re
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
            # Links are stored as base64(urlencode(url)) in data-link attr
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
    downloader: "ComicDownloader",
    download_dir: str,
    db: "Session"
):
    """
    Download a MEGA shared folder bundle: list files via Playwright, match to issues,
    download each with megatools CLI + lock files.
    Similar to _download_mediafire_folder_bundle but for MEGA folders.
    """
    import re
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
        # Priority 1: Issue number patterns (most specific)
        issue_patterns = [
            r'#\s*0*(\d+)',           # "#01", "#1", "# 01"
            r'[Ii]ssue\s*0*(\d+)',    # "Issue 01"
            r'[Tt]omo\s*0*(\d+)',     # "Tomo 01"
        ]
        for pattern in issue_patterns:
            match = re.search(pattern, filename)
            if match:
                return int(match.group(1))

        # Priority 2: Trailing number before extension
        trailing = re.search(r'[-_\s.]0*(\d{1,3})\.[a-zA-Z]{2,4}$', filename)
        if trailing:
            return int(trailing.group(1))

        # Priority 3: Volume number as last resort
        vol_match = re.search(r'[Vv]ol(?:ume|umen)?\s*\.?\s*(\d+)', filename)
        if vol_match:
            return int(vol_match.group(1))

        return 0

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
                _save_comic_metadata(comic, bi, result_path)

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


def _translate_comic_title(spanish_title: str) -> str:
    """
    Translate common Spanish comic terms to English for ComicVine search
    """
    # Dictionary of common Star Wars and comic terms
    translations = {
        # Star Wars specific
        'caballeros de la antigua república': 'knights of the old republic',
        'la antigua república': 'the old republic',
        'caballeros': 'knights',
        'imperio': 'empire',
        'república': 'republic',
        'antigua': 'old',
        'guerras clon': 'clone wars',
        'el ascenso': 'the rise',
        'amanecer': 'dawn',
        'darth': 'darth',  # Keep as-is

        # Common comic terms
        'volumen': 'volume',
        'tomo': 'volume',
        'tomos': 'volumes',
        'completo': 'complete',
        'colección': 'collection',

        # Generic words to remove
        '[9 tomos]': '',
        '[x tomos]': '',
        '[completo]': '',
        'español': '',
    }

    title_lower = spanish_title.lower()

    # Remove bracketed info like [9 Tomos]
    import re
    title_lower = re.sub(r'\[.*?\]', '', title_lower)

    # Apply translations
    for spanish, english in translations.items():
        if spanish in title_lower:
            title_lower = title_lower.replace(spanish, english)

    # Clean up extra spaces
    title_lower = ' '.join(title_lower.split())

    logger.debug(f"Translation: '{spanish_title}' → '{title_lower}'")
    return title_lower.title()  # Capitalize first letter of each word


async def _verify_link_active(url: str) -> bool:
    """Check if a download link is still active (not 404)"""
    import aiohttp

    logger.info(f"🔍 DEBUG: _verify_link_active() called for: {url[:60]}...")
    try:
        async with aiohttp.ClientSession() as session:
            logger.debug(f"🔍 DEBUG: Sending HEAD request to verify link...")
            async with session.head(url, timeout=aiohttp.ClientTimeout(total=10), allow_redirects=True) as response:
                logger.info(f"🔍 DEBUG: HEAD response status: {response.status}")
                # Accept 2xx and 3xx status codes
                if response.status < 400:
                    logger.info(f"🔍 DEBUG: Link verified OK (status {response.status})")
                    return True
                # Some hosts return 403 but file is still downloadable
                if response.status == 403:
                    logger.info(f"🔍 DEBUG: Got 403, trying GET request...")
                    # Try GET request for these
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10), allow_redirects=True) as get_resp:
                        logger.info(f"🔍 DEBUG: GET response status: {get_resp.status}")
                        result = get_resp.status < 400
                        logger.info(f"🔍 DEBUG: Verification result after GET: {result}")
                        return result
                logger.warning(f"🔍 DEBUG: Link check failed with status {response.status}: {url[:50]}...")
                return False
    except Exception as e:
        logger.warning(f"🔍 DEBUG: Link verification error: {e}")
        logger.info(f"🔍 DEBUG: Returning True (assume it might work)")
        # If we can't verify, assume it might work
        return True


def _normalize_title(title: str) -> str:
    """Normalize title for comparison"""
    import re
    # Remove common suffixes and clean
    title = title.lower().strip()
    title = re.sub(r'\s*\(.*?\)\s*', ' ', title)  # Remove parentheses
    title = re.sub(r'\s*\[.*?\]\s*', ' ', title)  # Remove brackets
    title = re.sub(r'[^\w\s]', '', title)  # Remove punctuation
    title = re.sub(r'\s+', ' ', title).strip()  # Normalize spaces
    return title


def _title_matches(search_title: str, result_title: str) -> bool:
    """Check if result title is a good match for search title"""
    import re

    search_norm = _normalize_title(search_title)
    result_norm = _normalize_title(result_title)

    # Exact match
    if search_norm == result_norm:
        return True

    # Result starts with search title (most reliable)
    if result_norm.startswith(search_norm + " ") or result_norm.startswith(search_norm + "-"):
        return True

    # For short titles (like "300"), be more strict
    # The title must appear as a standalone word or at the start
    if len(search_norm) <= 5:
        # Check if the title starts with our search term (best match)
        if result_norm.startswith(search_norm + " "):
            return True

        # Check for issue ranges like "#1-300", "#1 – 300", "Vol. 2 #1 – 300"
        # These should NOT match a search for "300"
        issue_range_pattern = r'#\s*\d+\s*[-–]\s*' + re.escape(search_norm)
        if re.search(issue_range_pattern, result_norm):
            logger.debug(f"Skipping issue range match: {result_norm}")
            return False

        # Check if it's just an issue number like "spawn #300" or "spawn 300"
        issue_number_pattern = r'\w+\s+#?\s*' + re.escape(search_norm) + r'\s*(\(|$|\s)'
        if re.search(issue_number_pattern, result_norm):
            logger.debug(f"Skipping issue number match: {result_norm}")
            return False

        # Use word boundary matching for exact word match
        pattern = r'(^|\s)' + re.escape(search_norm) + r'(\s|$|[:\-])'
        if re.search(pattern, result_norm):
            return True

        return False

    # Search title is contained in result (for longer titles)
    if search_norm in result_norm:
        return True

    # Check word overlap (all search words must be in result)
    search_words = set(search_norm.split())
    result_words = set(result_norm.split())
    if search_words and len(search_words) >= 2 and search_words.issubset(result_words):
        return True

    return False


def _extract_volume_info(title: str) -> Optional[dict]:
    """
    Extract volume information from a comic title

    Args:
        title: Title like "The Invaders Volumen 3 [12/12] Español"

    Returns:
        {
            "volume_number": 3,
            "base_title": "The Invaders",
            "has_volume": True
        } or None if no volume detected
    """
    import re

    # Patterns for volume detection
    # "Vol 3", "Vol. 3", "Volumen 3", "Volume 3", "V3"
    volume_patterns = [
        r'vol(?:umen|ume)?\.?\s*(\d+)',  # volumen 3, volume 3, vol 3, vol. 3
        r'\bv\.?\s*(\d+)\b',  # v3, v.3, v 3
    ]

    for pattern in volume_patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            vol_num = int(match.group(1))
            # Extract base title (remove volume part and extra info)
            base_title = re.sub(pattern, '', title, flags=re.IGNORECASE)
            # Remove [X/X] pattern, español, etc.
            base_title = re.sub(r'\[.*?\]', '', base_title)
            base_title = re.sub(r'español', '', base_title, flags=re.IGNORECASE)
            base_title = base_title.strip()

            return {
                "volume_number": vol_num,
                "base_title": base_title,
                "has_volume": True
            }

    return None


def _detect_bundle(title: str, description: str = "", count_of_issues: int = 0) -> Optional[dict]:
    """
    Detect if a comic result is a bundle/collection that covers multiple issues

    Args:
        title: Title of the result (e.g., "Paper Girls Vol. 6 (TPB)")
        description: Description text that might contain issue info
        count_of_issues: Total issues in the series (from ComicVine)

    Returns:
        {
            "type": "complete|tpb|hc|range",
            "range": "#1-30",
            "issues": [1, 2, 3, ..., 30]
        } or None if not a bundle
    """
    import re
    import hashlib

    title_lower = title.lower()
    desc_lower = description.lower() if description else ""
    combined = f"{title_lower} {desc_lower}"

    # Pattern 1: Explicit issue range "#X-Y" or "#X-#Y" or "[X/X]" or "[X/X??]"
    range_patterns = [
        r'#(\d+)-#?(\d+)',  # #1-30 or #1-#30
        r'issues?\s*#?(\d+)\s*-\s*#?(\d+)',  # "issues 1-30" or "issue #1-#30"
        r'#(\d+)\s*–\s*#?(\d+)',  # Using en-dash
        r'\[(\d+)/(\d+)\?*\]',  # [12/12], [8/8?], [8/8??] - all issues from 1 to X
        r'\[(\d+)\s+de\s+(\d+)\]',  # [5 de 5] - Spanish format (5 out of 5)
        r'\[(\d+)\s+tomos?\]',  # [9 Tomos] - Spanish format (9 volumes)
        r'\[(\d+)\s+n[uú]meros?\]',  # [80 números] or [80 numeros] - Spanish issue count
        r'\[(\d+)\s+vol[uú]menes?\]',  # [15 volúmenes] or [15 volumenes] - Spanish volumes
    ]

    for pattern in range_patterns:
        match = re.search(pattern, combined)
        if match:
            # Special case for single-count patterns [X Tomos], [X números], [X volúmenes]
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

            # Special case for [X de X] and [X/X] formats - means issues 1 through X
            if ('de' in pattern or '/' in pattern) and start == end:
                logger.info(f"Bundle detected via [X de X] or [X/X] pattern: #1-{end}")
                return {
                    "type": "range",
                    "range": f"#1-{end}",
                    "issues": list(range(1, end + 1))
                }

            # Normal range check
            if start < end and (end - start) <= 1000:  # Sanity check
                logger.info(f"Bundle detected via range pattern: #{start}-{end}")
                return {
                    "type": "range",
                    "range": f"#{start}-{end}",
                    "issues": list(range(start, end + 1))
                }

    # Pattern 2: "Complete" collections
    if any(word in combined for word in ["complete", "complete collection", "full series", "complete story"]):
        # Try to extract total from context
        total_match = re.search(r'(\d+)\s*issues?', combined)
        if total_match:
            total = int(total_match.group(1))
            logger.info(f"Bundle detected via 'complete' + {total} issues")
            return {
                "type": "complete",
                "range": f"#1-{total}",
                "issues": list(range(1, total + 1))
            }
        # If no explicit count, use count_of_issues from ComicVine
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
    # These typically contain 5-10 issues
    # We need to infer the range based on volume number
    vol_match = re.search(r'vol(?:ume)?\.?\s*(\d+)', title_lower)
    book_match = re.search(r'book\s+(\w+)', title_lower)

    if (vol_match or book_match) and any(word in combined for word in ["tpb", "tp", "trade paperback", "hardcover", "hc"]):
        # Try to extract from description
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

        # If no explicit range, we can't determine exact issues
        # Return None and let it be searched individually
        logger.debug(f"TPB/HC detected but no explicit range found: {title}")

    return None


async def _search_scrapers_directly(query: str) -> List[dict]:
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
            results = await asyncio.wait_for(task, timeout=10.0)

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
                    bundle_info = _detect_bundle(full_title, "", 0)

                    vol_info = _extract_volume_info(full_title)
                    if vol_info:
                        # Has volume number
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
                        # Collection without volume number
                        found_volumes.append({
                            "number": 0,
                            "title": title,
                            "source": scraper_name,
                            "issues": len(bundle_info["issues"]),
                            "cover": result.get("cover"),
                            "url": url
                        })
                    else:
                        # No volume or bundle detected - still include it
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


async def _quick_check_availability(title: str, publisher: str = "", count_of_issues: int = 0) -> dict:
    """
    Quick check if scrapers have sources for this comic (WITHOUT full scraping)
    Returns: {
        "has_sources": bool,
        "sources": ["cbrcomics", "zonacomics", ...],
        "score": int,
        "volumes": [{"number": 1, "title": "...", "source": "cbrcomics", "issues": 41}, ...]
    }
    """
    from app.services.comic_scrapers import ZonaComicsScraper, MegaComicsScraper, CBRComicsScraper

    scrapers = [
        CBRComicsScraper(),
        ZonaComicsScraper(),
        MegaComicsScraper(),
    ]

    available_sources = []
    detected_volumes = []  # Store volume information

    # Extract franchise/main keywords for fallback search
    # E.g., "Star Wars: Clone Wars" -> "Star Wars"
    franchise_keywords = []
    title_parts = title.split(':')
    if len(title_parts) > 1:
        # Take the part before the colon as franchise
        franchise = title_parts[0].strip()
        franchise_keywords.append(franchise)

    # Also try first 2 significant words
    words = [w.strip() for w in title.split() if w.lower() not in ['the', 'a', 'an']]
    if len(words) >= 2:
        franchise_keywords.append(f"{words[0]} {words[1]}")

    # Try quick searches in parallel with timeout
    search_tasks = []
    for scraper in scrapers:
        # Try main title first
        task = asyncio.create_task(scraper.search(title, page=1))
        search_tasks.append((scraper.name, task, title))

        # Also try franchise keywords as fallback
        for keyword in franchise_keywords[:1]:  # Try first franchise keyword
            if keyword and keyword != title:
                fallback_task = asyncio.create_task(scraper.search(keyword, page=1))
                search_tasks.append((scraper.name, fallback_task, keyword))

    # Wait for all with timeout (10 seconds per scraper for Playwright-based scrapers)
    for scraper_name, task, search_query in search_tasks:
        try:
            results = await asyncio.wait_for(task, timeout=10.0)
            if results and len(results) > 0:
                # Check if any result is a reasonable match
                title_lower = title.lower()

                # Extract main keywords for flexible matching
                # Remove common words and keep significant terms
                title_keywords = set()
                for word in title_lower.split():
                    # Skip common filler words
                    if word not in ['the', 'a', 'an', 'of', 'and', 'or', 'vol', 'vol.', 'volume']:
                        # Remove punctuation
                        clean_word = word.strip('":,.-!?')
                        if len(clean_word) > 2:  # Skip very short words
                            title_keywords.add(clean_word)

                for result in results[:10]:  # Check first 10 results for volume detection
                    result_title = result.get("title", "").lower()

                    # Method 1: Exact match (contains)
                    exact_match = title_lower in result_title or result_title in title_lower

                    # Method 2: Keyword matching (for franchises like Star Wars)
                    # Extract keywords from result title
                    result_keywords = set()
                    for word in result_title.split():
                        if word not in ['the', 'a', 'an', 'of', 'and', 'or', 'vol', 'vol.', 'volume']:
                            clean_word = word.strip('":,.-!?[]')
                            if len(clean_word) > 2:
                                result_keywords.add(clean_word)

                    # Check if main keywords match
                    common_keywords = title_keywords & result_keywords

                    # For titles with subtitles (after ":"), prefer subtitle match but fallback to franchise
                    keyword_match = False
                    if ':' in title_lower:
                        # Search title has a subtitle - extract UNIQUE subtitle keywords
                        # (keywords that appear ONLY in subtitle, not in franchise part)
                        title_franchise = title_lower.split(':', 1)[0].strip()
                        title_subtitle = title_lower.split(':', 1)[1].strip()

                        # Extract franchise keywords
                        franchise_keywords_set = set()
                        for word in title_franchise.split():
                            if word not in ['the', 'a', 'an', 'of', 'and', 'or']:
                                clean_word = word.strip('":,.-!?[]')
                                if len(clean_word) > 2:
                                    franchise_keywords_set.add(clean_word)

                        # Extract subtitle keywords (excluding franchise keywords)
                        title_subtitle_keywords = set()
                        for word in title_subtitle.split():
                            if word not in ['the', 'a', 'an', 'of', 'and', 'or', 'vol', 'vol.', 'volume', 'de', 'la', 'el', 'los', 'las']:
                                clean_word = word.strip('":,.-!?[]')
                                if len(clean_word) > 2 and clean_word not in franchise_keywords_set:
                                    title_subtitle_keywords.add(clean_word)

                        if len(title_subtitle_keywords) > 0:
                            # Check if subtitle keywords appear in result title
                            common_subtitle = title_subtitle_keywords & result_keywords
                            if len(common_subtitle) >= 1:
                                # Subtitle match - best case
                                keyword_match = True
                            else:
                                # No subtitle match - fallback to franchise-only match
                                # This handles cross-language matches (English title → Spanish results)
                                # Accept if franchise matches (e.g., "Star Wars" in both)
                                franchise_match = len(franchise_keywords_set & result_keywords) >= len(franchise_keywords_set)
                                keyword_match = franchise_match
                        else:
                            # No unique subtitle keywords - use franchise matching
                            keyword_match = len(common_keywords) >= 2
                    else:
                        # No subtitle - use original logic (at least 2 keywords or 50% overlap)
                        keyword_match = len(common_keywords) >= min(2, len(title_keywords) * 0.5)

                    if exact_match or keyword_match:
                        if scraper_name not in available_sources:
                            available_sources.append(scraper_name)

                        # Extract volume information - use full_title (with brackets) for better detection
                        detect_title = result.get("full_title", result.get("title", ""))
                        vol_info = _extract_volume_info(detect_title)
                        bundle_info = _detect_bundle(detect_title, result.get("description", ""), count_of_issues)

                        if vol_info:
                            # Has volume number - add as volume
                            issue_count = len(bundle_info["issues"]) if bundle_info else 0

                            # Check if this volume is already detected
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
                            # No volume number but has bundle (e.g., "[9 Tomos]", "Completo")
                            # Add as "Volume 0" to show it as a collection
                            issue_count = len(bundle_info["issues"])
                            existing = next((v for v in detected_volumes if v["url"] == result.get("url")), None)
                            if not existing:
                                detected_volumes.append({
                                    "number": 0,  # 0 means single collection (no volume number)
                                    "title": result.get("title", ""),
                                    "source": scraper_name,
                                    "issues": issue_count,
                                    "cover": result.get("cover"),
                                    "url": result.get("url")
                                })
                        else:
                            # No volume or bundle detected - still include as generic result
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
    score = 100  # Start at 100

    # Penalize non-English editions
    if any(keyword in title.lower() for keyword in ["french", "spanish", "italian", "german", "translation"]):
        score -= 30
    if any(keyword in publisher.lower() for keyword in ["urban comics", "planeta", "panini"]):
        score -= 20

    # Bonus for original publisher
    if publisher.lower() in ["image", "dc comics", "marvel", "dark horse", "idw"]:
        score += 20

    # Bonus for having many issues (likely original series)
    if count_of_issues >= 20:
        score += 15
    elif count_of_issues >= 10:
        score += 10

    # Bonus for trade paperbacks/collections (if few issues)
    if count_of_issues <= 10:
        if any(keyword in title.lower() for keyword in ["tpb", "hardcover", "deluxe", "complete"]):
            score += 5

    # Big bonus if sources available
    if available_sources:
        score += 30

    # Sort volumes by number
    detected_volumes.sort(key=lambda v: v["number"])

    return {
        "has_sources": len(available_sources) > 0,
        "sources": available_sources,
        "score": max(0, score),  # Ensure non-negative
        "volumes": detected_volumes
    }


async def _search_scrapers_for_comic(comic_id: int, title: str):
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
        # Simplify publisher name for search
        publisher_short = publisher.split()[0] if publisher else ""  # "Dark Horse Comics" -> "Dark"

        # Get main writer if available
        writers = comic.writers or []
        main_writer = writers[0] if writers else ""
        # Get last name of writer for search
        writer_name = main_writer.split()[-1] if main_writer else ""  # "Frank Miller" -> "Miller"

        # Strategy 1: For short/medium series (<=50 issues), search for complete/TPB first
        if total_issues <= 50:
            collection_queries = []

            # For very short titles, add various searches
            if len(title) <= 5:
                # Try with writer name if available
                if main_writer:
                    collection_queries.extend([
                        f"{title} {main_writer}",  # "300 Frank Miller"
                        f"{title} {writer_name}",  # "300 Miller"
                    ])
                if publisher_short:
                    collection_queries.extend([
                        f"{title} {publisher_short}",  # "300 Dark"
                    ])

            collection_queries.extend([
                f"{title} TPB",
                f"{title} HC",
                f"{title} complete collection",
                f'"{title}"',  # Quoted exact search
                f"{title}",  # Just the title (last resort)
            ])

            for query in collection_queries:
                logger.info(f"Trying collection search: '{query}'")

                # Try all scrapers
                for scraper in scrapers:
                    logger.info(f"Trying {scraper.name} scraper...")
                    results = await scraper.search(query)

                    for result in results:
                        result_title = result.get("title", "")
                        # Check if title actually matches
                        if not _title_matches(title, result_title):
                            logger.debug(f"Skipping non-matching result: {result_title}")
                            continue

                        logger.info(f"Found potential match on {scraper.name}: {result_title}")

                        # Get download links
                        scrape_result = await scraper.get_download_links(result["url"])
                        if scrape_result.success and scrape_result.best_link:
                            # Verify link is active
                            link_url = scrape_result.best_link.url
                            if await _verify_link_active(link_url):
                                # BUNDLE DETECTION: Check if this is a bundle/collection
                                bundle_info = _detect_bundle(
                                    result_title,
                                    result.get("description", ""),
                                    total_issues
                                )

                                if bundle_info:
                                    # This is a BUNDLE - assign to ALL covered issues
                                    import hashlib
                                    bundle_id = hashlib.md5(result["url"].encode()).hexdigest()[:16]
                                    issues_covered = bundle_info["issues"]
                                    assigned_count = 0
                                    first_assigned = True  # Track first issue actually assigned

                                    for issue_num in issues_covered:
                                        issue = next((i for i in issues if i.issue_number == str(issue_num)), None)
                                        if issue and not issue.download_url:  # Only if not already assigned
                                            issue.bundle_id = bundle_id
                                            issue.bundle_title = result_title
                                            issue.bundle_range = bundle_info["range"]
                                            issue.is_bundle_master = first_assigned  # First actually assigned is master
                                            issue.download_url = link_url
                                            issue.source = f"{scraper.name} (bundle)"

                                            if scrape_result.backup_link and issue.is_bundle_master:
                                                backup_url = scrape_result.backup_link.url
                                                if await _verify_link_active(backup_url):
                                                    issue.backup_url = backup_url

                                            assigned_count += 1
                                            first_assigned = False  # Only first one is master

                                    logger.info(f"✅ BUNDLE: '{result_title}' covers {assigned_count} issues ({bundle_info['range']})")
                                    db.commit()

                                    # If bundle covers ALL issues, we're done
                                    if assigned_count == len(issues):
                                        logger.info(f"Bundle covers all issues, search complete!")
                                        if not comic.source_urls:
                                            comic.source_urls = {}
                                        comic.source_urls[scraper.name] = result["url"]
                                        comic.last_check = datetime.utcnow()
                                        db.commit()
                                        return
                                    else:
                                        # Bundle only covers some issues, continue searching for the rest
                                        logger.info(f"Bundle covers {assigned_count}/{len(issues)} issues, continuing search...")
                                        # Refresh issues list (exclude already assigned)
                                        issues = db.query(ComicIssue).filter(
                                            ComicIssue.comic_id == comic_id,
                                            ComicIssue.download_url == None
                                        ).all()
                                        if not issues:
                                            logger.info("All issues now have URLs!")
                                            return
                                        # Continue to next query/scraper
                                        continue

                                else:
                                    # NOT a bundle - assign to first issue only (legacy behavior)
                                    first_issue = issues[0]
                                    first_issue.download_url = link_url
                                    first_issue.source = f"{scraper.name} (collection)"

                                    if scrape_result.backup_link:
                                        backup_url = scrape_result.backup_link.url
                                        if await _verify_link_active(backup_url):
                                            first_issue.backup_url = backup_url

                                    logger.info(f"Found verified collection link for '{title}': {result_title}")
                                    db.commit()

                                    # Update source_urls and return early
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
        # Try ALL scrapers for each issue (not just GetComics)
        logger.info(f"Searching individual issues for '{title}' using all {len(scrapers)} scrapers")
        for issue in issues:
            try:
                issue_num = issue.issue_number or "1"
                found_link = False

                # Try ALL scrapers for this issue
                for scraper in scrapers:
                    if found_link:
                        break  # Already found a link, skip remaining scrapers

                    logger.info(f"Trying {scraper.name} for issue #{issue_num}")

                    # Try multiple search patterns
                    search_patterns = [
                        f"{title} #{issue_num}",
                        f"{title} {issue_num}",
                    ]

                    for pattern in search_patterns:
                        if found_link:
                            break

                        # Skip if scraper doesn't have search_for_issue method
                        if not hasattr(scraper, 'search_for_issue'):
                            logger.debug(f"{scraper.name} doesn't support issue-specific search, skipping")
                            break

                        logger.info(f"Searching: '{pattern}'")
                        result = await scraper.search_for_issue(title, f"#{issue_num}")

                        if result and result.get("url"):
                            result_title = result.get("title", "")

                            # Verify title matches
                            if not _title_matches(title, result_title):
                                logger.warning(f"Skipping non-matching result for '{pattern}': {result_title}")
                                continue

                            # Get download links from the page
                            scrape_result = await scraper.get_download_links(result["url"])

                            if scrape_result.success and scrape_result.best_link:
                                link_url = scrape_result.best_link.url
                                logger.info(f"🔍 DEBUG: Found best_link URL for issue {issue.id} (#{issue_num}): {link_url[:80]}...")

                                # Check if it's a URL shortener (skip verification for shorteners)
                                is_shortener = any(domain in link_url.lower() for domain in ['ouo.io', 'ouo.press', 'uii.io', 'wordcount.im'])

                                if is_shortener:
                                    # Don't verify shorteners - they need to be resolved first
                                    logger.info(f"🔗 URL shortener detected, skipping verification: {link_url[:60]}...")
                                    is_active = True
                                else:
                                    # Verify link is active
                                    is_active = await _verify_link_active(link_url)
                                    logger.info(f"🔍 DEBUG: Link verification result: {is_active} for {link_url[:60]}...")

                                if is_active:
                                    logger.info(f"🔍 DEBUG: Assigning URL to issue {issue.id} (#{issue_num})")
                                    issue.download_url = link_url
                                    issue.source = scraper.name
                                    logger.info(f"🔍 DEBUG: Assigned! issue.download_url = {issue.download_url[:60] if issue.download_url else 'None'}")

                                    if scrape_result.backup_link:
                                        backup_url = scrape_result.backup_link.url
                                        if await _verify_link_active(backup_url):
                                            issue.backup_url = backup_url
                                            logger.info(f"🔍 DEBUG: Backup URL also assigned")

                                    logger.info(f"✅ Found verified link for {title} #{issue_num} on {scraper.name}")
                                    found_link = True
                                    break  # Found working link, move to next scraper/issue
                                else:
                                    logger.warning(f"Link inactive for {title} #{issue_num} on {scraper.name}")

                    # Small delay between scrapers
                    await asyncio.sleep(1)

                # Rate limiting between issues
                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"Error searching for {title} #{issue.issue_number}: {e}")
                continue

        # POST-PROCESSING: Detect bundles from duplicate download URLs
        # When multiple issues share the same URL, they are a bundle
        all_issues = db.query(ComicIssue).filter(
            ComicIssue.comic_id == comic_id,
            ComicIssue.download_url != None,
            ComicIssue.bundle_id == None  # Only process issues not already in a bundle
        ).order_by(ComicIssue.issue_number).all()

        # Group by download_url
        url_groups = {}
        for issue in all_issues:
            if issue.download_url not in url_groups:
                url_groups[issue.download_url] = []
            url_groups[issue.download_url].append(issue)

        # Create bundles for groups with 2+ issues sharing the same URL
        for url, group_issues in url_groups.items():
            if len(group_issues) >= 2:
                import hashlib
                bundle_id = hashlib.md5(url.encode()).hexdigest()[:16]
                issue_nums = [i.issue_number for i in group_issues]
                bundle_range = f"#{issue_nums[0]}-{issue_nums[-1]}"
                bundle_title = f"{title} ({bundle_range})"

                logger.info(f"📦 Bundle detected: {len(group_issues)} issues share URL {url[:60]}...")
                for idx, issue in enumerate(group_issues):
                    issue.bundle_id = bundle_id
                    issue.bundle_title = bundle_title
                    issue.bundle_range = bundle_range
                    issue.is_bundle_master = (idx == 0)  # First issue is master
                    issue.source = f"{issue.source} (bundle)" if issue.source and "(bundle)" not in issue.source else issue.source

                logger.info(f"📦 Created bundle: {bundle_title} - master: issue #{group_issues[0].issue_number}")

        # Update source_urls on comic
        if not comic.source_urls:
            comic.source_urls = {}
        comic.source_urls["getcomics"] = f"https://getcomics.org/?s={quote(title)}"
        comic.last_check = datetime.utcnow()

        issues_with_urls = sum(1 for i in all_issues if i.download_url is not None)
        logger.info(f"{issues_with_urls}/{len(all_issues)} issues have download URLs")

        db.commit()
        logger.info(f"Finished searching sources for comic {comic_id}")

    except Exception as e:
        logger.error(f"Error searching scrapers for comic {comic_id}: {e}")
    finally:
        db.close()
