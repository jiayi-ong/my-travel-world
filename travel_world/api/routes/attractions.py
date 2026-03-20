"""
/attractions routes: lookup, filtering, and crowding.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from travel_world.api.dependencies import get_active_world_state
from travel_world.services.attraction_service import AttractionService
from travel_world.core.enums import AttractionCategory
from travel_world.core.exceptions import EntityNotFoundError

router = APIRouter(prefix="/attractions", tags=["attractions"])


@router.get("/search")
def search_attractions(
    city_id: str,
    category: str | None = None,
    district_id: str | None = None,
    max_ticket_price: float | None = None,
    free_only: bool = False,
    world_state=Depends(get_active_world_state),
):
    cat = AttractionCategory(category.upper()) if category else None
    return AttractionService(world_state).search(city_id, cat, district_id, max_ticket_price, free_only)


@router.get("/nearby")
def get_nearby(
    location_id: str,
    radius_km: float = 1.0,
    location_types: str | None = None,
    world_state=Depends(get_active_world_state),
):
    types = [t.strip() for t in location_types.split(",")] if location_types else None
    return AttractionService(world_state).get_nearby(location_id, radius_km, types)


@router.get("/{attraction_id}")
def get_attraction(attraction_id: str, world_state=Depends(get_active_world_state)):
    try:
        return AttractionService(world_state).get_detail(attraction_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{attraction_id}/crowding")
def get_crowding(attraction_id: str, visit_datetime: str, world_state=Depends(get_active_world_state)):
    try:
        dt = datetime.fromisoformat(visit_datetime)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid datetime: {visit_datetime}")
    try:
        return AttractionService(world_state).get_crowding(attraction_id, dt)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{attraction_id}/entrances")
def get_area_entrances(
    attraction_id: str,
    world_state=Depends(get_active_world_state),
):
    """
    Return the named entrance/exit points for an AreaAttraction.

    Agents should use entrance coordinates (not the centroid) as routing
    targets when navigating to large parks or area attractions.

    Returns 404 if the attraction is not an AreaAttraction.
    """
    geo = world_state.get_layer("geo")
    loc = geo.locations.get(attraction_id)
    if loc is None:
        raise HTTPException(status_code=404, detail=f"Attraction '{attraction_id}' not found")
    if not hasattr(loc, "entrances"):
        raise HTTPException(status_code=404, detail=f"'{attraction_id}' is not an area attraction and has no entrances")
    return {
        "attraction_id": attraction_id,
        "name": loc.name,
        "entrances": [e.model_dump() for e in loc.entrances],
        "sub_areas": getattr(loc, "sub_areas", []),
        "area_sqkm": getattr(loc, "area_sqkm", None),
        "boundary_polygon": [c.model_dump() for c in getattr(loc, "boundary_polygon", [])],
    }
