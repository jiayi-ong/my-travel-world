"""
/restaurants routes: search and detail.
"""
from fastapi import APIRouter, Depends, HTTPException
from travel_world.api.dependencies import get_active_world_state
from travel_world.services.restaurant_service import RestaurantService
from travel_world.core.exceptions import EntityNotFoundError

router = APIRouter(prefix="/restaurants", tags=["restaurants"])


@router.get("/search")
def search_restaurants(
    city_id: str,
    cuisine: str | None = None,
    max_avg_spend: float | None = None,
    reservation_required: bool | None = None,
    district_id: str | None = None,
    session_id: str | None = None,
    world_state=Depends(get_active_world_state),
):
    """Search restaurants in a city with optional filters."""
    results = RestaurantService(world_state).search(
        city_id, cuisine, max_avg_spend, reservation_required, district_id, session_id
    )
    return {"restaurants": results, "total_results": len(results)}


@router.get("/{restaurant_id}")
def get_restaurant(restaurant_id: str, world_state=Depends(get_active_world_state)):
    """Get full details for a specific restaurant including reviews."""
    try:
        return RestaurantService(world_state).get_detail(restaurant_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
