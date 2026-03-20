"""
/oracle routes: world-context summary endpoints for external evaluator integration.

These endpoints are NOT intended for agent use during planning. They expose
privileged world information to support LLM-as-judge evaluation at Tier 3:
- What events were available during the trip window?
- What was the optimal hotel for a given budget?
- What did the agent miss?

Agents should never call these endpoints during a session.
"""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from travel_world.api.dependencies import get_active_world_state
from travel_world.layers.geo_layer import GeoLayer
from travel_world.layers.event_layer import EventLayer
from travel_world.layers.accommodation_layer import AccommodationLayer
from travel_world.core.enums import LocationType

router = APIRouter(prefix="/oracle", tags=["oracle"])


@router.get("/trip_window")
def trip_window_summary(
    city_id: str,
    start_date: str,
    end_date: str,
    world_state=Depends(get_active_world_state),
):
    """
    Return a scoped world-context summary for a specific city and date range.

    Intended for Tier 3 LLM-as-judge evaluation. Provides the evaluator
    with full knowledge of what was available during the trip window:
    events, hotel options, attraction categories present, and transit info.

    This endpoint is privileged — agents must not use it during planning.
    """
    geo: GeoLayer = world_state.get_layer("geo")
    city = geo.cities.get(city_id)
    if not city:
        raise HTTPException(status_code=404, detail=f"City '{city_id}' not found")

    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date format. Use YYYY-MM-DD.")

    # Events in window
    events_in_window = []
    try:
        event_layer: EventLayer = world_state.get_layer("event")
        for evt in event_layer.events.values():
            if evt.city_id != city_id:
                continue
            evt_start = date.fromisoformat(evt.start_datetime[:10])
            if start <= evt_start <= end:
                events_in_window.append({
                    "event_id": evt.event_id,
                    "name": evt.name,
                    "category": evt.category.value,
                    "start_datetime": evt.start_datetime,
                    "end_datetime": evt.end_datetime,
                    "base_ticket_price": evt.base_ticket_price,
                    "popularity": evt.popularity,
                })
    except KeyError:
        pass

    # Hotels available
    hotels = []
    try:
        acc_layer: AccommodationLayer = world_state.get_layer("accommodation")
        for hotel_id, slots in acc_layer.availability.items():
            hotel_loc = geo.locations.get(hotel_id)
            if not hotel_loc or hotel_loc.city_id != city_id:
                continue
            # Check if available for at least one night in the window
            available_nights = []
            for d_str, slot in slots.items():
                d = date.fromisoformat(d_str)
                if start <= d <= end and slot.rooms_available > 0:
                    available_nights.append({"date": d_str, "price_tonight": slot.price_tonight, "rooms": slot.rooms_available})
            if available_nights:
                hotels.append({
                    "hotel_id": hotel_id,
                    "name": hotel_loc.name,
                    "star_rating": getattr(hotel_loc, "star_rating", None),
                    "district_id": hotel_loc.district_id,
                    "available_nights": available_nights,
                    "min_price_per_night": min(n["price_tonight"] for n in available_nights),
                })
    except KeyError:
        pass

    # Attraction summary
    attractions_summary = []
    for loc in geo.locations.values():
        if loc.city_id != city_id or loc.location_type != LocationType.ATTRACTION:
            continue
        attractions_summary.append({
            "location_id": loc.location_id,
            "name": loc.name,
            "category": getattr(loc, "category", {}).value if hasattr(getattr(loc, "category", None), "value") else None,
            "ticket_price": getattr(loc, "ticket_price", 0),
            "district_id": loc.district_id,
        })

    return {
        "world_id": world_state.world_id,
        "city_id": city_id,
        "city_name": city.name,
        "city_archetype": getattr(city, "city_archetype", {}).value if hasattr(getattr(city, "city_archetype", None), "value") else None,
        "trip_window": {"start": start_date, "end": end_date},
        "events_in_window": sorted(events_in_window, key=lambda e: e["start_datetime"]),
        "hotels_available": sorted(hotels, key=lambda h: h["min_price_per_night"]),
        "attractions": attractions_summary,
        "dominant_event_categories": city.dominant_event_categories,
        "dominant_cuisines": city.dominant_cuisines,
        "dominant_attraction_categories": getattr(city, "dominant_attraction_categories", []),
    }


@router.get("/flights/cheapest")
def cheapest_flights(
    origin_city_id: str,
    destination_city_id: str,
    world_state=Depends(get_active_world_state),
):
    """Return the cheapest available flight option for a city pair (oracle/evaluator use)."""
    geo: GeoLayer = world_state.get_layer("geo")
    cheapest = None
    for edge in geo.transport_edges.values():
        meta = edge.metadata or {}
        if (
            meta.get("origin_city_id") == origin_city_id
            and meta.get("destination_city_id") == destination_city_id
            and meta.get("is_direct") is True
        ):
            if cheapest is None or edge.base_cost < cheapest["base_cost"]:
                cheapest = {
                    "edge_id": edge.edge_id,
                    "base_cost": edge.base_cost,
                    "departure_time": meta.get("departure_time"),
                    "duration_min": meta.get("duration_min"),
                    "airline": meta.get("airline"),
                    "flight_number": meta.get("flight_number"),
                }
    if cheapest is None:
        raise HTTPException(status_code=404, detail="No direct flights found for this route.")
    return cheapest
