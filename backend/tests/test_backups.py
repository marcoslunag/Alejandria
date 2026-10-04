"""
Tests de backups automáticos (roadmap #16):
- parse_database_url (credenciales para pg_dump)
- run_backup: JSON + pg_dump + retención (con run_pg_dump mockeado)
- apply_retention: conserva los N más recientes
- delete_backup: anti path-traversal
- Endpoints admin: POST /system/backup, GET /system/backups, DELETE /system/backups/{name}
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.services import backup_service


# ── parse_database_url ─────────────────────────────────────────────────────────

def test_parse_database_url_simple():
    creds = backup_service.parse_database_url(
        "postgresql://alejandria:alejandria@postgres:5432/alejandria"
    )
    assert creds == {
        "host": "postgres", "port": "5432",
        "user": "alejandria", "password": "alejandria", "dbname": "alejandria",
    }


def test_parse_database_url_encoded_password():
    creds = backup_service.parse_database_url(
        "postgresql://admin:pa%40ss%2Fword@db.internal:5433/mydb"
    )
    assert creds["password"] == "pa@ss/word"
    assert creds["host"] == "db.internal"
    assert creds["port"] == "5433"
    assert creds["dbname"] == "mydb"


def test_parse_database_url_defaults():
    creds = backup_service.parse_database_url("postgresql:///aledb")
    assert creds["host"] == "localhost"
    assert creds["port"] == "5432"
    assert creds["dbname"] == "aledb"


# ── Fixtures ───────────────────────────────────────────────────────────────────

class _FakeBackupSettings:
    def __init__(self, backup_dir, retention=4):
        self.BACKUP_DIR = str(backup_dir)
        self.BACKUP_RETENTION = retention
        self.DATABASE_URL = "postgresql://u:p@localhost:5432/aledb"


@pytest.fixture
def backup_env(db, tmp_path, monkeypatch):
    """BACKUP_DIR en tmp + pg_dump mockeado (sin binario ni red)."""
    settings = _FakeBackupSettings(backup_dir=tmp_path / "backups", retention=4)
    monkeypatch.setattr(backup_service, "get_settings", lambda: settings)

    def fake_pg_dump(backup_dir, ts):
        (backup_dir / f"{ts}.dump").write_bytes(b"fake-pg-dump-bytes")
        return True, ""

    monkeypatch.setattr(backup_service, "run_pg_dump", fake_pg_dump)
    return settings


@pytest.fixture
def test_sessions(db, monkeypatch):
    """run_backup crea su propia session con app.database.SessionLocal."""
    from sqlalchemy.orm import sessionmaker
    from app import database as app_database
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=db.bind)
    monkeypatch.setattr(app_database, "SessionLocal", test_session)
    return test_session


def _make_item(db, regular_user):
    """Un manga + un cómic + un libro para que el JSON no esté vacío."""
    from .conftest import _make_manga, _make_comic, _make_book
    _make_manga(db, regular_user, title="Backup Manga")
    _make_comic(db, regular_user, title="Backup Comic")
    _make_book(db, regular_user, title="Backup Book")


# ── run_backup ─────────────────────────────────────────────────────────────────

def test_run_backup_creates_json_and_dump(db, backup_env, test_sessions, regular_user):
    _make_item(db, regular_user)

    summary = backup_service.run_backup()

    assert summary["ok"] is True
    assert summary["json"]["ok"] is True
    assert summary["pg_dump"]["ok"] is True

    backup_dir = Path(backup_env.BACKUP_DIR)
    json_files = list(backup_dir.glob("*.json"))
    assert len(json_files) == 1
    data = json.loads(json_files[0].read_text())
    assert data["type"] == "full-backup"
    assert regular_user.username in data["users"]
    titles = [m["title"] for m in data["users"][regular_user.username]["manga"]]
    assert "Backup Manga" in titles


def test_run_backup_pg_dump_failure_still_ok(backup_env, monkeypatch, test_sessions, db, regular_user):
    monkeypatch.setattr(backup_service, "run_pg_dump", lambda d, ts: (False, "pg_dump no disponible"))

    summary = backup_service.run_backup()

    # El JSON portable sigue siendo un backup válido
    assert summary["ok"] is True
    assert summary["pg_dump"]["ok"] is False
    assert "no disponible" in summary["pg_dump"]["error"]


def test_run_backup_never_raises(backup_env, monkeypatch, test_sessions, db, regular_user):
    # El JSON explota (BD caída) → run_backup debe devolver resumen, no lanzar
    monkeypatch.setattr(backup_service, "export_json_backup", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))

    summary = backup_service.run_backup()

    assert summary["ok"] is True          # pg_dump (mockeado) sí funcionó
    assert summary["json"]["ok"] is False
    assert "db down" in summary["json"]["error"]


# ── apply_retention ────────────────────────────────────────────────────────────

def test_apply_retention_keeps_newest(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    base = datetime(2026, 10, 1, 4, 0, 0)

    for i in range(6):
        ts = (base + timedelta(days=i * 7)).strftime("%Y%m%d-%H%M%S")
        (backup_dir / f"{ts}.json").write_text("{}")
        (backup_dir / f"{ts}.dump").write_bytes(b"x")

    deleted = backup_service.apply_retention(backup_dir, retention=3)

    assert len(deleted) == 3
    remaining = sorted(p.name for p in backup_dir.iterdir())
    # Los 3 más recientes (20261022, 20261029, 20261105) siguen; los 3 primeros borrados
    assert len(remaining) == 6  # 3 ts × 2 archivos
    assert "20261001-040000.json" not in remaining
    assert "20261008-040000.json" not in remaining
    assert "20261105-040000.json" in remaining  # más reciente
    assert "20261022-040000.dump" in remaining


def test_apply_retention_ignores_foreign_files(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    (backup_dir / "notas.txt").write_text("hola")
    (backup_dir / "random.json").write_text("{}")  # no sigue el patrón <ts>.json

    deleted = backup_service.apply_retention(backup_dir, retention=2)

    assert deleted == []
    assert (backup_dir / "notas.txt").exists()
    assert (backup_dir / "random.json").exists()


def test_apply_retention_negative_disables(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    (backup_dir / "20261001-040000.json").write_text("{}")

    assert backup_service.apply_retention(backup_dir, retention=-1) == []
    assert (backup_dir / "20261001-040000.json").exists()


# ── delete_backup ──────────────────────────────────────────────────────────────

def test_delete_backup_rejects_traversal(backup_env):
    assert backup_service.delete_backup("../etc/passwd") is False
    assert backup_service.delete_backup("2026/1004-040000") is False
    assert backup_service.delete_backup("no-valid-name") is False
    assert backup_service.delete_backup("") is False


def test_delete_backup_valid(backup_env):
    backup_dir = Path(backup_env.BACKUP_DIR)
    backup_dir.mkdir(parents=True)
    (backup_dir / "20261004-040000.json").write_text("{}")
    (backup_dir / "20261004-040000.dump").write_bytes(b"x")

    assert backup_service.delete_backup("20261004-040000") is True
    assert not (backup_dir / "20261004-040000.json").exists()
    assert not (backup_dir / "20261004-040000.dump").exists()

    # Ya no existe → False
    assert backup_service.delete_backup("20261004-040000") is False


# ── list_backups ───────────────────────────────────────────────────────────────

def test_list_backups_structure(backup_env):
    backup_dir = Path(backup_env.BACKUP_DIR)
    backup_dir.mkdir(parents=True)
    (backup_dir / "20261004-040000.json").write_text("x" * 100)
    (backup_dir / "20261004-040000.dump").write_bytes(b"y" * 200)

    result = backup_service.list_backups()

    assert len(result) == 1
    entry = result[0]
    assert entry["timestamp"] == "20261004-040000"
    assert entry["json"]["bytes"] == 100
    assert entry["pg_dump"]["bytes"] == 200
    assert "modified" in entry["json"]


def test_list_backups_empty_when_no_dir(backup_env, monkeypatch):
    backup_env.BACKUP_DIR = str(Path(backup_env.BACKUP_DIR) / "no-existe")
    assert backup_service.list_backups() == []


# ── Endpoints ──────────────────────────────────────────────────────────────────

def test_list_backups_endpoint_admin(client, backup_env, admin_headers):
    r = client.get("/api/v1/system/backups", headers=admin_headers)
    assert r.status_code == 200
    assert "backups" in r.json()


def test_list_backups_endpoint_forbidden(client, backup_env, auth_headers):
    r = client.get("/api/v1/system/backups", headers=auth_headers)
    assert r.status_code == 403


def test_trigger_backup_endpoint_admin(client, backup_env, admin_headers, monkeypatch):
    monkeypatch.setattr(
        backup_service, "run_backup",
        lambda: {"ok": True, "timestamp": "20261004-040000", "json": {"ok": True}, "pg_dump": {"ok": True}, "deleted": []},
    )
    r = client.post("/api/v1/system/backup", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_trigger_backup_endpoint_failure(client, backup_env, admin_headers, monkeypatch):
    monkeypatch.setattr(backup_service, "run_backup", lambda: {"ok": False, "error": "boom"})
    r = client.post("/api/v1/system/backup", headers=admin_headers)
    assert r.status_code == 500
    assert "boom" in r.json()["detail"]


def test_trigger_backup_endpoint_forbidden(client, backup_env, auth_headers):
    r = client.post("/api/v1/system/backup", headers=auth_headers)
    assert r.status_code == 403


def test_delete_backup_endpoint(client, backup_env, admin_headers):
    backup_dir = Path(backup_env.BACKUP_DIR)
    backup_dir.mkdir(parents=True)
    (backup_dir / "20261004-040000.json").write_text("{}")

    r = client.delete("/api/v1/system/backups/20261004-040000", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r = client.delete("/api/v1/system/backups/20261004-040000", headers=admin_headers)
    assert r.status_code == 404

    r = client.delete("/api/v1/system/backups/..%2F..%2Fetc", headers=admin_headers)
    assert r.status_code == 404


def test_delete_backup_endpoint_forbidden(client, backup_env, auth_headers):
    r = client.delete("/api/v1/system/backups/20261004-040000", headers=auth_headers)
    assert r.status_code == 403
