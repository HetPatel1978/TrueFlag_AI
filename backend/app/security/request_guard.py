"""Bound request bodies and correlate logs without retaining body/header/customer values."""

import logging
import time
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

from app.core.telemetry import METHODS, ROUTES, status_label

logger = logging.getLogger("trueflag.security")


class RequestGuardMiddleware:
    def __init__(self, app, max_request_bytes: int, telemetry=None, csv_max_bytes=None):
        self.app = app
        self.limit = max_request_bytes
        self.telemetry = telemetry
        self.csv_max_bytes = csv_max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        ident = uuid4().hex
        begin = time.monotonic()
        scope.setdefault("state", {})["request_id"] = ident
        status = 500
        started = False

        async def guarded_send(message):
            nonlocal status, started
            if message["type"] == "http.response.start":
                status = message["status"]
                started = True
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = ident
                headers["Cache-Control"] = "no-store"
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "no-referrer"
            await send(message)

        async def reject(code, detail):
            await JSONResponse({"detail": detail}, status_code=code)(scope, receive, guarded_send)

        try:
            csv_stream = (
                self.csv_max_bytes is not None
                and scope.get("path") == "/api/v1/batch-uploads"
                and scope.get("method") == "POST"
            )
            limit = self.csv_max_bytes if csv_stream else self.limit
            declared = Headers(scope=scope).get("content-length")
            if declared is not None:
                try:
                    size = int(declared)
                except ValueError:
                    return await reject(400, "Invalid content length")
                if size < 0:
                    return await reject(400, "Invalid content length")
                if size > limit:
                    return await reject(413, "Request body exceeds configured limit")
            if csv_stream:
                # This single route authenticates before consuming bytes and counts every chunk
                # into a private bounded spool. All existing JSON routes retain their original cap.
                return await self.app(scope, receive, guarded_send)
            chunks = []
            size = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    status = 499
                    return
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > self.limit:
                    return await reject(413, "Request body exceeds configured limit")
                chunks.append(chunk)
                if not message.get("more_body", False):
                    break
            delivered = False

            async def buffered_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
                return await receive()

            await self.app(scope, buffered_receive, guarded_send)
        except Exception as error:
            logger.error(
                "request.failed", extra={"request_id": ident, "error_type": type(error).__name__}
            )
            if started:
                raise
            await reject(500, "Request could not be completed")
        finally:
            route = scope.get("route")
            method = scope.get("method")
            method = method if method in METHODS else "OTHER"
            name = getattr(route, "name", "unmatched")
            name = name if name in ROUTES else "unmatched"
            elapsed = (time.monotonic() - begin) * 1000
            if self.telemetry is not None:
                self.telemetry.observe(
                    "api.request", f"{name}|{method}|{status_label(status)}", elapsed
                )
            logger.info(
                "request.completed",
                extra={
                    "request_id": ident,
                    "status_code": status,
                    "method": method,
                    "route_name": name,
                    "duration_ms": elapsed,
                },
            )
