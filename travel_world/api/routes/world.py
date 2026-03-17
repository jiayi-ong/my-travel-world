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
            {"city_id": c.city_id, "name": c.name, "region_id": c.region_id}
            for c in geo.cities.values()
        ]
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
