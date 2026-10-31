from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import router
from app.core.config import Settings
from app.core.database import make_engine


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or Settings()
    database = engine or make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
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
        return JSONResponse({"detail": "Database operation unavailable"}, status_code=503)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "trueflag-ai", "version": "0.1.0"}

    @app.get("/ready")
    def ready():
        try:
            with database.connect() as connection:
                revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != "0001_foundation":
                raise ValueError("Migration required")
        except (SQLAlchemyError, ValueError):
            return JSONResponse({"status": "not_ready"}, status_code=503)
        return {"status": "ready"}

    app.include_router(router)
    return app
