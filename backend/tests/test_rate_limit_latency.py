"""
Tests de roadmap #17: rate-limit de búsquedas + latencia p95 en panel de logs.

- SlidingWindowRateLimiter: máx por ventana, expiración, reset, thread-safety
- LatencyTracker: percentiles (p50/p95/p99), ventana temporal, agrupación por route
- GET /system/latency: admin 200 / usuario 403, el middleware registra peticiones
- Endpoints de búsqueda: 429 al exceder el límite (con AniList stubeado, sin red)
"""
import threading
import time

import pytest

import app.core.rate_limit as rate_limit_module
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.latency import LatencyTracker


# ── SlidingWindowRateLimiter ──────────────────────────────────────────────────

def test_limiter_allows_up_to_max():
    lim = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)
    assert lim.allow("u1") is True
    assert lim.allow("u1") is True
    assert lim.allow("u1") is True
    assert lim.allow("u1") is False  # 4ª rechazada
    assert lim.remaining("u1") == 0
    assert lim.remaining("unknown") == 3


def test_limiter_keys_are_independent():
    lim = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)
    assert lim.allow("u1") is True
    assert lim.allow("u1") is False
    assert lim.allow("u2") is True  # otro key no se ve afectado


def test_limiter_window_expiry():
    lim = SlidingWindowRateLimiter(max_requests=2, window_seconds=1)
    assert lim.allow("u1") is True
    assert lim.allow("u1") is True
    assert lim.allow("u1") is False
    time.sleep(1.05)
    assert lim.allow("u1") is True  # ventana expirada → vuelve a permitir


def test_limiter_reset():
    lim = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)
    assert lim.allow("u1") is True
    assert lim.allow("u1") is False
    lim.reset("u1")
    assert lim.allow("u1") is True


def test_limiter_thread_safety():
    """80 attempts concurrentes con max=10 → exactamente 10 permitidas."""
    lim = SlidingWindowRateLimiter(max_requests=10, window_seconds=60)
    results = []
    lock = threading.Lock()

    def worker():
        allowed = sum(1 for _ in range(20) if lim.allow("shared"))
        with lock:
            results.append(allowed)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(results) == 10


# ── LatencyTracker ────────────────────────────────────────────────────────────

def test_tracker_percentiles():
    tr = LatencyTracker()
    for i in range(1, 101):
        tr.record("/api/v1/x", float(i))

    stats = tr.stats(window_minutes=60)
    assert stats["count"] == 100
    assert stats["max_ms"] == 100.0
    # Interpolación lineal: p50=50.5, p95=95.05→95.0 y p99=99.01→99.0 tras round(·,1)
    # (95.05 es 95.0499… en float64 → redondea a 95.0)
    assert stats["p50_ms"] == 50.5
    assert stats["p95_ms"] == 95.0
    assert stats["p99_ms"] == 99.0
    assert stats["avg_ms"] == 50.5


def test_tracker_empty():
    tr = LatencyTracker()
    stats = tr.stats()
    assert stats["count"] == 0
    assert stats["p95_ms"] is None
    assert stats["slowest"] == []


def test_tracker_window_filtering():
    tr = LatencyTracker()
    # Muestra "vieja" (hace 5 min) insertada directamente en el deque
    tr._samples.append((time.time() - 300, "/api/v1/old", 9999.0))
    tr.record("/api/v1/new", 10.0)

    stats = tr.stats(window_minutes=1)
    assert stats["count"] == 1
    assert stats["max_ms"] == 10.0


def test_tracker_slowest_grouping():
    tr = LatencyTracker()
    for _ in range(10):
        tr.record("/api/v1/fast", 5.0)
    for _ in range(5):
        tr.record("/api/v1/slow", 500.0)

    stats = tr.stats()
    assert stats["slowest"][0]["route"] == "/api/v1/slow"
    assert stats["slowest"][0]["count"] == 5
    assert stats["slowest"][0]["p95_ms"] == 500.0
    assert stats["slowest"][1]["route"] == "/api/v1/fast"
    assert stats["slowest"][1]["p95_ms"] == 5.0


# ── Endpoint GET /system/latency ─────────────────────────────────────────────

def test_latency_endpoint_admin(client, admin_headers):
    r = client.get("/api/v1/system/latency", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert "p95_ms" in data
    assert "p50_ms" in data
    assert "slowest" in data


def test_latency_endpoint_forbidden(client, auth_headers):
    r = client.get("/api/v1/system/latency", headers=auth_headers)
    assert r.status_code == 403


def test_latency_middleware_records_api_requests(client, admin_headers):
    """El middleware registra las peticiones a /api/v1/* en el tracker."""
    from app.core.latency import get_latency_tracker
    tracker = get_latency_tracker()

    before = tracker.stats(window_minutes=1)["count"]
    r = client.get("/api/v1/system/latency", headers=admin_headers)
    assert r.status_code == 200
    after = tracker.stats(window_minutes=1)["count"]
    assert after >= before + 1


# ── Rate-limit en endpoints de búsqueda ──────────────────────────────────────

@pytest.fixture
def tight_search_limiter(monkeypatch):
    """Límite de 3 búsquedas/min (el default es 30/5min) para forzar el 429."""
    monkeypatch.setattr(
        rate_limit_module, "_search_limiter",
        SlidingWindowRateLimiter(max_requests=3, window_seconds=60),
    )


def test_manga_search_rate_limit_429(client, auth_headers, tight_search_limiter, monkeypatch):
    """Las 3 primeras búsquedas → 200; la 4ª → 429. AniList stubeado (sin red)."""
    import app.api.v1.manga as manga_module

    class _FakeAnilist:
        async def search_manga(self, q, page=1, per_page=20):
            return {"results": [], "total": 0}

    monkeypatch.setattr(manga_module, "AnilistService", _FakeAnilist)

    for i in range(3):
        r = client.get(f"/api/v1/manga/search?q=busqueda+{i}", headers=auth_headers)
        assert r.status_code == 200, r.text

    r = client.get("/api/v1/manga/search?q=otra", headers=auth_headers)
    assert r.status_code == 429
    assert "Demasiadas búsquedas" in r.json()["detail"]


def test_rate_limit_is_per_user(client, admin_headers, auth_headers, tight_search_limiter, monkeypatch):
    """El límite es por usuario: agotar el de `user` no afecta al admin."""
    import app.api.v1.manga as manga_module

    class _FakeAnilist:
        async def search_manga(self, q, page=1, per_page=20):
            return {"results": [], "total": 0}

    monkeypatch.setattr(manga_module, "AnilistService", _FakeAnilist)

    for i in range(3):
        r = client.get(f"/api/v1/manga/search?q=user+{i}", headers=auth_headers)
        assert r.status_code == 200

    # El mismo user sigue limitado...
    r = client.get("/api/v1/manga/search?q=otra", headers=auth_headers)
    assert r.status_code == 429
    # ...pero otro usuario no lo está
    r = client.get("/api/v1/manga/search?q=admin+busca", headers=admin_headers)
    assert r.status_code == 200
