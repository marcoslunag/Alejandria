"""
Comic API Endpoints
American comics library management with ComicVine integration
"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import List, Optional
from pydantic import BaseModel
from app.database import get_db
from app.models.comic import Comic, ComicIssue
from app.services.comicvine import get_comicvine_service
import logging
from slugify import slugify

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/comics", tags=["comics"])


# ============================================================================
# Pydantic Schemas
# ============================================================================

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

class ComicSearchResponse(BaseModel):
    results: List[ComicSearchResult]
    total: int
    page: int
    per_page: int

class ComicCreate(BaseModel):
    comicvine_id: int

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
    db: Session = Depends(get_db)
):
    """
    Search comics on ComicVine
    """
    comicvine = get_comicvine_service()
    search_result = await comicvine.search_volumes(q, page=page, per_page=limit)
    
    if search_result.get('error'):
        raise HTTPException(status_code=503, detail=search_result['error'])
    
    results = []
    for item in search_result.get('results', []):
        # Check if in library
        in_library = db.query(Comic).filter(Comic.comicvine_id == item['comicvine_id']).first()
        
        results.append(ComicSearchResult(
            comicvine_id=item['comicvine_id'],
            title=item['title'],
            description=item.get('description', '')[:300] + '...' if item.get('description') and len(item.get('description', '')) > 300 else item.get('description'),
            cover_image=item.get('cover_image'),
            publisher=item.get('publisher'),
            start_year=item.get('start_year'),
            count_of_issues=item.get('count_of_issues'),
            comicvine_url=item.get('comicvine_url'),
            in_library=bool(in_library),
            library_id=in_library.id if in_library else None
        ))
    
    return ComicSearchResponse(
        results=results,
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


@router.post("/", response_model=ComicResponse)
async def add_comic(
    data: ComicCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Add comic to library from ComicVine
    """
    # Check if already exists
    existing = db.query(Comic).filter(Comic.comicvine_id == data.comicvine_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Comic already in library")
    
    # Fetch details from ComicVine
    comicvine = get_comicvine_service()
    details = await comicvine.get_volume(data.comicvine_id)
    
    if not details:
        raise HTTPException(status_code=404, detail="Comic not found on ComicVine")
    
    # Create comic
    comic = Comic(
        title=details['title'],
        slug=slugify(details['title']),
        comicvine_id=details['comicvine_id'],
        title_original=details['title'],
        aliases=details.get('aliases'),
        description=details.get('description'),
        cover_image=details.get('cover_image'),
        publisher=details.get('publisher'),
        start_year=details.get('start_year'),
        count_of_issues=details.get('count_of_issues'),
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
    
    # Fetch issues in background
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
            'file_path': issue.file_path
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
        file_path=issue.file_path
    ) for issue in issues]


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
