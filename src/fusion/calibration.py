"""
Brier score and calibration tracking.

Measures how well the model's predicted probabilities match actual outcomes.
Brier score = mean((predicted - actual)^2), lower is better.
Perfect = 0.0, random = 0.25, always-0.5 = 0.25.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from collections import deque


@dataclass
class PredictionRecord:
    market_id: str
    predicted_prob: float  # our posterior
    actual_outcome: float | None  # 1.0 = YES, 0.0 = NO, None = unresolved
    timestamp: float = field(default_factory=time.time)
    signal_count: int = 0


class CalibrationTracker:
    """Tracks prediction accuracy via Brier score and calibration buckets."""

    def __init__(self, max_records: int = 1000) -> None:
        self._records: deque[PredictionRecord] = deque(maxlen=max_records)
        self._resolved: list[PredictionRecord] = []

    def record_prediction(self, market_id: str, predicted_prob: float, signal_count: int = 0) -> None:
        self._records.append(PredictionRecord(
            market_id=market_id,
            predicted_prob=predicted_prob,
            actual_outcome=None,
            signal_count=signal_count,
        ))

    def resolve(self, market_id: str, outcome: bool) -> None:
        actual = 1.0 if outcome else 0.0
        for r in self._records:
            if r.market_id == market_id and r.actual_outcome is None:
                r.actual_outcome = actual
                self._resolved.append(r)
                break

    @property
    def brier_score(self) -> float | None:
        if not self._resolved:
            return None
        return sum(
            (r.predicted_prob - r.actual_outcome) ** 2
            for r in self._resolved
        ) / len(self._resolved)

    @property
    def n_resolved(self) -> int:
        return len(self._resolved)

    def calibration_buckets(self, n_buckets: int = 5) -> list[dict]:
        if not self._resolved:
            return []
        bucket_size = 1.0 / n_buckets
        buckets = []
        for i in range(n_buckets):
            lo = i * bucket_size
            hi = (i + 1) * bucket_size
            in_bucket = [r for r in self._resolved if lo <= r.predicted_prob < hi]
            if in_bucket:
                avg_predicted = sum(r.predicted_prob for r in in_bucket) / len(in_bucket)
                avg_actual = sum(r.actual_outcome for r in in_bucket) / len(in_bucket)
            else:
                avg_predicted = (lo + hi) / 2
                avg_actual = 0.0
            buckets.append({
                "bucket": f"{int(lo*100)}-{int(hi*100)}%",
                "predicted": round(avg_predicted, 3),
                "actual": round(avg_actual, 3),
                "n": len(in_bucket),
            })
        return buckets

    def to_dict(self) -> dict:
        return {
            "brier_score": round(self.brier_score, 4) if self.brier_score is not None else None,
            "n_predictions": len(self._records),
            "n_resolved": self.n_resolved,
            "calibration": self.calibration_buckets(),
        }


# Module-level singleton
calibration_tracker = CalibrationTracker()
