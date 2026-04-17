"""
Circuit Breaker for scrapers.

Tracks consecutive failures per scraper. When a scraper accumulates
FAILURE_THRESHOLD failures within WINDOW_SECONDS, it is marked as OPEN
(unavailable) for COOLDOWN_SECONDS. After the cooldown, the first request
is allowed through (HALF-OPEN); if it succeeds the circuit closes again.

State lives in-memory — resets on process restart, which is fine behaviour
for a circuit breaker (a restart itself signals the issue may have cleared).
"""

from datetime import datetime, timedelta
from typing import Dict, Optional
import logging
import threading

logger = logging.getLogger(__name__)

# Tunable constants
FAILURE_THRESHOLD = 3      # Consecutive failures before opening
COOLDOWN_SECONDS = 300     # 5 minutes cooldown when open
WINDOW_SECONDS = 120       # Reset counter if no failure in 2 minutes


class _ScraperState:
    def __init__(self):
        self.consecutive_failures: int = 0
        self.open_until: Optional[datetime] = None
        self.last_failure_at: Optional[datetime] = None
        self.total_failures: int = 0
        self.total_successes: int = 0

    @property
    def is_open(self) -> bool:
        if self.open_until is None:
            return False
        return datetime.utcnow() < self.open_until

    @property
    def is_half_open(self) -> bool:
        """True when cooldown has passed — allow one probe request through."""
        if self.open_until is None:
            return False
        return datetime.utcnow() >= self.open_until

    def to_dict(self) -> dict:
        now = datetime.utcnow()
        status = "closed"
        remaining_seconds = None
        if self.open_until:
            if now < self.open_until:
                status = "open"
                remaining_seconds = int((self.open_until - now).total_seconds())
            else:
                status = "half_open"
        return {
            "status": status,
            "consecutive_failures": self.consecutive_failures,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "open_until": self.open_until.isoformat() if self.open_until else None,
            "remaining_cooldown_seconds": remaining_seconds,
            "last_failure_at": self.last_failure_at.isoformat() if self.last_failure_at else None,
        }


class CircuitBreakerRegistry:
    """Thread-safe registry of per-scraper circuit breakers."""

    def __init__(self):
        self._lock = threading.Lock()
        self._scrapers: Dict[str, _ScraperState] = {}

    def _get(self, name: str) -> _ScraperState:
        if name not in self._scrapers:
            self._scrapers[name] = _ScraperState()
        return self._scrapers[name]

    def is_open(self, name: str) -> bool:
        """Returns True if requests to this scraper should be blocked."""
        with self._lock:
            state = self._get(name)
            return state.is_open

    def allow_request(self, name: str) -> bool:
        """
        Returns True if a request should be allowed through.
        Always True when closed; True once when half-open (probe request);
        False when open and still within cooldown.
        """
        with self._lock:
            state = self._get(name)
            if not state.is_open:
                return True
            # Half-open: allow probe but don't reset yet
            if state.is_half_open:
                return True
            return False

    def record_success(self, name: str) -> None:
        with self._lock:
            state = self._get(name)
            state.consecutive_failures = 0
            state.open_until = None
            state.total_successes += 1
            logger.debug(f"CircuitBreaker [{name}]: success recorded, circuit closed")

    def record_failure(self, name: str) -> None:
        with self._lock:
            state = self._get(name)
            now = datetime.utcnow()

            # Reset counter if last failure was long ago (window expired)
            if state.last_failure_at and (now - state.last_failure_at).total_seconds() > WINDOW_SECONDS:
                state.consecutive_failures = 0

            state.consecutive_failures += 1
            state.total_failures += 1
            state.last_failure_at = now

            if state.consecutive_failures >= FAILURE_THRESHOLD:
                state.open_until = now + timedelta(seconds=COOLDOWN_SECONDS)
                logger.warning(
                    f"CircuitBreaker [{name}]: OPEN after {state.consecutive_failures} consecutive failures. "
                    f"Cooldown until {state.open_until.strftime('%H:%M:%S')} UTC"
                )
            else:
                logger.debug(
                    f"CircuitBreaker [{name}]: failure {state.consecutive_failures}/{FAILURE_THRESHOLD}"
                )

    def get_all_statuses(self) -> dict:
        with self._lock:
            return {name: state.to_dict() for name, state in self._scrapers.items()}

    def reset(self, name: str) -> None:
        """Manually reset a circuit breaker (e.g., via admin endpoint)."""
        with self._lock:
            if name in self._scrapers:
                self._scrapers[name] = _ScraperState()
                logger.info(f"CircuitBreaker [{name}]: manually reset")


# Global singleton
_registry = CircuitBreakerRegistry()


def get_circuit_breaker() -> CircuitBreakerRegistry:
    return _registry
