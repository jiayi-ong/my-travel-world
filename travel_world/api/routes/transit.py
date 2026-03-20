"""
/transit routes: public transit network queries.
"""
from fastapi import APIRouter, Depends, HTTPException
from travel_world.api.dependencies import get_active_world_state
from travel_world.layers.geo_layer import GeoLayer
from travel_world.core.enums import LocationType

router = APIRouter(prefix="/transit", tags=["transit"])


@router.get("/lines")
def list_transit_lines(
    city_id: str | None = None,
    world_state=Depends(get_active_world_state),
):
    """List all transit lines, optionally filtered by city."""
    geo: GeoLayer = world_state.get_layer("geo")
    lines = list(geo.transit_lines.values())
    if city_id:
        lines = [l for l in lines if l.city_id == city_id]
    return {
        "lines": [l.model_dump() for l in lines],
        "count": len(lines),
    }


@router.get("/lines/{line_id}")
def get_transit_line(
    line_id: str,
    world_state=Depends(get_active_world_state),
):
    """Get a transit line with its ordered stop details."""
    geo: GeoLayer = world_state.get_layer("geo")
    line = geo.transit_lines.get(line_id)
    if not line:
        raise HTTPException(status_code=404, detail=f"Transit line '{line_id}' not found")
    stops = []
    for stop_id in line.stop_ids:
        loc = geo.locations.get(stop_id)
        if loc:
            stops.append({
                "stop_id": stop_id,
                "name": loc.name,
                "coordinates": loc.coordinates.model_dump(),
                "is_interchange": getattr(loc, "is_interchange", False),
                "accessible": getattr(loc, "accessible", True),
            })
    return {
        "line": line.model_dump(),
        "stops": stops,
    }


@router.get("/stops")
def list_transit_stops(
    city_id: str | None = None,
    world_state=Depends(get_active_world_state),
):
    """List all transit stops in the world or a specific city."""
    geo: GeoLayer = world_state.get_layer("geo")
    stops = geo.get_transit_stops(city_id)
    return {
        "stops": [s.model_dump() for s in stops],
        "count": len(stops),
    }


@router.get("/stops/{stop_id}/lines")
def get_stop_lines(
    stop_id: str,
    world_state=Depends(get_active_world_state),
):
    """Get all transit lines serving a specific stop."""
    geo: GeoLayer = world_state.get_layer("geo")
    stop = geo.locations.get(stop_id)
    if not stop or stop.location_type != LocationType.TRANSIT_STOP:
        raise HTTPException(status_code=404, detail=f"Transit stop '{stop_id}' not found")
    line_ids = getattr(stop, "line_ids", [])
    lines = [geo.transit_lines[lid].model_dump() for lid in line_ids if lid in geo.transit_lines]
    return {"stop_id": stop_id, "lines": lines}
