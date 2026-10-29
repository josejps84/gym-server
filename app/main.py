import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import Settings
from app.container import Container, build_container
from app.dependencies import ContainerDep
from app.domain.errors import Conflict, DomainError, Forbidden, Invalid, NotFound
from app.routers import feed, me, pages, routines, sync, users, workouts
from app.routers.schemas import Health
from app.services.ports import UpstreamError

log = logging.getLogger(__name__)

_STATUS_OF: dict[type[DomainError], int] = {
    NotFound: status.HTTP_404_NOT_FOUND,
    Forbidden: status.HTTP_403_FORBIDDEN,
    Conflict: status.HTTP_409_CONFLICT,
    Invalid: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def create_app(container: Container | None = None) -> FastAPI:
    """`uvicorn --factory app.main:create_app`; tests pass a container with fakes."""
    container = container or build_container(Settings())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await container.close()

    app = FastAPI(title="Giimme server", version="0.1.0", lifespan=lifespan)
    app.state.container = container

    app.add_middleware(
        CORSMiddleware,
        allow_origins=container.settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=3600,
    )

    @app.middleware("http")
    async def limit_body_size(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > container.settings.max_body_bytes:
            return JSONResponse({"error": "body.tooLarge", "message": "Request body too large"}, 413)
        return await call_next(request)

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, error: DomainError) -> JSONResponse:
        code = next((s for t, s in _STATUS_OF.items() if isinstance(error, t)), status.HTTP_400_BAD_REQUEST)
        return JSONResponse({"error": error.code, "message": error.message}, code)

    @app.exception_handler(UpstreamError)
    async def upstream_error(_: Request, error: UpstreamError) -> JSONResponse:
        log.error("Upstream failure: %s", error, exc_info=error)
        return JSONResponse({"error": "upstream", "message": "Try again later"}, status.HTTP_502_BAD_GATEWAY)

    @app.get("/health", tags=["health"])
    async def health(c: ContainerDep) -> Health:
        """Also touches the database, so the keep-alive job stops Supabase from pausing it."""
        async with c.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return Health(status="ok")

    for module in (me, sync, users, routines, feed, workouts, pages):
        app.include_router(module.router)
    return app
