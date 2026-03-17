"""Request and response schemas for the /attractions endpoints."""
from pydantic import BaseModel


class AttractionSearchRequest(BaseModel):
    city_id: str
    category: str | None = None
    district_id: str | None = None
    max_ticket_price: float | None = None
    free_only: bool = False
    session_id: str | None = None


class AttractionResult(BaseModel):
    attraction_id: str
    name: str
    category: str
    district_name: str
    ticket_price: float
    duration_hours: float
    crowding_level: float
    wait_time_min: int
    average_rating: float | None
    review_count: int
    opening_hours: dict


class NearbyRequest(BaseModel):
    location_id: str
    radius_km: float = 1.0
    location_types: list[str] | None = None
