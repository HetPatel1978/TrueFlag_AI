"""Configure only the application security logger; never enable SQL parameter logging."""

import json
import logging
import math
import re

from app.core.telemetry import METHODS, ROUTES


class SecurityFormatter(logging.Formatter):
    def format(self, record):
        allowed = {
            "request.completed",
            "request.failed",
            "database.operation_failed",
            "worker.completed",
            "worker.failed",
            "telemetry.unavailable",
            "telemetry.recovered",
            "csv.cleanup.unavailable",
        }
        payload = {"event": record.msg if record.msg in allowed else "security.event"}
        ident = getattr(record, "request_id", None)
        if type(ident) is str and re.fullmatch(r"[a-f0-9]{32}", ident):
            payload["request_id"] = ident
        status = getattr(record, "status_code", None)
        if type(status) is int and 100 <= status <= 599:
            payload["status_code"] = status
        method = getattr(record, "method", None)
        if method in METHODS:
            payload["method"] = method
        route = getattr(record, "route_name", None)
        if route in ROUTES:
            payload["route_name"] = route
        error = getattr(record, "error_type", None)
        if type(error) is str and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", error):
            payload["error_type"] = error
        correlation = getattr(record, "correlation_id", None)
        if type(correlation) is str and re.fullmatch(r"[a-f0-9]{32}", correlation):
            payload["correlation_id"] = correlation
        duration = getattr(record, "duration_ms", None)
        if type(duration) in (int, float) and math.isfinite(duration) and 0 <= duration <= 3600000:
            payload["duration_ms"] = round(duration, 3)
        outcome = getattr(record, "outcome", None)
        if outcome in {
            "succeeded",
            "pending",
            "failed",
            "lease_lost",
            "worker_denied",
            "unavailable",
        }:
            payload["outcome"] = outcome
        return json.dumps(payload)


def configure_security_logging():
    logger = logging.getLogger("trueflag.security")
    logger.setLevel(logging.INFO)
    # Respect test/deployment root handlers. A standalone Uvicorn process needs its own handler.
    if not logger.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(SecurityFormatter())
        logger.addHandler(handler)
