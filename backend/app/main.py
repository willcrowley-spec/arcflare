import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import agents, connections, documents, metadata, organization, processes, recommendations
from app.core.config import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Starting Arcflare API (environment=%s)", settings.ENVIRONMENT)
    yield
    logger.info("Shutting down Arcflare API")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Arcflare API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.ENVIRONMENT}

    api_prefix = "/api/v1"
    app.include_router(connections.router, prefix=f"{api_prefix}/connections", tags=["connections"])
    app.include_router(metadata.router, prefix=f"{api_prefix}/metadata", tags=["metadata"])
    app.include_router(documents.router, prefix=f"{api_prefix}/documents", tags=["documents"])
    app.include_router(processes.router, prefix=f"{api_prefix}/processes", tags=["processes"])
    app.include_router(
        recommendations.router, prefix=f"{api_prefix}/recommendations", tags=["recommendations"]
    )
    app.include_router(
        organization.router, prefix=f"{api_prefix}/organization", tags=["organization"]
    )
    app.include_router(agents.router, prefix=f"{api_prefix}/agents", tags=["agents"])

    return app


app = create_app()
