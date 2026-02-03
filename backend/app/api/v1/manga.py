"""
Manga API Endpoints - Enhanced with Anilist Integration
Kaizoku-inspired approach to manga library management
"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from typing import List, Optional
from app.database import get_db
from app.models.manga import Manga
from app.models.chapter import Chapter
from app.schemas.manga import (
    MangaCreateFromAnilist,
    MangaCreateFromURL,
    MangaResponse,
    MangaDetailResponse,
    MangaCardResponse,
    MangaUpdate,
    MangaSearch,
    SearchResponse,
    AnilistSearchResponse,
    MangaStats,
    LibraryStats
)
from app.schemas.chapter import ChapterResponse
from app.services.anilist import AnilistService
from app.services.scraper import TomosMangaScraper
from app.services.mangaycomics_scraper import MangayComicsScraper
import logging
from slugify import slugify
from pydantic import BaseModel
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/manga", tags=["manga"])


# ============================================================================
# DISCOVERY & SEARCH - Kaizoku Style
# ============================================================================

@router.get("/discover/trending", response_model=List[dict])
async def get_trending_manga(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Get trending manga from Anilist
    """
    anilist = AnilistService()
    trending = await anilist.get_trending_manga(page=page, per_page=limit)

    # Check which ones are already in library
    result = []
    for item in trending:
        # Check if in library
        in_library = db.query(Manga).filter(Manga.anilist_id == item['anilist_id']).first()

        card = {
            "id": in_library.id if in_library else 0,
            "title": item['title'],
            "cover_image": item.get('cover_image'),
            "cover_color": item.get('cover_color'),
            "format": item.get('format'),
            "status": item.get('status'),
            "average_score": item.get('average_score'),
            "genres": item.get('genres', []),
            "monitored": in_library.monitored if in_library else False,
            "chapters_total": item.get('chapters'),
            "downloaded_chapters": 0,
            "anilist_id": item['anilist_id'],
            "in_library": bool(in_library)
        }
        result.append(card)

    return result


@router.get("/discover/popular", response_model=List[dict])
async def get_popular_manga(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Get popular manga from Anilist
    """
    anilist = AnilistService()
    popular = await anilist.get_popular_manga(page=page, per_page=limit)

    result = []
    for item in popular:
        in_library = db.query(Manga).filter(Manga.anilist_id == item['anilist_id']).first()

        card = {
            "id": in_library.id if in_library else 0,
            "title": item['title'],
            "cover_image": item.get('cover_image'),
            "cover_color": item.get('cover_color'),
            "format": item.get('format'),
            "status": item.get('status'),
            "average_score": item.get('average_score'),
            "genres": item.get('genres', []),
            "monitored": in_library.monitored if in_library else False,
            "chapters_total": item.get('chapters'),
            "downloaded_chapters": 0,
            "anilist_id": item['anilist_id'],
            "in_library": bool(in_library)
        }
        result.append(card)

    return result


@router.get("/search", response_model=SearchResponse)
async def search_manga(
    q: str = Query(..., min_length=2, description="Search query"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Search manga on AniList - the best manga/anime database
    """
    results = []

    try:
        anilist = AnilistService()
        anilist_results = await anilist.search_manga(q, page=page, per_page=limit)

        for item in anilist_results['results']:
            # Check if already in library
            in_library = db.query(Manga).filter(Manga.anilist_id == item['anilist_id']).first()

            results.append(MangaSearch(
                title=item['title'],
                description=item.get('description', '')[:200] + '...' if item.get('description') else None,
                cover=item.get('cover_image'),
                source='anilist',
                anilist_id=item['anilist_id'],
                anilist_url=item.get('anilist_url'),
                genres=item.get('genres', []),
                average_score=item.get('average_score'),
                status=item.get('status'),
                in_library=bool(in_library),
                library_id=in_library.id if in_library else None
            ))
    except Exception as e:
        logger.error(f"AniList search error: {e}")

    return SearchResponse(
        query=q,
        results=results,
        total=len(results),
        sources=['anilist']
    )


# ============================================================================
# LIBRARY MANAGEMENT
# ============================================================================

@router.get("/", response_model=List[MangaResponse])
def list_manga(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    monitored: Optional[bool] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List manga in library with filtering
    """
    query = db.query(Manga)

    if monitored is not None:
        query = query.filter(Manga.monitored == monitored)

    if status:
        query = query.filter(Manga.status == status)

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                Manga.title.ilike(search_pattern),
                Manga.title_english.ilike(search_pattern),
                Manga.title_romaji.ilike(search_pattern)
            )
        )

    manga_list = query.offset(skip).limit(limit).all()
    return manga_list


@router.post("/add/anilist", response_model=MangaResponse, status_code=201)
async def add_manga_from_anilist(
    data: MangaCreateFromAnilist,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Add manga to library from Anilist ID (Kaizoku-style)
    This is the preferred method!
    """
    # Check if already exists
    existing = db.query(Manga).filter(Manga.anilist_id == data.anilist_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Manga already in library")

    # Fetch metadata from Anilist
    anilist = AnilistService()
    metadata = await anilist.get_manga_by_id(data.anilist_id)

    if not metadata:
        raise HTTPException(status_code=404, detail="Manga not found on Anilist")

    # Create slug
    slug = slugify(metadata['title'])

    # Make slug unique
    base_slug = slug
    counter = 1
    while db.query(Manga).filter(Manga.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    # Create manga in database
    manga = Manga(
        title=metadata['title'],
        slug=slug,
        source_url=data.source_url,
        source_type='tomosmanga' if data.source_url else None,

        # Anilist metadata
        anilist_id=metadata['anilist_id'],
        mal_id=metadata.get('mal_id'),
        title_romaji=metadata.get('title_romaji'),
        title_english=metadata.get('title_english'),
        title_native=metadata.get('title_native'),

        # Visual
        description=metadata.get('description'),
        cover_image=metadata.get('cover_image'),
        banner_image=metadata.get('banner_image'),
        cover_color=metadata.get('cover_color'),

        # Info
        format=metadata.get('format'),
        status=metadata.get('status'),
        start_date=metadata.get('start_date'),
        end_date=metadata.get('end_date'),
        chapters_total=metadata.get('chapters'),
        volumes_total=metadata.get('volumes'),

        # Categories
        genres=metadata.get('genres', []),
        tags=metadata.get('tags', []),
        authors=metadata.get('authors', []),
        artists=metadata.get('artists', []),

        # Ratings
        average_score=metadata.get('average_score'),
        popularity=metadata.get('popularity'),

        # Links
        anilist_url=metadata.get('anilist_url'),
        country=metadata.get('country'),

        # Settings
        monitored=data.monitored,
        auto_download=data.auto_download
    )

    db.add(manga)
    db.commit()
    db.refresh(manga)

    logger.info(f"Added manga from Anilist: {manga.title} (ID: {manga.anilist_id})")

    # If source URL not provided, try auto-search
    if not manga.source_url:
        from app.services.tomosmanga_search import TomosMangaSearch, MangayComicsSearch

        tomos_search = TomosMangaSearch()
        result = tomos_search.find_best_match(manga.title)

        if result:
            manga.source_url = result['url']
            manga.source_type = 'tomosmanga'
            db.commit()
            db.refresh(manga)
            logger.info(f"Auto-found source: {manga.source_url}")
        else:
            mangay_search = MangayComicsSearch()
            results = mangay_search.search(manga.title)
            if results:
                manga.source_url = results[0]['url']
                manga.source_type = 'mangaycomics'
                db.commit()
                db.refresh(manga)
                logger.info(f"Auto-found source: {manga.source_url}")

    # If source URL available, fetch chapters in background
    if manga.source_url:
        background_tasks.add_task(_fetch_chapters_from_source, manga.id, manga.source_url)

    return manga


@router.post("/add/url", response_model=MangaResponse, status_code=201)
async def add_manga_from_url(
    data: MangaCreateFromURL,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Add manga from direct URL (legacy method)
    Optionally link to Anilist for metadata
    """
    # Check if already exists
    existing = db.query(Manga).filter(Manga.source_url == data.source_url).first()
    if existing:
        raise HTTPException(status_code=400, detail="Manga already in library")

    # Scrape basic info from source
    scraper = TomosMangaScraper()
    details = scraper.get_manga_details(data.source_url)

    if not details:
        raise HTTPException(status_code=400, detail="Could not fetch manga from URL")

    title = details['title']
    slug = slugify(title)

    # Make slug unique
    base_slug = slug
    counter = 1
    while db.query(Manga).filter(Manga.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    # Fetch Anilist metadata if ID provided
    metadata = None
    if data.anilist_id:
        anilist = AnilistService()
        metadata = await anilist.get_manga_by_id(data.anilist_id)

    # Create manga
    manga = Manga(
        title=metadata['title'] if metadata else title,
        slug=slug,
        source_url=data.source_url,
        source_type='tomosmanga',
        description=metadata.get('description') if metadata else details.get('description'),
        cover_image=metadata.get('cover_image') if metadata else details.get('cover'),
        monitored=data.monitored,
        auto_download=data.auto_download
    )

    # Add Anilist fields if available
    if metadata:
        manga.anilist_id = metadata['anilist_id']
        manga.mal_id = metadata.get('mal_id')
        manga.title_romaji = metadata.get('title_romaji')
        manga.title_english = metadata.get('title_english')
        manga.title_native = metadata.get('title_native')
        manga.banner_image = metadata.get('banner_image')
        manga.cover_color = metadata.get('cover_color')
        manga.format = metadata.get('format')
        manga.status = metadata.get('status')
        manga.start_date = metadata.get('start_date')
        manga.end_date = metadata.get('end_date')
        manga.chapters_total = metadata.get('chapters')
        manga.volumes_total = metadata.get('volumes')
        manga.genres = metadata.get('genres', [])
        manga.tags = metadata.get('tags', [])
        manga.authors = metadata.get('authors', [])
        manga.artists = metadata.get('artists', [])
        manga.average_score = metadata.get('average_score')
        manga.popularity = metadata.get('popularity')
        manga.anilist_url = metadata.get('anilist_url')
        manga.country = metadata.get('country')

    db.add(manga)
    db.commit()
    db.refresh(manga)

    # Add chapters
    if details.get('chapters'):
        for ch_data in details['chapters']:
            download_url = ""
            if ch_data.get('download_links'):
                download_url = _select_best_download_link(ch_data['download_links'])

            chapter = Chapter(
                manga_id=manga.id,
                number=ch_data['number'],
                title=ch_data.get('title', ''),
                url=ch_data.get('url', data.source_url),
                download_url=download_url,
                status='pending'
            )
            db.add(chapter)

        db.commit()
        logger.info(f"Added {len(details['chapters'])} chapters for {manga.title}")

    return manga


# ============================================================================
# LIBRARY STATS - Must be before dynamic routes
# ============================================================================

@router.get("/library/stats", response_model=LibraryStats)
def get_library_stats(db: Session = Depends(get_db)):
    """
    Get overall library statistics
    """
    total_manga = db.query(func.count(Manga.id)).scalar()
    monitored = db.query(func.count(Manga.id)).filter(Manga.monitored == True).scalar()
    total_chapters = db.query(func.count(Chapter.id)).scalar()
    downloaded = db.query(func.count(Chapter.id)).filter(
        Chapter.status.in_(['downloaded', 'converted', 'sent'])
    ).scalar()
    pending = db.query(func.count(Chapter.id)).filter(Chapter.status == 'pending').scalar()

    # Genre distribution
    manga_with_genres = db.query(Manga).filter(Manga.genres != None).all()
    genre_counts = {}
    for manga in manga_with_genres:
        if manga.genres:
            for genre in manga.genres:
                genre_counts[genre] = genre_counts.get(genre, 0) + 1

    # Status distribution
    status_counts = {}
    for manga in db.query(Manga).all():
        if manga.status:
            status_counts[manga.status] = status_counts.get(manga.status, 0) + 1

    return LibraryStats(
        total_manga=total_manga or 0,
        monitored_manga=monitored or 0,
        total_chapters=total_chapters or 0,
        downloaded_chapters=downloaded or 0,
        pending_downloads=pending or 0,
        disk_usage_mb=0.0,  # TODO: Calculate actual disk usage
        genres_distribution=genre_counts,
        status_distribution=status_counts
    )


# ============================================================================
# DYNAMIC ROUTES - Must be after specific routes
# ============================================================================

@router.get("/{manga_id}", response_model=MangaDetailResponse)
def get_manga(manga_id: int, db: Session = Depends(get_db)):
    """
    Get detailed manga information
    """
    manga = db.query(Manga).filter(Manga.id == manga_id).first()

    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    # Calculate stats
    total_in_library = db.query(Chapter).filter(Chapter.manga_id == manga_id).count()
    downloaded = db.query(Chapter).filter(
        and_(
            Chapter.manga_id == manga_id,
            Chapter.status.in_(['downloaded', 'converted', 'sent'])
        )
    ).count()
    pending = db.query(Chapter).filter(
        and_(
            Chapter.manga_id == manga_id,
            Chapter.status == 'pending'
        )
    ).count()

    # Build response manually
    response_data = manga.__dict__.copy()
    response_data['total_chapters_in_library'] = total_in_library
    response_data['downloaded_chapters'] = downloaded
    response_data['pending_chapters'] = pending

    return MangaDetailResponse(**response_data)


@router.put("/{manga_id}", response_model=MangaResponse)
async def update_manga(
    manga_id: int,
    data: MangaUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Update manga settings
    """
    manga = db.query(Manga).filter(Manga.id == manga_id).first()

    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    # Check if source_url is being updated
    source_url_updated = False
    if data.source_url and data.source_url != manga.source_url:
        source_url_updated = True
        new_source_url = data.source_url

    # Update fields
    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(manga, key, value)

    db.commit()
    db.refresh(manga)

    # If source URL was updated, fetch chapters in background
    if source_url_updated:
        background_tasks.add_task(_fetch_chapters_from_source, manga_id, new_source_url)
        logger.info(f"Source URL updated for {manga.title}, fetching chapters...")

    logger.info(f"Updated manga: {manga.title}")
    return manga


@router.get("/{manga_id}/search-source")
async def search_manga_source(manga_id: int, db: Session = Depends(get_db)):
    """
    Busca automáticamente la source_url para un manga sin source
    """
    from app.services.tomosmanga_search import TomosMangaSearch, MangayComicsSearch

    manga = db.query(Manga).filter(Manga.id == manga_id).first()

    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    tomos_search = TomosMangaSearch()
    mangay_search = MangayComicsSearch()

    # Buscar en ambas fuentes
    tomos_results = tomos_search.search(manga.title)
    mangay_results = mangay_search.search(manga.title)

    all_results = tomos_results + mangay_results

    if not all_results:
        raise HTTPException(status_code=404, detail="No se encontraron fuentes para este manga")

    return {
        "manga_id": manga_id,
        "manga_title": manga.title,
        "results": all_results
    }


@router.post("/{manga_id}/set-source")
async def set_manga_source(
    manga_id: int,
    source_url: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Establece la source_url de un manga y descarga los capítulos
    """
    manga = db.query(Manga).filter(Manga.id == manga_id).first()

    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    # Detectar tipo de source
    source_type = None
    if 'tomosmanga' in source_url.lower():
        source_type = 'tomosmanga'
    elif 'mangaycomics' in source_url.lower():
        source_type = 'mangaycomics'

    manga.source_url = source_url
    manga.source_type = source_type
    db.commit()
    db.refresh(manga)

    # Fetch chapters in background
    background_tasks.add_task(_fetch_chapters_from_source, manga_id, source_url)

    logger.info(f"Set source URL for {manga.title}: {source_url}")

    return {
        "status": "success",
        "manga_id": manga_id,
        "source_url": source_url,
        "source_type": source_type
    }


@router.delete("/{manga_id}", status_code=204)
def delete_manga(manga_id: int, db: Session = Depends(get_db)):
    """
    Delete manga and all its chapters
    """
    manga = db.query(Manga).filter(Manga.id == manga_id).first()

    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    title = manga.title
    db.delete(manga)
    db.commit()

    logger.info(f"Deleted manga: {title}")
    return None


@router.post("/{manga_id}/refresh", status_code=202)
async def refresh_manga(
    manga_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Force refresh of manga chapters
    """
    manga = db.query(Manga).filter(Manga.id == manga_id).first()

    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    background_tasks.add_task(_refresh_manga_task, manga_id)

    return {"status": "refresh_queued", "manga_id": manga_id}


@router.get("/{manga_id}/stats", response_model=MangaStats)
def get_manga_stats(manga_id: int, db: Session = Depends(get_db)):
    """
    Get detailed statistics for a manga
    """
    manga = db.query(Manga).filter(Manga.id == manga_id).first()

    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    total = db.query(Chapter).filter(Chapter.manga_id == manga_id).count()
    downloaded = db.query(Chapter).filter(
        Chapter.manga_id == manga_id,
        Chapter.status == 'downloaded'
    ).count()
    downloading = db.query(Chapter).filter(
        Chapter.manga_id == manga_id,
        Chapter.status == 'downloading'
    ).count()
    pending = db.query(Chapter).filter(
        Chapter.manga_id == manga_id,
        Chapter.status == 'pending'
    ).count()
    failed = db.query(Chapter).filter(
        Chapter.manga_id == manga_id,
        Chapter.status == 'error'
    ).count()
    sent = db.query(Chapter).filter(
        Chapter.manga_id == manga_id,
        Chapter.status == 'sent'
    ).count()

    last_download = db.query(func.max(Chapter.downloaded_at)).filter(
        Chapter.manga_id == manga_id
    ).scalar()

    return MangaStats(
        manga_id=manga_id,
        title=manga.title,
        total_chapters=total,
        downloaded=downloaded,
        downloading=downloading,
        pending=pending,
        failed=failed,
        sent_to_kindle=sent,
        last_download=last_download,
        last_check=manga.last_check
    )


@router.get("/{manga_id}/chapters", response_model=List[ChapterResponse])
def get_manga_chapters(
    manga_id: int,
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db)
):
    """
    Get all chapters for a manga
    """
    manga = db.query(Manga).filter(Manga.id == manga_id).first()

    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    query = db.query(Chapter).filter(Chapter.manga_id == manga_id)

    if status:
        query = query.filter(Chapter.status == status)

    chapters = query.order_by(Chapter.number.asc()).all()

    return chapters


class ChapterDownloadRequest(BaseModel):
    """Request schema for downloading specific chapters"""
    chapter_ids: List[int]


@router.post("/{manga_id}/chapters/download", status_code=202)
async def download_chapters(
    manga_id: int,
    request: ChapterDownloadRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Queue specific chapters for download.
    
    Automatically deduplicates chapters that share the same download_url
    (bundled volumes) to avoid downloading the same file multiple times.
    """
    manga = db.query(Manga).filter(Manga.id == manga_id).first()

    if not manga:
        raise HTTPException(status_code=404, detail="Manga not found")

    # Verify all chapter IDs belong to this manga
    chapters = db.query(Chapter).filter(
        and_(
            Chapter.id.in_(request.chapter_ids),
            Chapter.manga_id == manga_id
        )
    ).all()

    if len(chapters) != len(request.chapter_ids):
        raise HTTPException(
            status_code=400,
            detail="Some chapter IDs are invalid or don't belong to this manga"
        )

    # Deduplicar por download_url para evitar descargar el mismo archivo múltiples veces
    # Si varios capítulos comparten la misma URL (bundle), solo descargamos uno
    seen_urls = set()
    chapters_to_download = []
    all_chapter_ids = []  # Todos los IDs para marcar como downloading
    
    for chapter in chapters:
        if chapter.status in ['pending', 'error']:
            all_chapter_ids.append(chapter.id)
            
            # Solo añadir a la descarga si no hemos visto esta URL
            if chapter.download_url:
                if chapter.download_url not in seen_urls:
                    seen_urls.add(chapter.download_url)
                    chapters_to_download.append(chapter)
            else:
                # Sin URL, incluir siempre
                chapters_to_download.append(chapter)

    # Marcar TODOS los capítulos seleccionados como 'downloading'
    # (incluidos los del bundle que no se descargarán directamente)
    for chapter in chapters:
        if chapter.id in all_chapter_ids:
            chapter.status = 'downloading'
            chapter.retry_count = 0

    db.commit()

    # Trigger background download task solo para capítulos únicos por URL
    if chapters_to_download:
        background_tasks.add_task(
            _process_chapter_downloads, 
            manga_id, 
            [c.id for c in chapters_to_download]
        )

    return {
        "status": "queued",
        "manga_id": manga_id,
        "chapters_queued": len(all_chapter_ids),
        "unique_downloads": len(chapters_to_download),
        "total_requested": len(request.chapter_ids)
    }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _select_best_download_link(download_links: list) -> str:
    """
    Selecciona el mejor enlace de descarga basado en prioridad
    Prioridad: MEGA > Google Drive > MediaFire > Otros > TeraBox/OUO.io

    Args:
        download_links: Lista de dicts con 'url' y 'host'

    Returns:
        URL del mejor enlace disponible
    """
    if not download_links:
        return ""

    # Definir prioridades (menor número = mayor prioridad)
    priority_map = {
        'MEGA': 1,
        'Google Drive': 2,
        'MediaFire': 3,
        '1fichier': 4,
        'Uptobox': 5,
        'Uploaded': 6,
        'Dropbox': 7,
        'TeraBox': 98,
        'OUO.io': 99,
        'ShrinkMe': 99,
        'Unknown': 100
    }

    # Ordenar enlaces por prioridad
    sorted_links = sorted(
        download_links,
        key=lambda x: priority_map.get(x.get('host', 'Unknown'), 100)
    )

    # Retornar el mejor enlace
    return sorted_links[0]['url'] if sorted_links else ""


async def _fetch_chapters_from_source(manga_id: int, source_url: str):
    """Background task to fetch chapters from source"""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        # Detect which scraper to use based on URL
        parsed_url = urlparse(source_url)
        domain = parsed_url.netloc.lower()

        scraper = None
        if 'tomosmanga' in domain:
            scraper = TomosMangaScraper()
            logger.info(f"Using TomosManga scraper for {source_url}")
        elif 'mangaycomics' in domain:
            scraper = MangayComicsScraper()
            logger.info(f"Using MangayComics scraper for {source_url}")
        else:
            # Default to TomosManga scraper
            scraper = TomosMangaScraper()
            logger.warning(f"Unknown domain {domain}, using TomosManga scraper as fallback")

        details = scraper.get_manga_details(source_url)

        if not details or not details.get('chapters'):
            logger.warning(f"No chapters/volumes found for manga {manga_id} from {source_url}")
            return

        chapters_added = 0
        for ch_data in details['chapters']:
            # Obtener URLs priorizadas del scraper (ya vienen procesadas)
            download_url = ch_data.get('download_url') or (
                _select_best_download_link(ch_data.get('download_links', []))
            )
            backup_url = ch_data.get('backup_url')
            download_host = ch_data.get('download_host', 'unknown')

            # Check if chapter already exists
            existing = db.query(Chapter).filter(
                and_(
                    Chapter.manga_id == manga_id,
                    Chapter.number == ch_data['number']
                )
            ).first()

            if existing:
                # Update URLs si los nuevos son mejores
                updated = False
                if download_url:
                    # Actualizar si el nuevo URL es mejor o si no tenía
                    current_is_bad = existing.download_url and (
                        'terabox' in existing.download_url.lower() or
                        'ouo.io' in existing.download_url.lower()
                    )
                    new_is_good = download_url and not (
                        'terabox' in download_url.lower() or
                        'ouo.io' in download_url.lower()
                    )
                    if not existing.download_url or (current_is_bad and new_is_good):
                        existing.download_url = download_url
                        existing.download_host = download_host
                        updated = True

                # Siempre actualizar backup si no existe
                if backup_url and not existing.backup_url:
                    existing.backup_url = backup_url
                    updated = True

                if updated:
                    chapters_added += 1
                continue

            chapter = Chapter(
                manga_id=manga_id,
                number=ch_data['number'],
                title=ch_data.get('title', ''),
                url=ch_data.get('url', source_url),
                download_url=download_url,
                backup_url=backup_url,
                download_host=download_host,
                volume_range_start=ch_data.get('volume_range_start'),
                volume_range_end=ch_data.get('volume_range_end'),
                status='pending'
            )
            db.add(chapter)
            chapters_added += 1

        db.commit()
        logger.info(f"Fetched {chapters_added} chapters/volumes for manga {manga_id} from {domain}")

    except Exception as e:
        logger.error(f"Error fetching chapters from {source_url}: {e}")
        db.rollback()
    finally:
        db.close()


async def _refresh_manga_task(manga_id: int):
    """Background task to refresh manga chapters"""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        manga = db.query(Manga).filter(Manga.id == manga_id).first()
        if not manga or not manga.source_url:
            return

        await _fetch_chapters_from_source(manga_id, manga.source_url)

    finally:
        db.close()


async def _process_chapter_downloads(manga_id: int, chapter_ids: List[int]):
    """Background task to process chapter downloads"""
    from app.database import SessionLocal
    from app.services.downloader import MangaDownloader
    import json

    db = SessionLocal()
    try:
        downloader = MangaDownloader()

        for chapter_id in chapter_ids:
            chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()

            if not chapter or chapter.status not in ['pending', 'error']:
                continue

            try:
                # Update status to downloading
                chapter.status = 'downloading'
                db.commit()

                # Download the chapter
                if chapter.download_url:
                    # Check if it's an unsupported service
                    # Note: OUO.io is now supported via resolver
                    url_lower = chapter.download_url.lower()
                    if 'shrinkme' in url_lower:
                        chapter.status = 'error'
                        chapter.error_message = 'Manual download required - ShrinkMe not supported'
                        db.commit()
                        logger.warning(f"Chapter {chapter_id} requires manual download: {chapter.download_url}")
                        continue

                    # Get manga info for filename
                    manga = db.query(Manga).filter(Manga.id == chapter.manga_id).first()

                    # Generate filename: MangaTitle - Tomo XXX.cbz
                    filename = f"{manga.slug} - Tomo {int(chapter.number):03d}.cbz"

                    # Preparar URLs de backup si existen
                    backup_urls = [chapter.backup_url] if chapter.backup_url else None

                    file_path = await downloader.download_chapter(
                        url=chapter.download_url,
                        filename=filename,
                        backup_urls=backup_urls
                    )

                    if file_path:
                        chapter.file_path = str(file_path)
                        chapter.status = 'downloaded'
                        chapter.downloaded_at = datetime.utcnow()

                        # Guardar metadatos del manga para ComicInfo.xml
                        _save_manga_metadata(manga, chapter, file_path)

                        # Si este capítulo está en un bundle, marcar todos los capítulos relacionados
                        if chapter.is_bundled and chapter.download_url:
                            _mark_bundled_chapters_downloaded(
                                db, manga.id, chapter.download_url, str(file_path), chapter.id
                            )
                    else:
                        chapter.status = 'error'
                        chapter.error_message = 'Download failed'
                else:
                    chapter.status = 'error'
                    chapter.error_message = 'No download URL available'

                db.commit()
                logger.info(f"Downloaded chapter {chapter_id}")

            except Exception as e:
                logger.error(f"Error downloading chapter {chapter_id}: {e}")
                chapter.status = 'error'
                chapter.error_message = str(e)
                chapter.retry_count += 1
                db.commit()

    except Exception as e:
        logger.error(f"Error in download task: {e}")
    finally:
        db.close()


def _mark_bundled_chapters_downloaded(
    db: Session, manga_id: int, download_url: str, file_path: str, exclude_chapter_id: int
):
    """
    Marca todos los capítulos que comparten el mismo download_url como descargados.
    Esto sucede cuando un archivo contiene múltiples tomos (ej: Gantz Tomos 1-6).

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
                Chapter.status.in_(['pending', 'downloading'])
            )
        ).all()

        if related_chapters:
            logger.info(f"Marking {len(related_chapters)} bundled chapters as downloaded")

            for ch in related_chapters:
                ch.status = 'downloaded'
                ch.file_path = file_path  # Mismo archivo para todos
                ch.downloaded_at = datetime.utcnow()

            db.commit()
            logger.info(f"Bundled chapters marked: {[int(ch.number) for ch in related_chapters]}")

    except Exception as e:
        logger.error(f"Error marking bundled chapters: {e}")


def _save_manga_metadata(manga: Manga, chapter: Chapter, file_path: str):
    """
    Guarda metadatos del manga como JSON junto al archivo descargado
    El converter usara estos datos para generar ComicInfo.xml
    """
    import json
    from pathlib import Path

    try:
        cbz_path = Path(file_path)
        metadata_path = cbz_path.with_suffix('.metadata.json')

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
            # Info del capitulo/tomo
            'volume_number': int(chapter.number),
            'chapter_title': chapter.title,
        }

        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        logger.info(f"Metadata saved: {metadata_path}")

    except Exception as e:
        logger.warning(f"Could not save metadata for {file_path}: {e}")
