"""
Ingestion pipeline latency metrics.

Tracks per-source fetch latency, data freshness, and staleness
to demonstrate latency-aware data ingestion.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from collections import deque

@dataclass
class SourceMetrics:
    source: str
    fetch_count: int = 0
    total_fetch_ms: float = 0.0
    last_fetch_ms: float = 0.0
    last_fetch_at: float = 0.0
    items_ingested: int = 0
    items_rejected_stale: int = 0
    avg_data_age_s: float = 0.0
    _recent_latencies: deque = field(default_factory=lambda: deque(maxlen=50))

    @property
    def avg_fetch_ms(self) -> float:
        return self.total_fetch_ms / self.fetch_count if self.fetch_count else 0

    @property
    def p95_fetch_ms(self) -> float:
        if not self._recent_latencies:
            return 0
        sorted_lats = sorted(self._recent_latencies)
        idx = int(len(sorted_lats) * 0.95)
        return sorted_lats[min(idx, len(sorted_lats) - 1)]

    def record_fetch(self, duration_ms: float, items: int = 0, stale_rejected: int = 0, avg_age_s: float = 0.0) -> None:
        self.fetch_count += 1
        self.total_fetch_ms += duration_ms
        self.last_fetch_ms = duration_ms
        self.last_fetch_at = time.time()
        self.items_ingested += items
        self.items_rejected_stale += stale_rejected
        self.avg_data_age_s = avg_age_s
        self._recent_latencies.append(duration_ms)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "fetch_count": self.fetch_count,
            "avg_fetch_ms": round(self.avg_fetch_ms, 1),
            "p95_fetch_ms": round(self.p95_fetch_ms, 1),
            "last_fetch_ms": round(self.last_fetch_ms, 1),
            "items_ingested": self.items_ingested,
            "stale_rejected": self.items_rejected_stale,
            "avg_data_age_s": round(self.avg_data_age_s, 1),
        }


class IngestionMetrics:
    """Global ingestion metrics tracker. Singleton pattern."""

    def __init__(self) -> None:
        self._sources: dict[str, SourceMetrics] = {}
        self.pipeline_start = time.time()

    def source(self, name: str) -> SourceMetrics:
        if name not in self._sources:
            self._sources[name] = SourceMetrics(source=name)
        return self._sources[name]

    def snapshot(self) -> dict:
        return {
            "uptime_s": round(time.time() - self.pipeline_start, 1),
            "sources": {name: m.to_dict() for name, m in self._sources.items()},
        }


# Module-level singleton
ingestion_metrics = IngestionMetrics()
