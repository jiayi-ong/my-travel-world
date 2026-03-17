"""FastAPI application factory.

Startup sequence:
    1. Read TRAVEL_WORLD_API_URL and WORLDS_ROOT from environment.
    2. Instantiate WorldManager pointing at WORLDS_ROOT.
    3. Instantiate SessionService (in-memory store).
    4. Register all route modules with their prefixes.
    5. Configure CORS to allow Streamlit frontend and external LLM projects.

Design: Application Factory pattern — create_app() is called by run_api.py
and by test fixtures, keeping the app object creation separate from its execution.
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from travel_world.manager.world_manager import WorldManager
from travel_world.services.session_service import SessionService
from travel_world.api.routes import world, flights, hotels, routing, attractions, events, session


def create_app(worlds_root: str | None = None) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        worlds_root: Override path to worlds directory (used in tests).

    Returns:
        Configured FastAPI app instance, not yet running.
    """
    worlds_path = Path(worlds_root or os.getenv("WORLDS_ROOT", "./worlds"))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        app.state.world_manager = WorldManager(worlds_path)
        app.state.session_service = SessionService()
        app.state.active_world_state = None
        yield
        # Shutdown (nothing to clean up)

    app = FastAPI(
        title="Travel World API",
        version="0.1.0",
        description="Simulated travel world environment for LLM travel-agent research.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(world.router)
    app.include_router(flights.router)
    app.include_router(hotels.router)
    app.include_router(routing.router)
    app.include_router(attractions.router)
    app.include_router(events.router)
    app.include_router(session.router)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.1.0"}

    return app


app = create_app()
