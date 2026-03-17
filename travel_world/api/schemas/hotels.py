"""Request and response schemas for the /hotels endpoints."""
from pydantic import BaseModel, Field


class HotelSearchRequest(BaseModel):
    city_id: str
    check_in: str
    check_out: str
    guests: int = Field(default=1, ge=1)
    max_price_per_night: float | None = None
    min_stars: int | None = Field(default=None, ge=1, le=5)
    required_amenities: list[str] | None = None
    session_id: str | None = None


class HotelResult(BaseModel):
    hotel_id: str
    name: str
    star_rating: int
    district_name: str
    price_per_night: float
    total_cost: float
    amenities: list[str]
    rooms_available: int
    average_rating: float | None
    review_count: int
    check_in_time: str
    check_out_time: str


class HotelSearchResponse(BaseModel):
    hotels: list[HotelResult]
    world_id: str
    total_results: int
