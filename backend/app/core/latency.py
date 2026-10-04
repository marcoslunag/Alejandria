"""
Request latency tracker (roadmap #17)
Registro in-memory de latencias de peticiones API para el panel de logs
(admin). Calcula percentiles (p50/p95/p99) por ventana temporal y los
endpoints más lentos.

Diseño:
- Bounded deque (max_samples) para no crecer sin límite.
- Thread-safe: el middleware FastAPI (async) y los endpoints sync (thread
  pool) pueden registrar simultáneamente.
- No persiste en BD: la telemetría de latencia es efímera (diagnóstico en
  vivo), los logs persistentes ya van a SystemLog.
"""
import threading
import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple


class LatencyTracker:
    def __init__(self, max_samples: int = 5000):
        # (timestamp, route, duration_ms)
        self._samples: Deque[Tuple[float, str, float]] = deque(maxlen=max_samples)
        self._lock = threading.Lock()

    def record(self, route: str, duration_ms: float):
        """Registrar una petición (llamado desde el middleware)."""
        with self._lock:
            self._samples.append((time.time(), route, duration_ms))

    @staticmethod
    def _percentile(values: List[float], pct: float) -> float:
        """Percentil con interpolación lineal (requiere values no vacío)."""
        values = sorted(values)
        k = (len(values) - 1) * (pct / 100)
        f = int(k)
        c = min(f + 1, len(values) - 1)
        if f == c:
            return values[f]
        return values[f] + (values[c] - values[f]) * (k - f)

    def stats(self, window_minutes: int = 60) -> Dict:
        """Percentiles y endpoints más lentos en la ventana dada (minutos)."""
        cutoff = time.time() - window_minutes * 60
        with self._lock:
            samples = [s for s in self._samples if s[0] >= cutoff]

        if not samples:
            return {
                "count": 0,
                "window_minutes": window_minutes,
                "avg_ms": None, "p50_ms": None, "p95_ms": None,
                "p99_ms": None, "max_ms": None,
                "slowest": [],
            }

        durations = [s[2] for s in samples]
        by_route: Dict[str, List[float]] = {}
        for _, route, dur in samples:
            by_route.setdefault(route, []).append(dur)

        slowest = [
            {
                "route": route,
                "count": len(durs),
                "p95_ms": round(self._percentile(durs, 95), 1),
                "max_ms": round(max(durs), 1),
            }
            for route, durs in by_route.items()
        ]
        slowest.sort(key=lambda x: -x["p95_ms"])

        return {
            "count": len(samples),
            "window_minutes": window_minutes,
            "avg_ms": round(sum(durations) / len(durations), 1),
            "p50_ms": round(self._percentile(durations, 50), 1),
            "p95_ms": round(self._percentile(durations, 95), 1),
            "p99_ms": round(self._percentile(durations, 99), 1),
            "max_ms": round(max(durations), 1),
            "slowest": slowest[:10],
        }


_tracker = LatencyTracker()


def get_latency_tracker() -> LatencyTracker:
    return _tracker
