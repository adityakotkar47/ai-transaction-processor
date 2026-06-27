import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import _async_engine
from app.core.logging_config import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
    logger.info("Upload directory ready at %s", settings.UPLOADS_DIR)
    yield
    await _async_engine.dispose()
    logger.info("DB engine disposed.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Transaction Processor",
        description=(
            "Async CSV ingestion pipeline with anomaly detection and LLM-powered "
            "categorisation. Single `docker compose up` to start."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from app.api.v1.routes import jobs  # noqa: PLC0415

    app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok", "env": settings.APP_ENV}

    return app


app = create_app()
