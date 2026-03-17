"""Request and response schemas for the /events endpoints."""
from pydantic import BaseModel


class EventSearchRequest(BaseModel):
    city_id: str
    start_date: str | None = None
    end_date: str | None = None
    category: str | None = None
    max_price: float | None = None
    session_id: str | None = None


class EventResult(BaseModel):
    event_id: str
    name: str
    category: str
    venue_name: str
    start_datetime: str
    end_datetime: str
    base_ticket_price: float
    tickets_remaining: int
    popularity: float
    description: str


class BookTicketRequest(BaseModel):
    event_id: str
    quantity: int = 1
    session_id: str
