"""Request and response schemas for the /session endpoints."""
from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    world_id: str


class UpdatePreferencesRequest(BaseModel):
    origin_city_id: str | None = None
    destination_city_ids: list[str] | None = None
    departure_date: str | None = None
    return_date: str | None = None
    budget_total: float | None = None
    group_size: int | None = None
    travel_style: str | None = None
    pace: str | None = None
    preferred_transport: list[str] | None = None


class TripPlanItemRequest(BaseModel):
    item_type: str
    ref_id: str
    date: str
    cost: float
    metadata: dict = {}


class ChatMessageRequest(BaseModel):
    role: str
    content: str


class SessionSummaryResponse(BaseModel):
    session_id: str
    world_id: str
    created_at: str
    total_cost: float
    budget_remaining: float | None
    item_count: int
    llm_connected: bool
