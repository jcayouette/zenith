from __future__ import annotations

from threading import Lock
from time import monotonic, time
from typing import Any


def eta_seconds(*, developed: int, remaining: int, elapsed: float) -> float | None:
    """Seconds left from frames actually demosaiced this run (skips do not count)."""
    if developed < 2 or remaining <= 0 or elapsed <= 0:
        return None
    return remaining * (elapsed / developed)


class EncodeTracker:
    def __init__(self) -> None:
        self._lock = Lock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def start(self, key: str, *, kind: str, date: str) -> None:
        with self._lock:
            self._jobs[key] = {
                "kind": kind,
                "date": date,
                "phase": "queued",
                "label": "Starting…",
                "total": 0,
                "done": 0,
                "developed": 0,
                "skipped": 0,
                "started_at": time(),
                "eta_seconds": None,
                "percent": 0.0,
                "error": None,
                "_develop_t0": None,
            }

    def active(self, key: str) -> bool:
        with self._lock:
            job = self._jobs.get(key)
            return job is not None and job["phase"] in {"queued", "developing", "encoding"}

    def snapshot(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(key)
            if job is None:
                return None
            return {k: v for k, v in job.items() if not k.startswith("_")}

    def tick(
        self,
        key: str,
        *,
        done: int,
        total: int,
        developed: int,
        skipped: int,
        label: str = "Developing RAW frames",
    ) -> None:
        with self._lock:
            job = self._jobs.get(key)
            if job is None:
                return
            job["phase"] = "developing"
            job["label"] = label
            job["done"] = done
            job["total"] = total
            job["developed"] = developed
            job["skipped"] = skipped
            if developed > 0 and job["_develop_t0"] is None:
                job["_develop_t0"] = monotonic()
            elapsed = 0.0
            if job["_develop_t0"] is not None:
                elapsed = monotonic() - job["_develop_t0"]
            remaining = max(0, total - done)
            job["eta_seconds"] = eta_seconds(
                developed=developed, remaining=remaining, elapsed=elapsed
            )
            job["percent"] = 0.0 if total <= 0 else min(99.0, 100.0 * done / total)

    def phase(self, key: str, phase: str, *, label: str | None = None) -> None:
        with self._lock:
            job = self._jobs.get(key)
            if job is None:
                return
            job["phase"] = phase
            if label:
                job["label"] = label
            if phase == "encoding":
                job["percent"] = max(float(job["percent"]), 99.0)
                job["eta_seconds"] = None
                if job["total"]:
                    job["done"] = job["total"]
            if phase in {"done", "error"}:
                job["percent"] = 100.0
                job["eta_seconds"] = 0.0

    def fail(self, key: str, message: str) -> None:
        self.phase(key, "error", label="Encode failed")
        with self._lock:
            job = self._jobs.get(key)
            if job is not None:
                job["error"] = message

    def finish(self, key: str) -> None:
        with self._lock:
            job = self._jobs.get(key)
            if job is None:
                return
            if job["phase"] not in {"error", "done"}:
                job["phase"] = "done"
                job["label"] = "Done"
                job["percent"] = 100.0
                job["eta_seconds"] = 0.0
                if job["total"]:
                    job["done"] = job["total"]


tracker = EncodeTracker()
