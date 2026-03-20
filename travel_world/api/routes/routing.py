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
            parsed_modes = [TransportMode(m.strip().lower()) for m in modes.split(",") if m.strip()]
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


@router.get("/nearby")
def proximity_search(
    lat: float,
    lon: float,
    top_n: int = 10,
    sort_by: str = "distance",
    location_type: str | None = None,
    city_id: str | None = None,
    mode: str = "walking",
    world_state=Depends(get_active_world_state),
):
    """
    Return the top N nearest locations to a coordinate.

    - sort_by: 'distance' (km) or 'travel_time' (minutes estimated from mode speed)
    - mode: transport mode for travel_time estimation (walking, bus, flight, ...)
    - location_type: optional filter (hotel, attraction, restaurant, event_venue, ...)
    - city_id: optional scope to a single city
    """
    results = RoutingService(world_state).proximity_search(
        lat=lat,
        lon=lon,
        top_n=top_n,
        sort_by=sort_by,
        location_type=location_type,
        city_id=city_id,
        mode=mode,
    )
    return {"results": results, "count": len(results)}


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
        transport_mode = TransportMode(mode.lower())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return RoutingService(world_state).get_travel_time(origin_id, destination_id, transport_mode, dt)


@router.get("/arrive_by")
def plan_route_arrive_by(
    origin_location_id: str,
    destination_location_id: str,
    arrival_datetime: str,
    modes: str | None = None,
    optimize_for: str = "time",
    world_state=Depends(get_active_world_state),
):
    """
    Back-calculate required departure time to arrive at a destination by a specified time.

    Useful for planning: 'I need to be at the airport by 14:00 — when should I leave my hotel?'

    Returns routes enriched with required_departure_datetime, estimated_arrival_datetime,
    and buffer_min (slack time before the target arrival).
    """
    try:
        dt = datetime.fromisoformat(arrival_datetime)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid datetime: {arrival_datetime}")
    parsed_modes = None
    if modes:
        try:
            parsed_modes = [TransportMode(m.strip().lower()) for m in modes.split(",") if m.strip()]
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"Invalid transport mode: {e}")
    routes = RoutingService(world_state).plan_arrive_by(
        origin_location_id, destination_location_id, dt, parsed_modes, optimize_for
    )
    return {
        "routes": routes,
        "world_id": world_state.world_id,
        "target_arrival_datetime": arrival_datetime,
    }


@router.get("/nearest_stops")
def nearest_transit_stops(
    lat: float,
    lon: float,
    top_n: int = 5,
    city_id: str | None = None,
    world_state=Depends(get_active_world_state),
):
    """Return the nearest public transit stops to a coordinate, with walking distances."""
    results = RoutingService(world_state).nearest_transit_stops(lat, lon, top_n, city_id)
    return {"stops": results, "count": len(results)}
