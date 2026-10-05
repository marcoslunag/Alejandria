"""
Cover proxy con caché local + ETag (roadmap #12)

Sirve las portadas externas (AniList/ComicVine/Google Books) a través del
backend en vez de hotlink directo:
- Evita bloqueos de hotlink de los CDN y fallos de CORS/mixed-content
- Caché en disco con TTL (7 días) → un solo fetch por portada
- ETag (md5 del contenido) + Cache-Control para el navegador
- 304 Not Modified cuando el cliente ya tiene la copia

Seguridad:
- Requiere autenticación: header Authorization (axios) o ?token=JWT (<img src>)
- Allowlist de hosts → NO es un proxy abierto (evita SSRF)
"""
import hashlib
import logging
import mimetypes
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.security import decode_token
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/covers", tags=["covers"])

# Solo CDN conocidos de portadas (el endpoint no debe servir de proxy abierto)
ALLOWED_HOSTS = {
    # AniList
    "media.anilist.co",
    # ComicVine
    "www.comicvine.com",
    # Google Books
    "books.google.com",
    "books.google.es",
    "books.google.co.uk",
    "lh3.googleusercontent.com",
    # Amazon (covers de Google Books a veces)
    "m.media-amazon.com",
}

CACHE_TTL_SECONDS = 7 * 24 * 3600      # 7 días
BROWSER_MAX_AGE = 7 * 24 * 3600        # el navegador también cachea 7 días
FETCH_TIMEOUT = 10                     # segundos
MAX_IMAGE_BYTES = 10 * 1024 * 1024     # 10 MB por portada
IMAGE_PREFIX = "image/"


def _cache_dir() -> Path:
    """Directorio de caché (monkeypatcheable en tests)."""
    d = Path(settings.LIBRARY_DIR) / "covers_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _host_allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if host in ALLOWED_HOSTS:
        return True
    return any(host.endswith("." + h) for h in ALLOWED_HOSTS)


def _ext_from_url(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"):
        return suffix
    return ".jpg"


def _etag_for(data: bytes) -> str:
    return '"' + hashlib.md5(data).hexdigest() + '"'


def _serve_cached(data: bytes, ext: str, request: Request) -> Response:
    """Devuelve la respuesta (200 o 304) para unos bytes de imagen."""
    etag = _etag_for(data)
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match.strip('"') == etag.strip('"'):
        return Response(status_code=304, headers={"ETag": etag})
    content_type = mimetypes.guess_type("img" + ext)[0] or "image/jpeg"
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "ETag": etag,
            "Cache-Control": f"public, max-age={BROWSER_MAX_AGE}",
        },
    )


def _user_from_token(token: str, db: Session) -> User:
    """Resuelve el usuario a partir de un JWT (misma lógica que get_current_user)."""
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Token invalido o expirado")
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token invalido")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuario no encontrado o inactivo")
    return user


def get_user_by_header_or_token(
    request: Request,
    token: Optional[str] = Query(None, description="JWT token (para <img src>)"),
    db: Session = Depends(get_db),
) -> User:
    """Auth por header Authorization (axios) o por query param token (<img src>).

    <img src> no puede enviar cabeceras, así que el frontend añade ?token=JWT
    (mismo patrón que el web reader de manga).
    """
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[len("Bearer "):]
    if not token:
        raise HTTPException(status_code=401, detail="Token requerido")
    return _user_from_token(token, db)


@router.get("/proxy")
def proxy_cover(
    request: Request,
    url: str = Query(..., description="URL externa de la portada (http/https)"),
    current_user: User = Depends(get_user_by_header_or_token),
):
    """Proxy de portadas con caché local + ETag/Cache-Control.

    Flujo:
    1. Valida http(s) + host en allowlist
    2. Si hay copia en caché con TTL vigente → sirve (200/304) sin fetch
    3. Si no → fetch (timeout 10s, máx 10 MB, solo image/*), guarda y sirve
    """
    if not url.startswith(("http://", "https://")) or not _host_allowed(url):
        raise HTTPException(status_code=400, detail="URL de portada no permitida")

    cache = _cache_dir()
    key = hashlib.md5(url.encode()).hexdigest()
    ext = _ext_from_url(url)
    cache_file = cache / f"{key}{ext}"

    # 1) Caché vigente
    now = time.time()
    if cache_file.exists():
        age = now - cache_file.stat().st_mtime
        if age < CACHE_TTL_SECONDS:
            try:
                return _serve_cached(cache_file.read_bytes(), ext, request)
            except OSError:
                pass  # archivo corrupto → re-fetch

    # 2) Fetch externo
    try:
        resp = requests.get(url, timeout=FETCH_TIMEOUT, stream=True)
    except requests.RequestException as e:
        logger.warning(f"Covers proxy: fallo fetch {url}: {e}")
        raise HTTPException(status_code=502, detail="No se pudo descargar la portada")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"CDN devolvió HTTP {resp.status_code}")

    content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if not content_type.startswith(IMAGE_PREFIX):
        # El CDN devolvió una página de error HTML u otro contenido
        raise HTTPException(status_code=502, detail="El CDN no devolvió una imagen")

    data = resp.content
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=502, detail="La portada excede el tamaño máximo")
    if len(data) == 0:
        raise HTTPException(status_code=502, detail="El CDN devolvió una imagen vacía")

    # 3) Guardar en caché (extensión según el Content-Type real si difiere)
    real_ext = mimetypes.guess_extension(content_type) or ext
    if real_ext == ".jpe" or real_ext == ".jfif":
        real_ext = ".jpg"
    cache_file = cache / f"{key}{real_ext}"
    try:
        cache_file.write_bytes(data)
    except OSError as e:
        logger.warning(f"Covers proxy: no se pudo cachear {url}: {e}")

    return _serve_cached(data, real_ext, request)
