"""
Tests de lógica pura (roadmap #15) — sin red, sin BD:
- Scorer TomosManga (find_best_match): re-ediciones +25, recencia +5/año, color -20, guía -100
- detect_bundle: patrones #1-30, [12/12], [5 de 5], [N Tomos], 'collects', 'complete'
- Clasificador de fallos STK: definitivo vs transitorio, burst window, MAX_CONSECUTIVE_FAILURES
- Rate-limiter del traductor: espaciado mínimo entre llamadas (thread-safe)
"""
import threading
import time

import pytest


# ── 1. Scorer TomosManga ──────────────────────────────────────────────────────

@pytest.fixture
def scorer():
    from app.services.tomosmanga_search import TomosMangaSearch
    s = TomosMangaSearch()
    s._fixed_results = []
    s.search = lambda query: s._fixed_results  # evita red
    return s


def _pick(scorer, query, titles):
    scorer._fixed_results = [{"title": t} for t in titles]
    return scorer.find_best_match(query)


def test_scorer_empty_results(scorer):
    scorer._fixed_results = []
    assert scorer.find_best_match("One Piece") is None


def test_scorer_single_result_returned_directly(scorer):
    scorer._fixed_results = [{"title": "One Piece [01-100]"}]
    result = scorer.find_best_match("One Piece")
    assert result["title"] == "One Piece [01-100]"


def test_scorer_reedition_wins(scorer):
    # Re-edición: +25 (re-edición) + recencia 2023 (+40) > original exacto (+100)
    result = _pick(scorer, "One Piece", ["One Piece", "One Piece [Nueva Edición 2023]"])
    assert result["title"] == "One Piece [Nueva Edición 2023]"


def test_scorer_recent_year_beats_old_year(scorer):
    result = _pick(scorer, "One Piece", ["One Piece [2018]", "One Piece [2023]"])
    assert result["title"] == "One Piece [2023]"


def test_scorer_more_volumes_wins(scorer):
    result = _pick(scorer, "One Piece", ["One Piece", "One Piece [01-72]"])
    assert result["title"] == "One Piece [01-72]"


def test_scorer_guide_penalized(scorer):
    result = _pick(scorer, "One Piece", ["One Piece", "One Piece Guía Oficial"])
    assert result["title"] == "One Piece"


def test_scorer_color_penalized(scorer):
    result = _pick(scorer, "One Piece", ["One Piece", "One Piece Color"])
    assert result["title"] == "One Piece"


def test_scorer_spinoff_penalized(scorer):
    # "Boruto: Naruto" → -80 (spin-off) frente a "Naruto" exacto (+100)
    result = _pick(scorer, "Naruto", ["Naruto", "Boruto: Naruto Next Generations"])
    assert result["title"] == "Naruto"


def test_scorer_complete_bonus(scorer):
    # 'completo' +30: "One Piece Completo" (parcial +50 +30) gana a "One Piece Deluxe" (parcial +50)
    result = _pick(scorer, "One Piece", ["One Piece Deluxe", "One Piece Completo"])
    assert result["title"] == "One Piece Completo"


# ── 2. detect_bundle ──────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def detect_bundle():
    from app.services.comic_service import detect_bundle as _detect
    return _detect


def test_bundle_explicit_range(detect_bundle):
    info = detect_bundle("Batman #1-30")
    assert info["type"] == "range"
    assert info["range"] == "#1-30"
    assert info["issues"] == list(range(1, 31))


def test_bundle_hash_range_with_hash(detect_bundle):
    info = detect_bundle("Batman #4-#12")
    assert info["range"] == "#4-12"
    assert info["issues"] == list(range(4, 13))


def test_bundle_fraction_complete(detect_bundle):
    info = detect_bundle("Batman [12/12]")
    assert info["range"] == "#1-12"
    assert info["issues"] == list(range(1, 13))


def test_bundle_de_n(detect_bundle):
    info = detect_bundle("Batman [5 de 5]")
    assert info["range"] == "#1-5"


def test_bundle_n_tomos(detect_bundle):
    info = detect_bundle("Batman [9 Tomos]")
    assert info["type"] == "complete"
    assert info["range"] == "#1-9"
    assert len(info["issues"]) == 9


def test_bundle_n_numeros(detect_bundle):
    info = detect_bundle("Batman [80 números]")
    assert info["type"] == "complete"
    assert info["range"] == "#1-80"


def test_bundle_reversed_range_not_detected(detect_bundle):
    # #30-1 no es un rango válido → None
    assert detect_bundle("Batman #30-1") is None


def test_bundle_single_volume_not_detected(detect_bundle):
    assert detect_bundle("Batman Vol. 4") is None


def test_bundle_collects_statement(detect_bundle):
    info = detect_bundle("Batman", description="Collects #13 - #15")
    assert info["type"] == "collects"
    assert info["range"] == "#13-15"
    assert info["issues"] == [13, 14, 15]


def test_bundle_issues_range_in_description(detect_bundle):
    # "Collects issues #13 - #15" → el patrón de rango 'issues N - M' lo captura antes
    info = detect_bundle("Batman", description="Collects issues #13 - #15")
    assert info["range"] == "#13-15"
    assert info["issues"] == [13, 14, 15]


def test_bundle_complete_with_count_of_issues(detect_bundle):
    info = detect_bundle("Batman Complete Collection", count_of_issues=12)
    assert info["type"] == "complete"
    assert info["range"] == "#1-12"
    assert len(info["issues"]) == 12


def test_bundle_plain_issue_not_detected(detect_bundle):
    assert detect_bundle("Batman #4") is None


# ── 3. Clasificador de fallos STK ─────────────────────────────────────────────

@pytest.fixture
def stk_sender():
    from app.services.stk_kindle_sender import STKKindleSender
    return STKKindleSender(user_id=99999)  # sin cliente en disco → sin red


def test_stk_definitive_expiry_signals(stk_sender):
    assert stk_sender._is_definitive_expiry("Invalid ADP Token provided")
    assert stk_sender._is_definitive_expiry("adp_token is invalid")
    assert stk_sender._is_definitive_expiry("Device not registered")
    assert stk_sender._is_definitive_expiry("customer not found")


def test_stk_transient_errors_not_definitive(stk_sender):
    for msg in ("403 Forbidden", "Read timeout", "503 Service Unavailable", "connection reset"):
        assert not stk_sender._is_definitive_expiry(msg), msg
        assert stk_sender._is_temporary_error(msg), msg


def test_stk_unclassified_error_keeps_session(stk_sender):
    assert stk_sender._record_failure("some weird unknown error") is False
    assert stk_sender._consecutive_failures == 0


def test_stk_burst_counts_as_one_operation(stk_sender):
    assert stk_sender._record_failure("invalid adp token") is False
    assert stk_sender._consecutive_failures == 1
    # Segundo fallo a los 2s (dentro de burst de 120s) → NO suma
    assert stk_sender._record_failure("invalid adp token") is False
    assert stk_sender._consecutive_failures == 1


def test_stk_max_consecutive_failures_triggers_reauth(stk_sender):
    from app.services import stk_kindle_sender as stk_module
    for i in range(stk_module.MAX_CONSECUTIVE_FAILURES):
        stk_sender._last_definitive_failure_at = 0.0  # simula operación previa lejana (fuera de burst)
        should_reauth = stk_sender._record_failure("invalid adp token")
        if i < stk_module.MAX_CONSECUTIVE_FAILURES - 1:
            assert should_reauth is False
    assert should_reauth is True


def test_stk_reset_failure_count(stk_sender):
    stk_sender._consecutive_failures = 19
    stk_sender._last_definitive_failure_at = 12345.0
    stk_sender._reset_failure_count()
    assert stk_sender._consecutive_failures == 0
    assert stk_sender._last_definitive_failure_at == 0.0


def test_stk_session_invalid_signals(stk_sender):
    # Amazon rechaza el token del dispositivo → "sesión inválida"
    assert stk_sender._is_session_invalid("Failed to validate DeviceInfoToken.")
    assert stk_sender._is_session_invalid('HTTP Error 403: {"Message": "Failed to validate DeviceInfoToken."}')
    # Un 403 genérico (rate limit) NO es "sesión inválida"
    assert not stk_sender._is_session_invalid("403 Forbidden")
    # Ni un fallo definitivo lo es
    assert not stk_sender._is_session_invalid("invalid adp token")


def test_stk_deviceinfotoken_is_not_definitive(stk_sender):
    # Regresión de la "muerte diaria": deviceinfotoken NO debe acumular hacia el
    # auto-logout (no borra la sesión), aunque sí marque el banner.
    assert not stk_sender._is_definitive_expiry("Failed to validate DeviceInfoToken.")
    assert stk_sender._record_failure("Failed to validate DeviceInfoToken.") is False
    assert stk_sender._consecutive_failures == 0


def test_stk_deviceinfotoken_marks_reauth_banner(stk_sender, monkeypatch):
    from app.services import stk_kindle_sender as stk_module
    calls = []
    monkeypatch.setattr(
        stk_module, "mark_stk_needs_reauth",
        lambda uid, reason="": calls.append((uid, reason)),
    )
    # Un DeviceInfoToken inválido marca el banner (reconectar) SIN borrar la sesión
    # (_record_failure devuelve False → el caller no llama a logout()).
    assert stk_sender._record_failure('HTTP Error 403: {"Message": "Failed to validate DeviceInfoToken."}') is False
    assert len(calls) == 1
    assert calls[0][0] == 99999
    assert "token inválido" in calls[0][1]


# ── 4. Rate-limiter del traductor ─────────────────────────────────────────────

@pytest.fixture
def rate_limiter():
    from app.services.translator import _TranslateRateLimiter
    return _TranslateRateLimiter(min_interval=0.05)


def test_rate_limiter_first_call_immediate(rate_limiter):
    t0 = time.monotonic()
    rate_limiter.wait()
    assert time.monotonic() - t0 < 0.04


def test_rate_limiter_spaces_calls(rate_limiter):
    t0 = time.monotonic()
    for _ in range(5):
        rate_limiter.wait()
    elapsed = time.monotonic() - t0
    # 5 llamadas: la primera inmediata + 4 esperas de 50ms → ≥ 200ms (con margen)
    assert elapsed >= 0.18, f"esperado ≥0.18s, real {elapsed:.3f}s"


def test_rate_limiter_thread_safe_slots():
    from app.services.translator import _TranslateRateLimiter
    rl = _TranslateRateLimiter(min_interval=0.05)
    n_threads = 6
    stamps = []
    lock = threading.Lock()

    def worker():
        rl.wait()
        with lock:
            stamps.append(time.monotonic())

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    t0 = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - t0

    stamps.sort()
    # Cada slot separa ≥ 50ms (con tolerancia de scheduling)
    for a, b in zip(stamps, stamps[1:]):
        assert b - a >= 0.03, f"slots demasiado juntos: {b - a:.4f}s"
    # 6 slots → ≥ 5 intervalos de 50ms = 250ms (con margen)
    assert elapsed >= 0.2, f"esperado ≥0.2s, real {elapsed:.3f}s"
