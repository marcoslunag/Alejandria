"""Tests del proxy de portadas con caché local + ETag (roadmap #12)."""
import hashlib

import pytest

from app.api.v1 import covers as covers_module

COVER_URL = "https://media.anilist.co/file/cover.jpg"
OTHER_URL = "https://www.comicvine.com/cover.png"
# CDN actual de AniList (el que devuelve la API hoy): s4.anilist.co, NO media.anilist.co
ANILIST_S4_URL = "https://s4.anilist.co/file/anilistcdn/media/manga/cover/large/bx30013-BeslEMqiPhlk.jpg"
FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"fake-image-data" * 10


class _FakeResp:
    def __init__(self, status_code=200, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {"Content-Type": "image/jpeg"}


def _patch_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(covers_module, "_cache_dir", lambda: tmp_path)
    calls = {"n": 0}

    def fake_get(url, timeout=None, stream=None):
        calls["n"] += 1
        return _FakeResp(200, FAKE_JPEG, {"Content-Type": "image/jpeg"})

    monkeypatch.setattr(covers_module.requests, "get", fake_get)
    return calls


def test_proxy_requires_auth(client):
    r = client.get("/api/v1/covers/proxy", params={"url": COVER_URL})
    assert r.status_code in (401, 403)


def test_proxy_accepts_token_query_param(client, regular_user, regular_token, monkeypatch, tmp_path):
    """<img src> no puede enviar cabeceras: el token va por ?token= (mismo patrón que el web reader)."""
    _patch_cache(monkeypatch, tmp_path)
    r = client.get(
        "/api/v1/covers/proxy",
        params={"url": COVER_URL, "token": regular_token},
    )
    assert r.status_code == 200
    assert r.content == FAKE_JPEG


def test_proxy_rejects_invalid_token_query_param(client, monkeypatch, tmp_path):
    """?token= inválido → 401 (no 500)."""
    _patch_cache(monkeypatch, tmp_path)
    r = client.get(
        "/api/v1/covers/proxy",
        params={"url": COVER_URL, "token": "token-invalido"},
    )
    assert r.status_code == 401


def test_proxy_allows_anilist_s4_cdn(client, auth_headers, monkeypatch, tmp_path):
    """Regresión: las portadas de manga usan s4.anilist.co (CDN actual de AniList).
    Antes solo estaba media.anilist.co en el allowlist → 400 y las portadas no se veían."""
    _patch_cache(monkeypatch, tmp_path)
    r = client.get(
        "/api/v1/covers/proxy",
        params={"url": ANILIST_S4_URL},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.content == FAKE_JPEG


def test_proxy_rejects_non_allowlisted_host(client, auth_headers):
    r = client.get(
        "/api/v1/covers/proxy",
        params={"url": "https://evil.example.com/secret.jpg"},
        headers=auth_headers,
    )
    assert r.status_code == 400


def test_proxy_rejects_non_http_url(client, auth_headers):
    r = client.get(
        "/api/v1/covers/proxy",
        params={"url": "ftp://media.anilist.co/x.jpg"},
        headers=auth_headers,
    )
    assert r.status_code == 400


def test_proxy_serves_image_with_etag_and_cache_headers(client, auth_headers, monkeypatch, tmp_path):
    _patch_cache(monkeypatch, tmp_path)

    r = client.get("/api/v1/covers/proxy", params={"url": COVER_URL}, headers=auth_headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/jpeg")
    assert r.content == FAKE_JPEG
    etag = r.headers["etag"]
    assert etag == '"' + hashlib.md5(FAKE_JPEG).hexdigest() + '"'
    assert "max-age=" in r.headers["cache-control"]


def test_proxy_caches_and_returns_304(client, auth_headers, monkeypatch, tmp_path):
    calls = _patch_cache(monkeypatch, tmp_path)

    r1 = client.get("/api/v1/covers/proxy", params={"url": COVER_URL}, headers=auth_headers)
    assert r1.status_code == 200
    etag = r1.headers["etag"]
    assert calls["n"] == 1

    # Segunda petición con If-None-Match → 304 SIN fetch externo
    r2 = client.get(
        "/api/v1/covers/proxy",
        params={"url": COVER_URL},
        headers={**auth_headers, "If-None-Match": etag},
    )
    assert r2.status_code == 304
    assert calls["n"] == 1  # sin fetch: servido desde caché


def test_proxy_cache_hit_without_revalidate(client, auth_headers, monkeypatch, tmp_path):
    calls = _patch_cache(monkeypatch, tmp_path)

    r1 = client.get("/api/v1/covers/proxy", params={"url": COVER_URL}, headers=auth_headers)
    assert r1.status_code == 200

    # Misma URL, sin If-None-Match → 200 desde caché, sin fetch nuevo
    r2 = client.get("/api/v1/covers/proxy", params={"url": COVER_URL}, headers=auth_headers)
    assert r2.status_code == 200
    assert r2.content == FAKE_JPEG
    assert calls["n"] == 1


def test_proxy_rejects_non_image_content(client, auth_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(covers_module, "_cache_dir", lambda: tmp_path)

    def fake_get(url, timeout=None, stream=None):
        return _FakeResp(200, b"<html>not an image</html>", {"Content-Type": "text/html"})

    monkeypatch.setattr(covers_module.requests, "get", fake_get)

    r = client.get("/api/v1/covers/proxy", params={"url": COVER_URL}, headers=auth_headers)
    assert r.status_code == 502


def test_proxy_upstream_error(client, auth_headers, monkeypatch, tmp_path):
    import requests as req
    monkeypatch.setattr(covers_module, "_cache_dir", lambda: tmp_path)

    def fake_get(url, timeout=None, stream=None):
        raise req.RequestException("connection refused")

    monkeypatch.setattr(covers_module.requests, "get", fake_get)

    r = client.get("/api/v1/covers/proxy", params={"url": COVER_URL}, headers=auth_headers)
    assert r.status_code == 502


def test_proxy_distinct_urls_distinct_cache(client, auth_headers, monkeypatch, tmp_path):
    calls = _patch_cache(monkeypatch, tmp_path)

    r1 = client.get("/api/v1/covers/proxy", params={"url": COVER_URL}, headers=auth_headers)
    r2 = client.get("/api/v1/covers/proxy", params={"url": OTHER_URL}, headers=auth_headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert calls["n"] == 2  # cada URL fetcha una vez
    assert len(list(tmp_path.iterdir())) == 2
