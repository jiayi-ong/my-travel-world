"""
/world routes: world instance management and layer operations.

These endpoints are used by researchers to create, inspect, and modify world instances.
They are not typically called by LLM agents during planning.
"""
from fastapi import APIRouter, Depends, HTTPException, Request

from travel_world.api.dependencies import get_world_manager
from travel_world.core.exceptions import WorldNotFoundError

router = APIRouter(prefix="/world", tags=["world"])


@router.get("/")
def list_worlds(wm=Depends(get_world_manager)):
    """List all available world instances with metadata."""
    return wm.list_worlds()


@router.post("/generate")
def generate_world(
    seed: int,
    world_id: str | None = None,
    request: Request = None,
    wm=Depends(get_world_manager),
):
    """Generate a new world from a seed. Returns world metadata."""
    world_state = wm.create_world(seed=seed, world_id=world_id)
    return {"world_id": world_state.world_id, "seed": seed, "summary": world_state.summary()}


@router.get("/{world_id}")
def get_world(world_id: str, wm=Depends(get_world_manager)):
    """Get metadata and layer summary for a world."""
    try:
        meta = wm._read_meta(world_id)
        world_state = wm.load_world(world_id)
        return {**meta, "layer_summary": world_state.summary()}
    except WorldNotFoundError:
        raise HTTPException(status_code=404, detail=f"World '{world_id}' not found.")


@router.post("/{world_id}/load")
def load_world(world_id: str, request: Request, wm=Depends(get_world_manager)):
    """Set this world as the active world for all subsequent API calls."""
    try:
        world_state = wm.load_world(world_id)
        request.app.state.active_world_state = world_state
        return {"message": f"World '{world_id}' loaded successfully.", "summary": world_state.summary()}
    except WorldNotFoundError:
        raise HTTPException(status_code=404, detail=f"World '{world_id}' not found.")


@router.get("/{world_id}/layers")
def list_layers(world_id: str, wm=Depends(get_world_manager)):
    """List all layers for a world with frozen/unfrozen status."""
    try:
        meta = wm._read_meta(world_id)
        return {"world_id": world_id, "layers": meta.get("layer_ids", []), "meta": meta}
    except WorldNotFoundError:
        raise HTTPException(status_code=404, detail=f"World '{world_id}' not found.")


@router.get("/{world_id}/cities")
def list_cities(world_id: str, wm=Depends(get_world_manager)):
    """List all cities in a world with their IDs and names."""
    try:
        world_state = wm.load_world(world_id)
        geo = world_state.get_layer("geo")
        return [
            {
                "city_id": c.city_id,
                "name": c.name,
                "region_id": c.region_id,
                "travel_advisory": c.travel_advisory,
                "safety_score": c.safety_score,
                "vibe_summary": c.vibe_summary,
                "dominant_cuisines": c.dominant_cuisines,
                "dominant_event_categories": c.dominant_event_categories,
            }
            for c in geo.cities.values()
        ]
    except WorldNotFoundError:
        raise HTTPException(status_code=404, detail=f"World '{world_id}' not found.")


@router.get("/{world_id}/districts")
def list_districts(world_id: str, city_id: str | None = None, wm=Depends(get_world_manager)):
    """List districts for a world, optionally filtered by city. Includes visitor reviews."""
    try:
        world_state = wm.load_world(world_id)
        geo = world_state.get_layer("geo")
        districts = geo.districts.values()
        if city_id:
            districts = [d for d in districts if d.city_id == city_id]
        return [
            {
                "district_id": d.district_id,
                "city_id": d.city_id,
                "name": d.name,
                "district_type": d.district_type.value,
                "safety_score": d.safety_score,
                "walkability_score": d.walkability_score,
                "noise_level": d.noise_level,
                "cost_index": d.cost_index,
                "description": d.description,
                "reviews": [
                    {"reviewer_id": r.reviewer_id, "rating": r.rating,
                     "positivity": r.positivity, "text": r.text,
                     "date": r.date, "tags": r.tags}
                    for r in d.reviews
                ],
            }
            for d in districts
        ]
    except WorldNotFoundError:
        raise HTTPException(status_code=404, detail=f"World '{world_id}' not found.")


@router.get("/{world_id}/map_data")
def get_map_data(world_id: str, wm=Depends(get_world_manager)):
    """Return all geographic data for the interactive map in one call."""
    try:
        from travel_world.core.enums import TransportMode
        world_state = wm.load_world(world_id)
        geo = world_state.get_layer("geo")

        cities = [
            {
                "city_id": c.city_id,
                "name": c.name,
                "lat": c.coordinates.lat,
                "lon": c.coordinates.lon,
                "safety_score": round(c.safety_score, 3),
                "travel_advisory": c.travel_advisory,
                "population": c.population,
                "tourism_density": round(c.tourism_density, 3),
            }
            for c in geo.cities.values()
        ]

        districts = [
            {
                "district_id": d.district_id,
                "city_id": d.city_id,
                "name": d.name,
                "lat": d.coordinates.lat,
                "lon": d.coordinates.lon,
                "district_type": d.district_type.value,
                "safety_score": round(d.safety_score, 3),
                "walkability_score": round(d.walkability_score, 3),
                "cost_index": round(d.cost_index, 3),
                "description": d.description,
            }
            for d in geo.districts.values()
        ]

        locations = []
        for loc in geo.locations.values():
            entry = {
                "location_id": loc.location_id,
                "name": loc.name,
                "location_type": loc.location_type.value,
                "city_id": loc.city_id,
                "district_id": loc.district_id,
                "lat": loc.coordinates.lat,
                "lon": loc.coordinates.lon,
                "description": getattr(loc, "description", ""),
                "average_rating": loc.ratings.average_rating if loc.ratings else None,
                "review_count": loc.ratings.review_count if loc.ratings else 0,
                "popularity_score": getattr(loc, "popularity_score", None),
            }
            ltype = loc.location_type.value
            if ltype == "hotel":
                entry["star_rating"] = getattr(loc, "star_rating", None)
                entry["price_per_night"] = getattr(loc, "price_per_night", None)
            elif ltype == "restaurant":
                entry["cuisine_types"] = getattr(loc, "cuisine_types", [])
                entry["average_spend"] = getattr(loc, "average_spend", None)
                entry["michelin_stars"] = getattr(loc, "michelin_stars", 0)
                entry["reservation_required"] = getattr(loc, "reservation_required", False)
            locations.append(entry)

        seen: set = set()
        flight_routes = []
        for edge in geo.transport_edges.values():
            if edge.mode != TransportMode.FLIGHT:
                continue
            o = geo.locations.get(edge.origin_node_id)
            d = geo.locations.get(edge.destination_node_id)
            if not o or not d:
                continue
            pair = (o.city_id, d.city_id)
            if pair in seen or pair[0] == pair[1]:
                continue
            seen.add(pair)
            flight_routes.append({"origin_city_id": o.city_id, "dest_city_id": d.city_id})

        return {
            "cities": cities,
            "districts": districts,
            "locations": locations,
            "flight_routes": flight_routes,
        }
    except WorldNotFoundError:
        raise HTTPException(status_code=404, detail=f"World '{world_id}' not found.")


@router.post("/{world_id}/layers/{layer_id}/freeze")
def freeze_layer(world_id: str, layer_id: str, wm=Depends(get_world_manager)):
    """Freeze a layer so simulation ticks do not mutate it."""
    try:
        layer = wm._load_layer(world_id, layer_id)
        layer.freeze()
        wm.save_layer(world_id, layer)
        return {"message": f"Layer '{layer_id}' frozen.", "world_id": world_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
