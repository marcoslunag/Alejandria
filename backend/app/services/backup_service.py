"""
Backup Service (roadmap #16)
Backup automático semanal de la base de datos:
- pg_dump (formato custom -Fc, restorable con pg_restore) — el backend instala postgresql-client
- JSON portable de toda la biblioteca (todos los usuarios)
- Retención: se conservan los N backups más recientes (BACKUP_RETENTION)

Los backups viven en BACKUP_DIR (volumen Docker `backups`).
El scheduler lanza `run_backup()` los domingos a las 4 AM; el endpoint
admin `POST /system/backup` lo dispara manualmente.
"""

import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from sqlalchemy import func

from app.config import get_settings

logger = logging.getLogger(__name__)

# Nombres de backup: <timestamp>.json / <timestamp>.dump — nada más se toca
_BACKUP_TS_RE = re.compile(r"^(\d{8}-\d{6})\.(json|dump)$")


def parse_database_url(url: str) -> Dict[str, str]:
    """
    Parsea DATABASE_URL → {host, port, user, password, dbname}.
    La contraseña puede estar URL-encoded (%2F etc.) → se decodifica.
    """
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "dbname": (parsed.path or "/").lstrip("/") or "postgres",
    }


def export_json_backup(backup_dir: Path, ts: str, db) -> Path:
    """
    Exporta TODA la biblioteca (todos los usuarios) a <ts>.json.
    Mismo esquema que el endpoint /export pero multi-usuario y con contadores.
    """
    from app.models.user import User
    from app.models.manga import Manga
    from app.models.comic import Comic
    from app.models.book import Book
    from app.models.chapter import Chapter
    from app.models.comic import ComicIssue
    from app.models.book_chapter import BookChapter

    chapter_counts = {
        mid: n for mid, n in db.query(Chapter.manga_id, func.count(Chapter.id)).group_by(Chapter.manga_id)
    }
    issue_counts = {
        cid: n for cid, n in db.query(ComicIssue.comic_id, func.count(ComicIssue.id)).group_by(ComicIssue.comic_id)
    }
    book_chapter_counts = {
        bid: n for bid, n in db.query(BookChapter.book_id, func.count(BookChapter.id)).group_by(BookChapter.book_id)
    }

    users = db.query(User).all()
    data = {
        "exported_at": datetime.utcnow().isoformat(),
        "version": "3.0",
        "type": "full-backup",
        "users": {},
    }

    for user in users:
        manga = db.query(Manga).filter(Manga.user_id == user.id).all()
        comics = db.query(Comic).filter(Comic.user_id == user.id).all()
        books = db.query(Book).filter(Book.user_id == user.id).all()
        data["users"][user.username] = {
            "manga": [
                {
                    "title": m.title,
                    "anilist_id": m.anilist_id,
                    "genres": m.genres,
                    "status": m.status,
                    "monitored": m.monitored,
                    "reading_status": m.reading_status,
                    "cover_image": m.cover_image,
                    "chapters": chapter_counts.get(m.id, 0),
                }
                for m in manga
            ],
            "comics": [
                {
                    "title": c.title,
                    "comicvine_id": c.comicvine_id,
                    "publisher": c.publisher,
                    "start_year": c.start_year,
                    "count_of_issues": c.count_of_issues,
                    "monitored": c.monitored,
                    "reading_status": c.reading_status,
                    "cover_image": c.cover_image,
                    "issues": issue_counts.get(c.id, 0),
                }
                for c in comics
            ],
            "books": [
                {
                    "title": b.title,
                    "google_books_id": b.google_books_id,
                    "authors": b.authors,
                    "isbn_13": b.isbn_13,
                    "language": b.language,
                    "monitored": b.monitored,
                    "reading_status": b.reading_status,
                    "cover_image": b.cover_image,
                    "chapters": book_chapter_counts.get(b.id, 0),
                }
                for b in books
            ],
        }

    path = backup_dir / f"{ts}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_pg_dump(backup_dir: Path, ts: str) -> Tuple[bool, str]:
    """
    Ejecuta pg_dump (custom format -Fc) usando las credenciales de DATABASE_URL.
    Devuelve (ok, error). Nunca lanza: un fallo de backup no puede romper el scheduler.
    """
    settings = get_settings()
    creds = parse_database_url(settings.DATABASE_URL)

    if shutil.which("pg_dump") is None:
        return False, "pg_dump no disponible (¿postgresql-client instalado?)"

    path = backup_dir / f"{ts}.dump"
    env = dict(os.environ)
    env["PGPASSWORD"] = creds["password"]
    cmd = [
        "pg_dump",
        "-h", creds["host"],
        "-p", creds["port"],
        "-U", creds["user"],
        "-d", creds["dbname"],
        "-Fc",  # custom format: compacto, parcial, restaurable con pg_restore
        "-f", str(path),
    ]
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=1800)
    except FileNotFoundError:
        return False, "pg_dump no disponible"
    except subprocess.TimeoutExpired:
        return False, "pg_dump timeout (>30min)"

    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "").strip()[:500]

    if not path.exists() or path.stat().st_size == 0:
        return False, "pg_dump devolvió 0 pero el archivo no existe o está vacío"
    return True, ""


def apply_retention(backup_dir: Path, retention: int) -> List[str]:
    """
    Conserva los `retention` timestamps más recientes y borra el resto
    (cada timestamp = par .json + .dump). Devuelve los timestamps borrados.
    """
    if retention < 0:
        return []

    timestamps: Dict[str, List[Path]] = {}
    for p in backup_dir.iterdir() if backup_dir.is_dir() else []:
        m = _BACKUP_TS_RE.match(p.name)
        if m:
            timestamps.setdefault(m.group(1), []).append(p)

    if len(timestamps) <= retention:
        return []

    # Los timestamps son YYYYMMDD-HHMMSS → orden lexicográfico = cronológico
    to_delete = sorted(timestamps.keys())[: len(timestamps) - retention]
    deleted = []
    for ts in to_delete:
        for p in timestamps[ts]:
            try:
                p.unlink()
                logger.info(f"Backup retention: borrado {p.name}")
            except OSError as e:
                logger.warning(f"Backup retention: no se pudo borrar {p.name}: {e}")
        deleted.append(ts)
    return deleted


def run_backup() -> Dict:
    """
    Orquesta un backup completo: JSON (siempre) + pg_dump (si es posible) + retención.
    Devuelve un resumen; NUNCA lanza (el scheduler lo ejecuta sin supervisión).
    """
    settings = get_settings()
    summary: Dict = {"ok": False}
    try:
        backup_dir = Path(settings.BACKUP_DIR)
        backup_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        summary["timestamp"] = ts

        # 1) JSON portable (toda la BD, todos los usuarios)
        try:
            from app.database import SessionLocal
            db = SessionLocal()
            try:
                json_path = export_json_backup(backup_dir, ts, db)
                summary["json"] = {"ok": True, "file": json_path.name, "bytes": json_path.stat().st_size}
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Backup JSON falló: {e}")
            summary["json"] = {"ok": False, "error": str(e)[:500]}

        # 2) pg_dump (la copia restaurable de verdad)
        dump_ok, dump_err = run_pg_dump(backup_dir, ts)
        summary["pg_dump"] = {"ok": dump_ok, **({"error": dump_err} if dump_err else {})}
        if dump_ok:
            summary["pg_dump"]["bytes"] = (backup_dir / f"{ts}.dump").stat().st_size

        # 3) Retención
        try:
            summary["deleted"] = apply_retention(backup_dir, settings.BACKUP_RETENTION)
        except Exception as e:
            logger.warning(f"Backup retention falló (no crítico): {e}")
            summary["deleted"] = []

        summary["ok"] = bool(summary.get("json", {}).get("ok")) or bool(summary.get("pg_dump", {}).get("ok"))
        logger.info(
            f"Backup completado: json={summary.get('json', {}).get('ok')} "
            f"pg_dump={summary.get('pg_dump', {}).get('ok')} borrados={summary.get('deleted')}"
        )
    except Exception as e:
        logger.error(f"Backup falló: {e}")
        summary["error"] = str(e)[:500]
    return summary


def list_backups() -> List[Dict]:
    """Lista los backups disponibles (por timestamp, más reciente primero)."""
    settings = get_settings()
    backup_dir = Path(settings.BACKUP_DIR)
    if not backup_dir.is_dir():
        return []

    entries: Dict[str, Dict] = {}
    for p in backup_dir.iterdir():
        m = _BACKUP_TS_RE.match(p.name)
        if not m:
            continue
        ts = m.group(1)
        entry = entries.setdefault(ts, {"timestamp": ts, "json": None, "pg_dump": None})
        key = "json" if m.group(2) == "json" else "pg_dump"
        entry[key] = {
            "file": p.name,
            "bytes": p.stat().st_size,
            "mb": round(p.stat().st_size / (1024 * 1024), 2),
            "modified": datetime.utcfromtimestamp(p.stat().st_mtime).isoformat(),
        }

    return sorted(entries.values(), key=lambda e: e["timestamp"], reverse=True)


def delete_backup(name: str) -> bool:
    """
    Borra un backup por su timestamp (sin sufijo o con él).
    Rechaza path traversal: solo nombres que coincidan con el patrón <ts>[.json|.dump].
    """
    settings = get_settings()
    backup_dir = Path(settings.BACKUP_DIR)

    # Sanitizar: solo el basename, y debe ser <ts> o <ts>.json|<ts>.dump
    base = os.path.basename(name)
    m = _BACKUP_TS_RE.match(base)
    ts = base[:-5] if base.endswith((".json", ".dump")) else base
    if not re.match(r"^\d{8}-\d{6}$", ts):
        return False

    deleted_any = False
    for suffix in (".json", ".dump"):
        p = backup_dir / f"{ts}{suffix}"
        if p.is_file():
            p.unlink()
            deleted_any = True

    if deleted_any:
        logger.info(f"Backup borrado manualmente: {ts}")
    return deleted_any
