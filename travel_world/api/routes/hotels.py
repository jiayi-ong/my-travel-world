"""
/hotels routes: search, availability, and booking.
"""
from fastapi import APIRouter, Depends, HTTPException

from travel_world.api.dependencies import get_active_world_state, get_session_service
from travel_world.services.hotel_service import HotelService
from travel_world.core.exceptions import EntityNotFoundError, FeasibilityViolationError

router = APIRouter(prefix="/hotels", tags=["hotels"])


@router.get("/search")
def search_hotels(
    city_id: str,
    check_in: str,
    check_out: str,
    guests: int = 1,
    max_price_per_night: float | None = None,
    min_stars: int | None = None,
    required_amenities: str | None = None,
    session_id: str | None = None,
    world_state=Depends(get_active_world_state),
    session_svc=Depends(get_session_service),
):
    """Search available hotels. Core tool used by LLM agents."""
    amenities = required_amenities.split(",") if required_amenities else None
    svc = HotelService(world_state)
    results = svc.search(city_id, check_in, check_out, guests, max_price_per_night, min_stars, amenities, session_id)
    if session_id:
        session_svc.log_interaction(session_id, "/hotels/search", {"city": city_id}, 200)
    return {"hotels": results, "world_id": world_state.world_id, "total_results": len(results)}


@router.get("/compare")
def compare_hotels(
    hotel_ids: str,
    check_in: str,
    check_out: str,
    world_state=Depends(get_active_world_state),
):
    """Compare multiple hotels side-by-side. hotel_ids is comma-separated."""
    ids = [h.strip() for h in hotel_ids.split(",")]
    svc = HotelService(world_state)
    return svc.compare(ids, check_in, check_out)


@router.get("/{hotel_id}")
def get_hotel(hotel_id: str, world_state=Depends(get_active_world_state)):
    """Get full details for a specific hotel."""
    try:
        return HotelService(world_state).get_hotel_detail(hotel_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{hotel_id}/availability")
def get_availability(
    hotel_id: str,
    check_in: str,
    check_out: str,
    world_state=Depends(get_active_world_state),
):
    """Get availability calendar for a hotel over a date range."""
    return HotelService(world_state).get_availability_calendar(hotel_id, check_in, check_out)


@router.post("/{hotel_id}/book")
def book_hotel(
    hotel_id: str,
    check_in: str,
    check_out: str,
    session_id: str,
    world_state=Depends(get_active_world_state),
    session_svc=Depends(get_session_service),
):
    """Book a hotel room and add it to the session trip plan."""
    try:
        result = HotelService(world_state).book(hotel_id, check_in, check_out, session_id)
        session_svc.add_trip_item(
            session_id,
            {
                "item_type": "hotel",
                "ref_id": hotel_id,
                "date": check_in,
                "cost": result.get("total_cost", 0),
                "metadata": result,
            },
        )
        return result
    except FeasibilityViolationError as e:
        raise HTTPException(status_code=409, detail={"message": str(e), "violations": e.violations})
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
