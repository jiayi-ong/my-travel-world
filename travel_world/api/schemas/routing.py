"""Request and response schemas for the /routing endpoints."""
from pydantic import BaseModel


class RoutePlanRequest(BaseModel):
    origin_location_id: str
    destination_location_id: str
    departure_datetime: str
    modes: list[str] | None = None
    optimize_for: str = "time"
    session_id: str | None = None


class RouteSegment(BaseModel):
    from_location_id: str
    to_location_id: str
    mode: str
    duration_min: int
    cost: float
    distance_km: float


class RouteOption(BaseModel):
    mode: str
    segments: list[RouteSegment]
    total_duration_min: int
    total_cost: float
    total_distance_km: float
    congestion_applied: bool
    polyline: list[list[float]]


class RoutePlanResponse(BaseModel):
    routes: list[RouteOption]
    world_id: str
    origin_name: str
    destination_name: str
