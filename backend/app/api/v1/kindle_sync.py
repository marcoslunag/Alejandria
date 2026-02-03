"""
Kindle Sync API Endpoints
Provides direct download access for Kindle browser and sync functionality
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Optional
import logging
import os

from app.database import get_db
from app.models.chapter import Chapter
from app.models.manga import Manga

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kindle-sync", tags=["kindle-sync"])

KINDLE_DIR = Path("/manga/kindle")


@router.get("/", response_class=HTMLResponse)
async def kindle_home(request: Request, db: Session = Depends(get_db)):
    """
    Simple HTML page optimized for Kindle browser
    Lists all available EPUBs for download
    """
    # Get all converted chapters
    chapters = db.query(Chapter).join(Manga).filter(
        Chapter.converted_path.isnot(None)
    ).order_by(Manga.title, Chapter.number).all()

    # Group by manga
    manga_dict = {}
    for chapter in chapters:
        manga_title = chapter.manga.title
        if manga_title not in manga_dict:
            manga_dict[manga_title] = []

        # Check if file exists and get size
        file_path = Path(chapter.converted_path)
        if file_path.exists():
            size_mb = file_path.stat().st_size / (1024 * 1024)
            manga_dict[manga_title].append({
                'id': chapter.id,
                'number': int(chapter.number) if chapter.number == int(chapter.number) else chapter.number,
                'title': chapter.title,
                'size_mb': size_mb,
                'filename': file_path.name,
                'sent': chapter.sent_at is not None
            })

    # Generate simple HTML for Kindle browser
    base_url = str(request.base_url).rstrip('/')

    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Alejandria - Kindle</title>
    <style>
        body {
            font-family: serif;
            font-size: 18px;
            line-height: 1.6;
            max-width: 100%;
            margin: 0;
            padding: 10px;
            background: #fff;
            color: #000;
        }
        h1 {
            font-size: 24px;
            border-bottom: 2px solid #000;
            padding-bottom: 5px;
            margin-bottom: 15px;
        }
        h2 {
            font-size: 20px;
            margin-top: 20px;
            margin-bottom: 10px;
            background: #eee;
            padding: 5px;
        }
        .chapter {
            padding: 8px 0;
            border-bottom: 1px solid #ccc;
        }
        .chapter a {
            color: #000;
            text-decoration: underline;
            font-weight: bold;
        }
        .size {
            color: #666;
            font-size: 14px;
        }
        .sent {
            color: #060;
            font-size: 14px;
        }
        .refresh {
            display: block;
            margin: 20px 0;
            padding: 10px;
            background: #333;
            color: #fff;
            text-align: center;
            text-decoration: none;
        }
        .empty {
            padding: 20px;
            text-align: center;
            color: #666;
        }
    </style>
</head>
<body>
    <h1>Alejandria</h1>
    <p>Tu biblioteca de manga</p>
"""

    if not manga_dict:
        html += '<p class="empty">No hay mangas disponibles para descargar.</p>'
    else:
        for manga_title, chapters in sorted(manga_dict.items()):
            html += f'<h2>{manga_title}</h2>\n'
            for ch in sorted(chapters, key=lambda x: x['number']):
                sent_mark = ' <span class="sent">[Enviado]</span>' if ch['sent'] else ''
                html += f'''<div class="chapter">
    <a href="{base_url}/api/v1/kindle-sync/download/{ch['id']}"">Tomo {ch['number']}</a>
    <span class="size">({ch['size_mb']:.0f} MB)</span>{sent_mark}
</div>
'''

    html += f'''
    <a href="{base_url}/api/v1/kindle-sync/" class="refresh">Actualizar lista</a>
    <p style="font-size: 12px; color: #999; text-align: center;">
        Toca en un tomo para descargarlo directamente al Kindle.
    </p>
</body>
</html>'''

    return HTMLResponse(content=html)


@router.get("/download/{chapter_id}")
async def download_epub(chapter_id: int, db: Session = Depends(get_db)):
    """
    Download EPUB file directly
    """
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()

    if not chapter:
        raise HTTPException(status_code=404, detail="Tomo not found")

    if not chapter.converted_path:
        raise HTTPException(status_code=400, detail="EPUB not available")

    file_path = Path(chapter.converted_path)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on server")

    # Get manga title for filename
    manga = db.query(Manga).filter(Manga.id == chapter.manga_id).first()
    chapter_num = int(chapter.number) if chapter.number == int(chapter.number) else chapter.number

    # Create a clean filename
    clean_title = manga.title if manga else "Manga"
    filename = f"{clean_title} - Tomo {chapter_num}.epub"

    logger.info(f"Kindle download: {filename}")

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/epub+zip"
    )


@router.get("/list")
async def list_available(db: Session = Depends(get_db)):
    """
    JSON list of available EPUBs
    """
    chapters = db.query(Chapter).join(Manga).filter(
        Chapter.converted_path.isnot(None)
    ).order_by(Manga.title, Chapter.number).all()

    result = []
    for chapter in chapters:
        file_path = Path(chapter.converted_path)
        if file_path.exists():
            result.append({
                'id': chapter.id,
                'manga_id': chapter.manga_id,
                'manga_title': chapter.manga.title,
                'number': chapter.number,
                'title': chapter.title,
                'size_mb': round(file_path.stat().st_size / (1024 * 1024), 2),
                'filename': file_path.name,
                'sent_at': chapter.sent_at.isoformat() if chapter.sent_at else None,
                'download_url': f"/api/v1/kindle-sync/download/{chapter.id}"
            })

    return {
        'count': len(result),
        'items': result
    }


@router.post("/mark-downloaded/{chapter_id}")
async def mark_as_downloaded(chapter_id: int, db: Session = Depends(get_db)):
    """
    Mark chapter as downloaded/sent (for tracking)
    """
    from datetime import datetime

    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()

    if not chapter:
        raise HTTPException(status_code=404, detail="Tomo not found")

    chapter.sent_at = datetime.utcnow()
    chapter.status = 'sent'
    db.commit()

    return {'ok': True, 'message': 'Marked as downloaded'}
