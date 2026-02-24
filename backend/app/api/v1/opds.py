"""
OPDS 1.x Catalog Server
Open Publication Distribution System — estándar para catálogos de libros sobre HTTP.

Compatible con: KOReader, PocketBook (firmware nativo), Moon+ Reader, Librera, Calibre.
Autenticación: HTTP Basic Auth (usuario/contraseña de Alejandría).

Endpoints:
  GET /opds                          → Catálogo raíz (navigation feed)
  GET /opds/manga                    → Feed de manga disponible (acquisition feed)
  GET /opds/comics                   → Feed de cómics disponible
  GET /opds/books                    → Feed de libros disponible
  GET /opds/search?q=...             → Búsqueda en toda la biblioteca
  GET /opds/covers/{type}/{id}       → Cover art
  GET /opds/download/{type}/{id}/{file_id}/{fmt}  → Descarga EPUB o CBZ
  GET /opds/opensearch.xml           → Descripción de búsqueda
"""

import base64
import hashlib
import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.database import get_db
from app.models.book import Book
from app.models.book_chapter import BookChapter
from app.models.chapter import Chapter
from app.models.comic import Comic, ComicIssue
from app.models.manga import Manga
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/opds", tags=["opds"])
security = HTTPBasic(auto_error=False)

OPDS_MIME = "application/atom+xml;profile=opds-catalog"
OPDS_NAV_MIME = "application/atom+xml;profile=opds-catalog;kind=navigation"
OPDS_ACQ_MIME = "application/atom+xml;profile=opds-catalog;kind=acquisition"
EPUB_MIME = "application/epub+zip"
CBZ_MIME = "application/x-cbz"
PAGE_SIZE = 25


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

def get_opds_user(
    credentials: Optional[HTTPBasicCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """HTTP Basic Auth para clientes OPDS."""
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Autenticación requerida",
            headers={"WWW-Authenticate": "Basic realm=\"Alejandría OPDS\""},
        )
    user = db.query(User).filter(
        User.username == credentials.username,
        User.is_active == True,
    ).first()
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Basic realm=\"Alejandría OPDS\""},
        )
    return user


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atom_feed(id_: str, title: str, updated: str, links: str, entries: str, kind: str = "navigation") -> str:
    mime = OPDS_ACQ_MIME if kind == "acquisition" else OPDS_NAV_MIME
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom"\n'
        '      xmlns:opds="http://opds-spec.org/2010/catalog"\n'
        '      xmlns:dcterms="http://purl.org/dc/terms/">\n'
        f'  <id>{_escape(id_)}</id>\n'
        f'  <title>{_escape(title)}</title>\n'
        f'  <updated>{updated}</updated>\n'
        f'  <link rel="self" href="/api/v1/opds" type="{mime}"/>\n'
        f'  <link rel="start" href="/api/v1/opds" type="{OPDS_NAV_MIME}"/>\n'
        f'  <link rel="search" href="/api/v1/opds/search" type="application/atom+xml"/>\n'
        f'{links}'
        f'{entries}'
        '</feed>\n'
    )


def _escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _nav_entry(id_: str, title: str, href: str, summary: str = "") -> str:
    return (
        f'  <entry>\n'
        f'    <id>{_escape(id_)}</id>\n'
        f'    <title>{_escape(title)}</title>\n'
        f'    <updated>{_now_iso()}</updated>\n'
        f'    <link rel="subsection" href="{href}" type="{OPDS_ACQ_MIME}"/>\n'
        f'    <summary>{_escape(summary)}</summary>\n'
        f'  </entry>\n'
    )


def _pagination_links(base_href: str, page: int, total: int) -> str:
    links = ""
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    if page > 1:
        links += f'  <link rel="previous" href="{base_href}?page={page - 1}" type="{OPDS_ACQ_MIME}"/>\n'
    if page < total_pages:
        links += f'  <link rel="next" href="{base_href}?page={page + 1}" type="{OPDS_ACQ_MIME}"/>\n'
    return links


def _acq_entry(
    id_: str,
    title: str,
    updated: str,
    author: str,
    summary: str,
    cover_url: str,
    acquisition_links: List[str],
) -> str:
    links_xml = "\n".join(f"    {ln}" for ln in acquisition_links)
    cover_xml = f'    <link rel="http://opds-spec.org/image" href="{cover_url}" type="image/jpeg"/>\n' if cover_url else ""
    return (
        f'  <entry>\n'
        f'    <id>{_escape(id_)}</id>\n'
        f'    <title>{_escape(title)}</title>\n'
        f'    <updated>{updated}</updated>\n'
        f'    <author><name>{_escape(author)}</name></author>\n'
        f'    <summary>{_escape(summary)}</summary>\n'
        f'{cover_xml}'
        f'{links_xml}\n'
        f'  </entry>\n'
    )


def _acq_link(href: str, mime: str, title: str = "") -> str:
    title_attr = f' title="{_escape(title)}"' if title else ""
    return f'<link rel="http://opds-spec.org/acquisition" href="{href}" type="{mime}"{title_attr}/>'


# ---------------------------------------------------------------------------
# Root catalog
# ---------------------------------------------------------------------------

@router.get("", response_class=Response)
@router.get("/", response_class=Response)
async def opds_root(user: User = Depends(get_opds_user), db: Session = Depends(get_db)):
    """Catálogo raíz OPDS con navegación por tipo de contenido."""
    manga_count = db.query(Manga).filter(Manga.user_id == user.id).count()
    comic_count = db.query(Comic).filter(Comic.user_id == user.id).count()
    book_count = db.query(Book).filter(Book.user_id == user.id).count()

    entries = (
        _nav_entry("urn:alejandria:manga", f"Manga ({manga_count})", "/api/v1/opds/manga", "Manga disponible en tu biblioteca")
        + _nav_entry("urn:alejandria:comics", f"Cómics ({comic_count})", "/api/v1/opds/comics", "Cómics disponibles en tu biblioteca")
        + _nav_entry("urn:alejandria:books", f"Libros ({book_count})", "/api/v1/opds/books", "Libros disponibles en tu biblioteca")
    )

    xml = _atom_feed(
        id_="urn:alejandria:catalog",
        title="Alejandría",
        updated=_now_iso(),
        links="",
        entries=entries,
        kind="navigation",
    )
    return Response(content=xml, media_type=OPDS_MIME)


# ---------------------------------------------------------------------------
# OpenSearch description
# ---------------------------------------------------------------------------

@router.get("/opensearch.xml", response_class=Response)
async def opds_opensearch():
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<OpenSearchDescription xmlns="http://a9.com/-/spec/opensearch/1.1/">\n'
        '  <ShortName>Alejandría</ShortName>\n'
        '  <Description>Buscar en la biblioteca de Alejandría</Description>\n'
        '  <Url type="application/atom+xml" template="/api/v1/opds/search?q={searchTerms}"/>\n'
        '</OpenSearchDescription>\n'
    )
    return Response(content=xml, media_type="application/opensearchdescription+xml")


# ---------------------------------------------------------------------------
# Manga feed
# ---------------------------------------------------------------------------

@router.get("/manga", response_class=Response)
async def opds_manga(
    page: int = Query(1, ge=1),
    user: User = Depends(get_opds_user),
    db: Session = Depends(get_db),
):
    mangas = db.query(Manga).filter(Manga.user_id == user.id).order_by(Manga.title).all()
    total = len(mangas)
    offset = (page - 1) * PAGE_SIZE
    page_items = mangas[offset: offset + PAGE_SIZE]

    entries = ""
    for m in page_items:
        links, avail, total = _manga_acquisition_links(m, db)
        summary = m.description or ""
        if total == 0:
            note = "(Sin capítulos)"
        elif avail == 0:
            note = f"(0/{total} cap. descargados — pendiente)"
        elif avail < total:
            note = f"({avail}/{total} cap. disponibles)"
        else:
            note = ""
        if note:
            summary = f"{note}  {summary}".strip()
        entries += _acq_entry(
            id_=f"urn:alejandria:manga:{m.id}",
            title=m.title,
            updated=_now_iso(),
            author=m.author or "",
            summary=summary,
            cover_url=f"/api/v1/opds/covers/manga/{m.id}" if m.cover_url else "",
            acquisition_links=links,
        )

    pagination = _pagination_links("/api/v1/opds/manga", page, total)
    xml = _atom_feed("urn:alejandria:manga", "Manga", _now_iso(), pagination, entries, kind="acquisition")
    return Response(content=xml, media_type=OPDS_MIME)


def _manga_acquisition_links(manga: Manga, db: Session) -> tuple:
    """Devuelve (links, capítulos_disponibles, total_capítulos)."""
    chapters = db.query(Chapter).filter(
        Chapter.manga_id == manga.id
    ).order_by(Chapter.number).all()

    total = len(chapters)
    avail = 0
    links = []
    for ch in chapters:
        label = f"Cap. {ch.number}"
        ch_links = []
        # EPUB (convertido por KCC)
        if ch.converted_path:
            epub_paths = [p.strip() for p in ch.converted_path.split("|") if p.strip()]
            for idx, ep in enumerate(epub_paths):
                part = f" Parte {idx+1}" if len(epub_paths) > 1 else ""
                ch_links.append(_acq_link(
                    href=f"/api/v1/opds/download/manga/{manga.id}/{ch.id}/epub/{idx}",
                    mime=EPUB_MIME,
                    title=f"{label}{part} (EPUB)",
                ))
        # CBZ original
        if ch.file_path and Path(ch.file_path).exists():
            ch_links.append(_acq_link(
                href=f"/api/v1/opds/download/manga/{manga.id}/{ch.id}/cbz",
                mime=CBZ_MIME,
                title=f"{label} (CBZ)",
            ))
        if ch_links:
            avail += 1
            links.extend(ch_links)
    return links, avail, total


# ---------------------------------------------------------------------------
# Comics feed
# ---------------------------------------------------------------------------

@router.get("/comics", response_class=Response)
async def opds_comics(
    page: int = Query(1, ge=1),
    user: User = Depends(get_opds_user),
    db: Session = Depends(get_db),
):
    comics = db.query(Comic).filter(Comic.user_id == user.id).order_by(Comic.title).all()
    total = len(comics)
    offset = (page - 1) * PAGE_SIZE
    page_items = comics[offset: offset + PAGE_SIZE]

    entries = ""
    for c in page_items:
        links, avail, total = _comic_acquisition_links(c, db)
        summary = c.description or ""
        if total == 0:
            note = "(Sin issues)"
        elif avail == 0:
            note = f"(0/{total} issues descargados — pendiente)"
        elif avail < total:
            note = f"({avail}/{total} issues disponibles)"
        else:
            note = ""
        if note:
            summary = f"{note}  {summary}".strip()
        entries += _acq_entry(
            id_=f"urn:alejandria:comics:{c.id}",
            title=c.title,
            updated=_now_iso(),
            author=c.author or "",
            summary=summary,
            cover_url=f"/api/v1/opds/covers/comics/{c.id}" if c.cover_url else "",
            acquisition_links=links,
        )

    pagination = _pagination_links("/api/v1/opds/comics", page, total)
    xml = _atom_feed("urn:alejandria:comics", "Cómics", _now_iso(), pagination, entries, kind="acquisition")
    return Response(content=xml, media_type=OPDS_MIME)


def _comic_acquisition_links(comic: Comic, db: Session) -> tuple:
    """Devuelve (links, issues_disponibles, total_issues)."""
    issues = db.query(ComicIssue).filter(
        ComicIssue.comic_id == comic.id
    ).order_by(ComicIssue.issue_number).all()

    total = len(issues)
    avail = 0
    links = []
    for issue in issues:
        label = f"#{issue.issue_number}"
        iss_links = []
        if issue.converted_path:
            epub_paths = [p.strip() for p in issue.converted_path.split("|") if p.strip()]
            for idx, ep in enumerate(epub_paths):
                part = f" Parte {idx+1}" if len(epub_paths) > 1 else ""
                iss_links.append(_acq_link(
                    href=f"/api/v1/opds/download/comics/{comic.id}/{issue.id}/epub/{idx}",
                    mime=EPUB_MIME,
                    title=f"{label}{part} (EPUB)",
                ))
        if issue.file_path and Path(issue.file_path).exists():
            iss_links.append(_acq_link(
                href=f"/api/v1/opds/download/comics/{comic.id}/{issue.id}/cbz",
                mime=CBZ_MIME,
                title=f"{label} (CBZ)",
            ))
        if iss_links:
            avail += 1
            links.extend(iss_links)
    return links, avail, total


# ---------------------------------------------------------------------------
# Books feed
# ---------------------------------------------------------------------------

@router.get("/books", response_class=Response)
async def opds_books(
    page: int = Query(1, ge=1),
    user: User = Depends(get_opds_user),
    db: Session = Depends(get_db),
):
    books = db.query(Book).filter(Book.user_id == user.id).order_by(Book.title).all()
    total = len(books)
    offset = (page - 1) * PAGE_SIZE
    page_items = books[offset: offset + PAGE_SIZE]

    entries = ""
    for b in page_items:
        links, avail, total = _book_acquisition_links(b, db)
        summary = b.description or ""
        if avail == 0:
            note = "(Pendiente de descarga)"
        else:
            note = ""
        if note:
            summary = f"{note}  {summary}".strip()
        entries += _acq_entry(
            id_=f"urn:alejandria:books:{b.id}",
            title=b.title,
            updated=_now_iso(),
            author=b.author or "",
            summary=summary,
            cover_url=f"/api/v1/opds/covers/books/{b.id}" if b.cover_url else "",
            acquisition_links=links,
        )

    pagination = _pagination_links("/api/v1/opds/books", page, total)
    xml = _atom_feed("urn:alejandria:books", "Libros", _now_iso(), pagination, entries, kind="acquisition")
    return Response(content=xml, media_type=OPDS_MIME)


def _book_acquisition_links(book: Book, db: Session) -> tuple:
    """Devuelve (links, archivos_disponibles, total_archivos)."""
    chapters = db.query(BookChapter).filter(
        BookChapter.book_id == book.id
    ).order_by(BookChapter.number).all()

    total = len(chapters)
    avail = 0
    links = []
    for ch in chapters:
        if ch.file_path and Path(ch.file_path).exists():
            ext = Path(ch.file_path).suffix.lower()
            mime = EPUB_MIME if ext == ".epub" else "application/pdf"
            links.append(_acq_link(
                href=f"/api/v1/opds/download/books/{book.id}/{ch.id}/epub",
                mime=mime,
                title=f"Libro ({ext[1:].upper()})",
            ))
            avail += 1
    return links, avail, total


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@router.get("/search", response_class=Response)
async def opds_search(
    q: str = Query(""),
    user: User = Depends(get_opds_user),
    db: Session = Depends(get_db),
):
    q = q.strip()
    entries = ""

    if q:
        # Manga
        mangas = db.query(Manga).filter(
            Manga.user_id == user.id,
            Manga.title.ilike(f"%{q}%"),
        ).limit(PAGE_SIZE).all()
        for m in mangas:
            links, avail, total = _manga_acquisition_links(m, db)
            note = f"({avail}/{total} cap.)" if avail < total else ""
            entries += _acq_entry(
                id_=f"urn:alejandria:manga:{m.id}",
                title=f"[Manga] {m.title}",
                updated=_now_iso(),
                author=m.author or "",
                summary=f"{note}  {m.description or ''}".strip() if note else (m.description or ""),
                cover_url=f"/api/v1/opds/covers/manga/{m.id}" if m.cover_url else "",
                acquisition_links=links,
            )

        # Comics
        comics = db.query(Comic).filter(
            Comic.user_id == user.id,
            Comic.title.ilike(f"%{q}%"),
        ).limit(PAGE_SIZE).all()
        for c in comics:
            links, avail, total = _comic_acquisition_links(c, db)
            note = f"({avail}/{total} issues)" if avail < total else ""
            entries += _acq_entry(
                id_=f"urn:alejandria:comics:{c.id}",
                title=f"[Cómic] {c.title}",
                updated=_now_iso(),
                author=c.author or "",
                summary=f"{note}  {c.description or ''}".strip() if note else (c.description or ""),
                cover_url=f"/api/v1/opds/covers/comics/{c.id}" if c.cover_url else "",
                acquisition_links=links,
            )

        # Books
        books = db.query(Book).filter(
            Book.user_id == user.id,
            Book.title.ilike(f"%{q}%"),
        ).limit(PAGE_SIZE).all()
        for b in books:
            links, avail, _ = _book_acquisition_links(b, db)
            note = "(Pendiente)" if avail == 0 else ""
            entries += _acq_entry(
                id_=f"urn:alejandria:books:{b.id}",
                title=f"[Libro] {b.title}",
                updated=_now_iso(),
                author=b.author or "",
                summary=f"{note}  {b.description or ''}".strip() if note else (b.description or ""),
                cover_url=f"/api/v1/opds/covers/books/{b.id}" if b.cover_url else "",
                acquisition_links=links,
            )

    xml = _atom_feed(
        id_="urn:alejandria:search",
        title=f"Búsqueda: {q}" if q else "Búsqueda",
        updated=_now_iso(),
        links="",
        entries=entries,
        kind="acquisition",
    )
    return Response(content=xml, media_type=OPDS_MIME)


# ---------------------------------------------------------------------------
# Cover proxy
# ---------------------------------------------------------------------------

@router.get("/covers/{content_type}/{item_id}", response_class=Response)
async def opds_cover(
    content_type: str,
    item_id: int,
    user: User = Depends(get_opds_user),
    db: Session = Depends(get_db),
):
    """Devuelve la imagen de portada del ítem."""
    cover_url = None
    if content_type == "manga":
        item = db.query(Manga).filter(Manga.id == item_id, Manga.user_id == user.id).first()
        if item:
            cover_url = item.cover_url
    elif content_type == "comics":
        item = db.query(Comic).filter(Comic.id == item_id, Comic.user_id == user.id).first()
        if item:
            cover_url = item.cover_url
    elif content_type == "books":
        item = db.query(Book).filter(Book.id == item_id, Book.user_id == user.id).first()
        if item:
            cover_url = item.cover_url

    if not cover_url:
        raise HTTPException(status_code=404, detail="Cover not found")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(cover_url)
            if resp.status_code == 200:
                content_type_header = resp.headers.get("content-type", "image/jpeg")
                return Response(content=resp.content, media_type=content_type_header)
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="Cover unavailable")


# ---------------------------------------------------------------------------
# File download
# ---------------------------------------------------------------------------

@router.get("/download/{content_type}/{item_id}/{file_id}/{fmt}", response_class=Response)
@router.get("/download/{content_type}/{item_id}/{file_id}/{fmt}/{part_idx}", response_class=Response)
async def opds_download(
    content_type: str,
    item_id: int,
    file_id: int,
    fmt: str,
    part_idx: int = 0,
    user: User = Depends(get_opds_user),
    db: Session = Depends(get_db),
):
    """Descarga un archivo (EPUB o CBZ) verificando ownership del usuario."""
    file_path: Optional[Path] = None
    filename = "file"

    if content_type == "manga":
        manga = db.query(Manga).filter(Manga.id == item_id, Manga.user_id == user.id).first()
        if not manga:
            raise HTTPException(404)
        ch = db.query(Chapter).filter(Chapter.id == file_id, Chapter.manga_id == item_id).first()
        if not ch:
            raise HTTPException(404)
        file_path, filename = _resolve_file(ch, fmt, part_idx, manga.title, f"Cap{ch.number}")

    elif content_type == "comics":
        comic = db.query(Comic).filter(Comic.id == item_id, Comic.user_id == user.id).first()
        if not comic:
            raise HTTPException(404)
        issue = db.query(ComicIssue).filter(ComicIssue.id == file_id, ComicIssue.comic_id == item_id).first()
        if not issue:
            raise HTTPException(404)
        file_path, filename = _resolve_file(issue, fmt, part_idx, comic.title, f"#{issue.issue_number}")

    elif content_type == "books":
        book = db.query(Book).filter(Book.id == item_id, Book.user_id == user.id).first()
        if not book:
            raise HTTPException(404)
        ch = db.query(BookChapter).filter(BookChapter.id == file_id, BookChapter.book_id == item_id).first()
        if not ch:
            raise HTTPException(404)
        if ch.file_path and Path(ch.file_path).exists():
            file_path = Path(ch.file_path)
            filename = f"{book.title}"
    else:
        raise HTTPException(400, "Tipo de contenido no válido")

    if not file_path or not file_path.exists():
        raise HTTPException(404, "Archivo no encontrado")

    ext = file_path.suffix.lower()
    if ext == ".epub":
        media_type = EPUB_MIME
    elif ext in (".cbz", ".cbr", ".zip"):
        media_type = CBZ_MIME
    elif ext == ".pdf":
        media_type = "application/pdf"
    else:
        media_type = "application/octet-stream"

    safe_name = "".join(c if c.isalnum() or c in " .-_()" else "_" for c in filename)
    disp = f'attachment; filename="{safe_name}{ext}"'

    def iterfile():
        with open(file_path, "rb") as f:
            while chunk := f.read(64 * 1024):
                yield chunk

    return StreamingResponse(
        iterfile(),
        media_type=media_type,
        headers={"Content-Disposition": disp, "Content-Length": str(file_path.stat().st_size)},
    )


def _resolve_file(item, fmt: str, part_idx: int, title: str, label: str):
    """Resuelve path y nombre de fichero para un ítem (Chapter, ComicIssue, BookChapter)."""
    if fmt == "epub" and hasattr(item, "converted_path") and item.converted_path:
        paths = [p.strip() for p in item.converted_path.split("|") if p.strip()]
        if 0 <= part_idx < len(paths):
            p = Path(paths[part_idx])
            if p.exists():
                return p, f"{title} {label}"
    if fmt == "cbz" and hasattr(item, "file_path") and item.file_path:
        p = Path(item.file_path)
        if p.exists():
            return p, f"{title} {label}"
    return None, ""
