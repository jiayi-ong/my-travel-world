"""FastAPI dependency injection functions.

All route handlers receive their dependencies via these functions,
ensuring consistent access to shared services and world state.
"""
from fastapi import Request, HTTPException

from travel_world.manager.world_manager import WorldManager
from travel_world.core.world_state import WorldState
from travel_world.services.session_service import SessionService, UserSession
from travel_world.core.exceptions import SessionNotFoundError


def get_world_manager(request: Request) -> WorldManager:
    """Retrieve WorldManager from app state."""
    return request.app.state.world_manager


def get_active_world_state(request: Request) -> WorldState:
    """
    Retrieve the currently active WorldState from app state.
    Raises HTTP 503 if no world is loaded.
    """
    ws = getattr(request.app.state, "active_world_state", None)
    if ws is None:
        raise HTTPException(
            status_code=503,
            detail="No world loaded. POST to /world/{world_id}/load first.",
        )
    return ws


def get_session_service(request: Request) -> SessionService:
    """Retrieve SessionService from app state."""
    return request.app.state.session_service


def get_session(session_id: str, request: Request) -> UserSession:
    """
    Retrieve a specific UserSession by ID.
    Raises HTTP 404 if session not found.
    """
    svc: SessionService = request.app.state.session_service
    try:
        return svc.get_session(session_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
