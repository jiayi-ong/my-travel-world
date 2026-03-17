"""
/events routes: search, calendar view, and ticket booking.
"""
from fastapi import APIRouter, Depends, HTTPException
from travel_world.api.dependencies import get_active_world_state, get_session_service
from travel_world.services.event_service import EventService
from travel_world.core.enums import EventCategory
from travel_world.core.exceptions import FeasibilityViolationError, EntityNotFoundError

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/search")
def search_events(
    city_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    category: str | None = None,
    max_price: float | None = None,
    session_id: str | None = None,
    world_state=Depends(get_active_world_state),
    session_svc=Depends(get_session_service),
):
    cat = EventCategory(category.lower()) if category else None
    results = EventService(world_state).search(city_id, start_date, end_date, cat, max_price, session_id)
    if session_id:
        session_svc.log_interaction(session_id, "/events/search", {"city": city_id}, 200)
    return results


@router.get("/calendar")
def get_calendar(city_id: str, year: int, month: int, world_state=Depends(get_active_world_state)):
    return EventService(world_state).get_calendar(city_id, year, month)


@router.get("/{event_id}")
def get_event(event_id: str, world_state=Depends(get_active_world_state)):
    try:
        return EventService(world_state).get_detail(event_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/book")
def book_ticket(
    event_id: str,
    quantity: int = 1,
    session_id: str = "",
    world_state=Depends(get_active_world_state),
    session_svc=Depends(get_session_service),
):
    try:
        result = EventService(world_state).book_ticket(event_id, quantity, session_id)
        if session_id:
            session_svc.add_trip_item(session_id, {
                "item_type": "event",
                "ref_id": event_id,
                "date": result.get("start_datetime", "")[:10],
                "cost": result.get("total_cost", 0),
                "metadata": result,
            })
        return result
    except FeasibilityViolationError as e:
        raise HTTPException(status_code=409, detail={"message": str(e), "violations": e.violations})
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
