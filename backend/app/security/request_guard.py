"""Bound request bodies and correlate logs without retaining body/header/customer values."""

import logging
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

logger = logging.getLogger("trueflag.security")


class RequestGuardMiddleware:
    def __init__(self, app, max_request_bytes: int):
        self.app = app
        self.limit = max_request_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        ident = uuid4().hex
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
            declared = Headers(scope=scope).get("content-length")
            if declared is not None:
                try:
                    size = int(declared)
                except ValueError:
                    return await reject(400, "Invalid content length")
                if size < 0:
                    return await reject(400, "Invalid content length")
                if size > self.limit:
                    return await reject(413, "Request body exceeds configured limit")
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
            logger.info(
                "request.completed",
                extra={
                    "request_id": ident,
                    "status_code": status,
                    "method": method
                    if method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
                    else "OTHER",
                    "route_name": getattr(route, "name", "unmatched"),
                },
            )
