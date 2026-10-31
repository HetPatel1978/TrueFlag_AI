"""Configure only the application security logger; never enable SQL parameter logging."""

import json
import logging


class SecurityFormatter(logging.Formatter):
    def format(self, record):
        allowed = {"request.completed", "request.failed", "database.operation_failed"}
        payload = {"event": record.msg if record.msg in allowed else "security.event"}
        for field in ["request_id", "status_code", "method", "route_name", "error_type"]:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload)


def configure_security_logging():
    logger = logging.getLogger("trueflag.security")
    logger.setLevel(logging.INFO)
    # Respect test/deployment root handlers. A standalone Uvicorn process needs its own handler.
    if not logger.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(SecurityFormatter())
        logger.addHandler(handler)
