"""Bounded, nonblocking, value-free histograms. No database or scientific dependencies."""

import bisect
import math
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from uuid import uuid4

BOUNDS_MS = (
    1,
    2,
    5,
    10,
    20,
    50,
    100,
    200,
    500,
    1000,
    2000,
    5000,
    10000,
    30000,
    60000,
    120000,
    300000,
    600000,
)
ROUTES = frozenset(
    {
        "health",
        "ready",
        "login",
        "me",
        "audit_events",
        "ingest",
        "case_list",
        "case_detail",
        "case_overview",
        "csv_upload_template",
        "csv_upload_contract",
        "csv_upload",
        "csv_upload_metadata",
        "case_assignment",
        "request_assessment",
        "assessment_job",
        "assessment_history",
        "assessment_detail",
        "operational_metrics",
        "unmatched",
    }
)
METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "OTHER"})
STATUS = frozenset(
    {"2xx", "401", "403", "404", "409", "422", "429", "503", "other4xx", "other5xx", "other"}
)
METRICS = frozenset(
    {
        "api.request",
        "worker.execution",
        "worker.recovery_scan",
        "worker.recovered",
        "model.initialization",
        "model.scoring",
        "model.shap",
        "api.queue_saturation",
        "api.queue_contention",
    }
)
OUTCOMES = frozenset(
    {
        "ok",
        "observed",
        "succeeded",
        "pending",
        "failed",
        "lease_lost",
        "worker_denied",
        "unavailable",
    }
)
_stages = ContextVar("operational_stage_timings", default=None)


def valid_label(name, label):
    if name == "api.request":
        parts = label.split("|")
        return len(parts) == 3 and parts[0] in ROUTES and parts[1] in METHODS and parts[2] in STATUS
    return name in METRICS and label in OUTCOMES


def status_label(code):
    if code in {401, 403, 404, 409, 422, 429, 503}:
        return str(code)
    return (
        "2xx"
        if 200 <= code < 300
        else "other4xx"
        if 400 <= code < 500
        else "other5xx"
        if 500 <= code < 600
        else "other"
    )


class Registry:
    def __init__(self, clock=None):
        self.instance_id = uuid4()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()
        self._data = {}
        self.dropped = 0

    def observe(self, name, label="ok", milliseconds=0.0, count=1):
        if (
            type(name) is not str
            or type(label) is not str
            or not valid_label(name, label)
            or type(milliseconds) not in (int, float)
            or not math.isfinite(milliseconds)
            or milliseconds < 0
            or milliseconds > 3600000
            or type(count) is not int
            or not 1 <= count <= 10000
        ):
            return
        minute = self.clock().astimezone(timezone.utc).replace(second=0, microsecond=0)
        with self._lock:
            keep = {minute, minute - timedelta(minutes=1)}
            self._data = {key: value for key, value in self._data.items() if key[0] in keep}
            if minute not in keep:
                self.dropped += count
                return
            key = (minute, name, label)
            if key not in self._data:
                if sum(k[0] == minute for k in self._data) >= 256:
                    self.dropped += count
                    return
                self._data[key] = [0, 0.0, [0] * (len(BOUNDS_MS) + 1)]
            row = self._data[key]
            row[0] += count
            row[1] += float(milliseconds) * count
            row[2][bisect.bisect_left(BOUNDS_MS, milliseconds)] += count

    def snapshot(self):
        with self._lock:
            return [
                {
                    "instance_id": self.instance_id,
                    "minute": key[0],
                    "name": key[1],
                    "label": key[2],
                    "count": value[0],
                    "total_ms": value[1],
                    "buckets": list(value[2]),
                }
                for key, value in self._data.items()
            ]


def histogram(count, total, buckets):
    result = {"count": count, "mean_ms": total / count if count else None}
    for q in (50, 95, 99):
        target = max(1, math.ceil(count * q / 100))
        cumulative = 0
        bound = None
        for i, amount in enumerate(buckets):
            cumulative += amount
            if cumulative >= target:
                bound = BOUNDS_MS[i] if i < len(BOUNDS_MS) else None
                break
        result[f"p{q}_upper_bound_ms"] = bound if count else None
    return result


@contextmanager
def capture_stages():
    timings = {}
    token = _stages.set(timings)
    try:
        yield timings
    finally:
        _stages.reset(token)


@contextmanager
def stage(name):
    start = time.monotonic()
    try:
        yield
    finally:
        target = _stages.get()
        if target is not None and name in {"model.initialization", "model.scoring", "model.shap"}:
            target[name] = (time.monotonic() - start) * 1000
