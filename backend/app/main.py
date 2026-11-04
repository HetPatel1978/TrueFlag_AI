import logging
from contextlib import asynccontextmanager
from threading import BoundedSemaphore

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.api.alerts import router as alerts_router
from app.api.assessments import router as assessments_router
from app.api.batch_assessments import router as batch_assessments_router
from app.api.cases import router as cases_router
from app.api.csv_imports import router as csv_imports_router
from app.api.csv_uploads import router as csv_uploads_router
from app.api.evidence import router as evidence_router
from app.api.monitoring import router as monitoring_router
from app.api.references import router as references_router
from app.api.routes import router
from app.core.config import Settings
from app.core.database import make_engine
from app.core.schema import EXPECTED_SCHEMA_REVISION
from app.core.telemetry import Registry
from app.security.logging import configure_security_logging
from app.security.request_guard import RequestGuardMiddleware
from app.services.batch_assessments import BatchAssessmentService, BatchDispatcher
from app.services.csv_staging import CSVRetention, CSVStagingService
from app.services.monitoring import MetricFlusher


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    configure_security_logging()
    settings = settings or Settings()
    database = engine or make_engine(settings.database_url)
    telemetry = Registry()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        exporter = MetricFlusher(database, telemetry).start()
        retention = CSVRetention(
            CSVStagingService(database, settings), settings.csv_cleanup_interval_seconds
        ).start()
        dispatcher = (
            BatchDispatcher(BatchAssessmentService(database, settings, telemetry)).start()
            if settings.batch_assessment_dispatch_enabled
            else None
        )
        try:
            yield
        finally:
            if dispatcher:
                dispatcher.close()
            retention.close()
            exporter.close()
        if engine is None:
            database.dispose()

    app = FastAPI(
        title="TrueFlag AI",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.app_env == "local" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.app_env == "local" else None,
    )
    app.state.settings = settings
    app.state.engine = database
    app.state.telemetry = telemetry
    app.state.csv_upload_slots = BoundedSemaphore(settings.csv_max_concurrent_uploads)
    app.state.csv_validation_slots = BoundedSemaphore(settings.csv_max_concurrent_validations)
    app.state.evidence_read_slots = BoundedSemaphore(4)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        expose_headers=["X-Request-ID", "Location", "Retry-After"],
    )
    app.add_middleware(
        RequestGuardMiddleware,
        max_request_bytes=settings.max_request_bytes,
        telemetry=telemetry,
        csv_max_bytes=settings.csv_max_bytes,
    )

    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(SQLAlchemyError)
    async def unavailable(request: Request, error: SQLAlchemyError):
        logging.getLogger("trueflag.security").warning(
            "database.operation_failed",
            extra={
                "request_id": getattr(request.state, "request_id", None),
                "error_type": type(error).__name__,
            },
        )
        return JSONResponse({"detail": "Database operation unavailable"}, status_code=503)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError):
        # Do not reflect submitted feature values, credentials or non-finite JSON into errors.
        detail = [
            {"type": item["type"], "loc": item["loc"], "msg": item["msg"]}
            for item in error.errors()
        ]
        return JSONResponse({"detail": detail}, status_code=422)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "trueflag-ai", "version": "0.1.0"}

    @app.get("/ready")
    def ready():
        try:
            with database.connect() as connection:
                revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != EXPECTED_SCHEMA_REVISION:
                raise ValueError("Migration required")
        except (SQLAlchemyError, ValueError):
            return JSONResponse({"status": "not_ready"}, status_code=503)
        return {"status": "ready"}

    app.include_router(router)
    app.include_router(alerts_router)
    app.include_router(cases_router)
    app.include_router(assessments_router)
    app.include_router(batch_assessments_router)
    app.include_router(monitoring_router)
    app.include_router(csv_uploads_router)
    app.include_router(csv_imports_router)
    app.include_router(evidence_router)
    app.include_router(references_router)
    return app
