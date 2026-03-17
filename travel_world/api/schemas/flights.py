"""Request and response schemas for the /flights endpoints."""
from pydantic import BaseModel, Field
from datetime import date
from typing import Optional


class FlightSearchRequest(BaseModel):
    origin_city_id: str
    destination_city_id: str
    departure_date: date
    return_date: Optional[date] = None
    passengers: int = Field(default=1, ge=1, le=9)
    cabin_class: Optional[str] = None
    session_id: Optional[str] = None


class FlightResult(BaseModel):
    """Matches the dict produced by FlightService._build_flight_result()."""
    edge_id: str
    origin_hub_id: str
    destination_hub_id: str
    airline: str
    flight_number: str
    departure_datetime: str
    arrival_datetime: str
    departure_time: str
    arrival_time: str
    duration_min: int
    price_per_person: float
    total_price: float
    passengers: int
    expected_delay_min: int
    distance_km: float
    baggage_included: bool
    seats_available: Optional[int] = None
    cabin_class: Optional[str] = None

    model_config = {"extra": "allow"}


class FlightSearchResponse(BaseModel):
    flights: list[FlightResult]
    world_id: str
    search_date: str
    total_results: int
