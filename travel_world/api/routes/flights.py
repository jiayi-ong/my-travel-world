"""
/flights routes: search and retrieve flight information.
"""
from fastapi import APIRouter, Depends, HTTPException

from travel_world.api.dependencies import get_active_world_state, get_session_service
from travel_world.api.schemas.flights import FlightSearchResponse
from travel_world.services.flight_service import FlightService
from travel_world.core.exceptions import EntityNotFoundError

router = APIRouter(prefix="/flights", tags=["flights"])


@router.get("/search", response_model=FlightSearchResponse)
def search_flights(
    origin_city_id: str,
    destination_city_id: str,
    departure_date: str,
    passengers: int = 1,
    cabin_class: str | None = None,
    session_id: str | None = None,
    world_state=Depends(get_active_world_state),
    session_svc=Depends(get_session_service),
):
    """Search available flights. Core tool used by LLM agents."""
    try:
        svc = FlightService(world_state)
        results = svc.search(
            origin_city_id, destination_city_id, departure_date, passengers, cabin_class, session_id
        )
        if session_id:
            session_svc.log_interaction(
                session_id,
                "/flights/search",
                {"origin": origin_city_id, "destination": destination_city_id, "date": departure_date},
                200,
            )
        return {
            "flights": results,
            "world_id": world_state.world_id,
            "search_date": departure_date,
            "total_results": len(results),
        }
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/routes")
def get_routes(world_state=Depends(get_active_world_state)):
    """List all available flight routes in the world."""
    svc = FlightService(world_state)
    return svc.get_available_routes()


@router.get("/{flight_id}")
def get_flight(flight_id: str, world_state=Depends(get_active_world_state)):
    """Get full details for a specific flight."""
    try:
        svc = FlightService(world_state)
        return svc.get_flight_detail(flight_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
