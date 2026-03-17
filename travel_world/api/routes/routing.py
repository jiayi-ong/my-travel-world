"""
/routing routes: multi-modal route planning and comparison.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from travel_world.api.dependencies import get_active_world_state
from travel_world.services.routing_service import RoutingService
from travel_world.core.enums import TransportMode

router = APIRouter(prefix="/routing", tags=["routing"])


@router.get("/plan")
def plan_route(
    origin_location_id: str,
    destination_location_id: str,
    departure_datetime: str,
    modes: str | None = None,
    optimize_for: str = "time",
    session_id: str | None = None,
    world_state=Depends(get_active_world_state),
):
    """Plan routes between two locations. Core tool used by LLM agents."""
    try:
        dt = datetime.fromisoformat(departure_datetime)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid datetime: {departure_datetime}")
    parsed_modes = None
    if modes:
        try:
            parsed_modes = [TransportMode(m.strip().upper()) for m in modes.split(",") if m.strip()]
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"Invalid transport mode: {e}")
    routes = RoutingService(world_state).plan(
        origin_location_id, destination_location_id, dt, parsed_modes, optimize_for
    )
    return {
        "routes": routes,
        "world_id": world_state.world_id,
        "origin_name": origin_location_id,
        "destination_name": destination_location_id,
    }


@router.get("/compare")
def compare_modes(
    origin_location_id: str,
    destination_location_id: str,
    departure_datetime: str,
    world_state=Depends(get_active_world_state),
):
    """Compare all transport modes side-by-side."""
    try:
        dt = datetime.fromisoformat(departure_datetime)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid datetime: {departure_datetime}")
    routes = RoutingService(world_state).compare_modes(origin_location_id, destination_location_id, dt)
    return {"routes": routes, "world_id": world_state.world_id}


@router.get("/time")
def get_travel_time(
    origin_id: str,
    destination_id: str,
    mode: str,
    departure_datetime: str,
    world_state=Depends(get_active_world_state),
):
    """Get travel time for a specific mode and departure time."""
    try:
        dt = datetime.fromisoformat(departure_datetime)
        transport_mode = TransportMode(mode.upper())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return RoutingService(world_state).get_travel_time(origin_id, destination_id, transport_mode, dt)
