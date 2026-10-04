"""
Tests de telemetría persistente por scraper/host + priorización dinámica (roadmap #13).

Cubre:
- upsert de éxitos/fallos (host y scraper) con tasa y racha de fallos
- umbrales de penalización (mínimo de intentos, tasa < 50% → +2, < 30% → +4, racha ≥ 5 → +4)
- prioridad efectiva y reordenamiento dinámico de links de descarga
- reset manual
- endpoints admin: GET /system/scraper-stats + POST /system/scraper-stats/reset/{kind}/{name}
"""
import pytest

from app import database as app_database
from app.services import scraper_telemetry
from app.services.scraper_telemetry import (
    record_success,
    record_failure,
    get_stats,
    reset,
    dynamic_penalty,
    effective_host_priority,
    sort_links_dynamically,
    PENALTY_WARN,
    PENALTY_BAD,
)

MEDIAFIRE_URL = "https://www.mediafire.com/file/abc123/test.cbz/file"
MEGA_URL = "https://mega.nz/file/xyz789#token"


@pytest.fixture
def telemetry(db, monkeypatch):
    """Apunta el servicio de telemetría a la BD de tests (in-memory StaticPool)."""
    from sqlalchemy.orm import sessionmaker
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=db.bind)
    monkeypatch.setattr(app_database, "SessionLocal", test_session)
    yield test_session


def _stats_for(kind: str, name: str):
    return [s for s in get_stats() if s["kind"] == kind and s["name"] == name]


def _fill(kind: str, name: str, successes: int, failures: int):
    for _ in range(successes):
        record_success(kind, name)
    for _ in range(failures):
        record_failure(kind, name)


# ── Registro (upsert) ──────────────────────────────────────────────────────────

def test_record_upsert_and_rate(telemetry):
    record_success("host", "mediafire")
    record_success("host", "mediafire")
    record_failure("host", "mediafire", "HTTP 404")

    stats = _stats_for("host", "mediafire")
    assert len(stats) == 1
    s = stats[0]
    assert s["successes"] == 2
    assert s["failures"] == 1
    assert s["attempts"] == 3
    assert s["success_rate"] == pytest.approx(0.667, abs=0.001)
    assert s["streak_failures"] == 1  # S, S, F → 1 fallo consecutivo al final
    assert s["last_error"] == "HTTP 404"
    assert s["dynamic_penalty"] == 0  # muestra < MIN_ATTEMPTS


def test_record_separate_kinds(telemetry):
    record_failure("host", "mediafire")
    record_success("scraper", "zonacomics")

    assert len(_stats_for("host", "mediafire")) == 1
    assert len(_stats_for("scraper", "zonacomics")) == 1
    assert get_stats()[0]["key"] in ("host:mediafire", "scraper:zonacomics")


def test_streak_resets_on_success(telemetry):
    record_failure("scraper", "zonacomics")
    record_failure("scraper", "zonacomics")
    record_failure("scraper", "zonacomics")
    s = _stats_for("scraper", "zonacomics")[0]
    assert s["streak_failures"] == 3

    record_success("scraper", "zonacomics")
    s = _stats_for("scraper", "zonacomics")[0]
    assert s["streak_failures"] == 0
    assert s["successes"] == 1
    assert s["failures"] == 3


def test_record_invalid_input_noop(telemetry):
    record_success("", "mediafire")   # kind vacío
    record_success("host", "")        # name vacío
    assert get_stats() == []


# ── Penalización dinámica ──────────────────────────────────────────────────────

def test_penalty_no_data(telemetry):
    assert dynamic_penalty("host", "mediafire") == 0
    assert dynamic_penalty("scraper", "noexistente") == 0


def test_penalty_requires_min_attempts(telemetry):
    # Tasa 0% pero solo 2 intentos → sin evidencia suficiente
    _fill("host", "mediafire", 0, 2)
    assert dynamic_penalty("host", "mediafire") == 0


def test_penalty_warn_at_40_percent(telemetry):
    # 2/5 = 40% → PENALTY_WARN
    _fill("host", "mediafire", 2, 3)
    assert dynamic_penalty("host", "mediafire") == PENALTY_WARN


def test_penalty_bad_at_20_percent(telemetry):
    # 2/10 = 20% → PENALTY_BAD
    _fill("host", "mediafire", 2, 8)
    assert dynamic_penalty("host", "mediafire") == PENALTY_BAD


def test_penalty_bad_on_streak_even_with_good_rate(telemetry):
    # 10 éxitos seguidos y luego 5 fallos: tasa 67% pero racha 5 → PENALTY_BAD
    _fill("host", "mega", 10, 0)
    _fill("host", "mega", 0, 5)
    assert dynamic_penalty("host", "mega") == PENALTY_BAD


# ── Prioridad efectiva y orden dinámico ────────────────────────────────────────

def test_effective_priority_no_stats(telemetry):
    from app.services.host_manager import get_host_priority
    assert effective_host_priority(MEDIAFIRE_URL) == get_host_priority(MEDIAFIRE_URL)


def test_effective_priority_with_penalty(telemetry):
    from app.services.host_manager import get_host_priority
    base = get_host_priority(MEDIAFIRE_URL)  # 1 (EXCELLENT)
    _fill("host", "mediafire", 2, 8)  # 20% → PENALTY_BAD
    assert effective_host_priority(MEDIAFIRE_URL) == base + PENALTY_BAD


def test_dynamic_sort_demotes_failing_host(telemetry):
    from app.services.host_manager import get_host_priority
    base_mf = get_host_priority(MEDIAFIRE_URL)   # 1
    base_mega = get_host_priority(MEGA_URL)      # 2
    assert base_mf < base_mega

    links = [{"url": MEDIAFIRE_URL}, {"url": MEGA_URL}]
    # Sin telemetría: mediafire primero
    assert [l["url"] for l in sort_links_dynamically(links)] == [MEDIAFIRE_URL, MEGA_URL]

    # Mediafire con tasa 20% → 1+4=5 > mega 2 → mega primero
    _fill("host", "mediafire", 2, 8)
    ordered = [l["url"] for l in sort_links_dynamically(links)]
    assert ordered == [MEGA_URL, MEDIAFIRE_URL]


def test_sort_links_empty_and_unknown_host(telemetry):
    assert sort_links_dynamically([]) == []
    links = [{"url": "https://desconocido.example.com/x.cbz"}]
    # Host desconocido → MEDIUM (3), sin telemetría → orden intacto
    assert [l["url"] for l in sort_links_dynamically(links)] == [links[0]["url"]]


# ── Reset ──────────────────────────────────────────────────────────────────────

def test_reset(telemetry):
    _fill("host", "mediafire", 1, 2)
    assert _stats_for("host", "mediafire")
    assert reset("host", "mediafire") is True
    assert _stats_for("host", "mediafire") == []
    assert reset("host", "mediafire") is False   # ya no existe
    assert reset("bogus", "x") is False           # kind inválido


# ── Endpoints admin ────────────────────────────────────────────────────────────

def test_scraper_stats_admin(client, db, admin_headers, telemetry):
    _fill("scraper", "zonacomics", 1, 1)
    r = client.get("/api/v1/system/scraper-stats", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["with_penalty"] == 0
    s = data["stats"][0]
    assert s["key"] == "scraper:zonacomics"
    assert s["successes"] == 1 and s["failures"] == 1


def test_scraper_stats_requires_admin(client, db, auth_headers, telemetry):
    r = client.get("/api/v1/system/scraper-stats", headers=auth_headers)
    assert r.status_code == 403


def test_scraper_stats_requires_auth(client, db, telemetry):
    r = client.get("/api/v1/system/scraper-stats")
    assert r.status_code in (401, 403)


def test_reset_endpoint(client, db, admin_headers, telemetry):
    _fill("host", "mediafire", 0, 2)
    r = client.post("/api/v1/system/scraper-stats/reset/host/mediafire", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # Segunda vez: ya no hay métricas
    r2 = client.post("/api/v1/system/scraper-stats/reset/host/mediafire", headers=admin_headers)
    assert r2.status_code == 404
    # kind inválido
    r3 = client.post("/api/v1/system/scraper-stats/reset/bogus/x", headers=admin_headers)
    assert r3.status_code == 400


def test_reset_endpoint_requires_admin(client, db, auth_headers, telemetry):
    _fill("host", "mediafire", 0, 2)
    r = client.post("/api/v1/system/scraper-stats/reset/host/mediafire", headers=auth_headers)
    assert r.status_code == 403
