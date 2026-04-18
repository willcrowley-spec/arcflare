import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.routes import (
    agents,
    chat,
    connections,
    discovery,
    documents,
    metadata,
    organization,
    processes,
    prompts,
    recommendations,
)
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

    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])
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
        origin = request.headers.get("origin", "")
        headers: dict[str, str] = {}
        allowed = settings.cors_origins_list()
        if origin and (origin in allowed or "*" in allowed):
            headers["access-control-allow-origin"] = origin
            headers["access-control-allow-credentials"] = "true"
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
            headers=headers,
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
    app.include_router(discovery.router, prefix=f"{api_prefix}/discovery", tags=["discovery"])
    app.include_router(chat.router, prefix=f"{api_prefix}/chat", tags=["chat"])
    app.include_router(prompts.router, prefix=f"{api_prefix}/prompts", tags=["prompts"])

    return app


app = create_app()
