from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core.db.base import Base, engine, import_models
from core.exceptions import (
    Conflict,
    InvalidTransition,
    NotFound,
    PluginError,
    RoleViolation,
    WikiError,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure all ORM models are imported before creating tables.
    import_models()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Wolfina Wiki",
        description="LLM-native knowledge system with multi-Agent governance and plugin layer.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # --- Exception handlers ---
    @app.exception_handler(NotFound)
    async def not_found_handler(request: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(Conflict)
    async def conflict_handler(request: Request, exc: Conflict) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(RoleViolation)
    async def role_violation_handler(request: Request, exc: RoleViolation) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(InvalidTransition)
    async def invalid_transition_handler(request: Request, exc: InvalidTransition) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(PluginError)
    async def plugin_error_handler(request: Request, exc: PluginError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(WikiError)
    async def wiki_error_handler(request: Request, exc: WikiError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    # --- Routers ---
    from api.routers.ingest import router as ingest_router
    from api.routers.pages import router as pages_router
    from api.routers.plugins import events_router, router as plugins_router
    from api.routers.proposals import router as proposals_router

    app.include_router(ingest_router)
    app.include_router(pages_router)
    app.include_router(proposals_router)
    app.include_router(plugins_router)
    app.include_router(events_router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
