"""
Event search, browsing, and ticket booking service.
"""
from calendar import monthrange
from travel_world.core.enums import EventCategory
from travel_world.core.exceptions import FeasibilityViolationError, EntityNotFoundError


class EventService:
    """Handles event queries and ticket transactions."""

    def __init__(self, world_state):
        self._world_state = world_state
        self._event_layer = world_state.get_layer("event")
        self._geo_layer = world_state.get_layer("geo")

    def search(self, city_id: str, start_date: str | None = None,
               end_date: str | None = None,
               category: EventCategory | None = None,
               max_price: float | None = None,
               session_id: str | None = None) -> list[dict]:
        """Search events in a city with optional filters. Returns EventResult dicts sorted by date."""
        events = self._event_layer.get_events_in_city(city_id, start_date, end_date)
        if category is not None:
            events = [e for e in events if e.category == category]
        if max_price is not None:
            events = [e for e in events if e.base_ticket_price <= max_price]
        events = sorted(events, key=lambda e: e.start_datetime)
        return [self._to_result_dict(e) for e in events]

    def get_detail(self, event_id: str) -> dict:
        """Return full event record with current ticket availability."""
        event = self._event_layer.get_event(event_id)
        result = self._to_result_dict(event)
        # Attach venue location details
        try:
            venue = self._geo_layer.get_location(event.venue_id)
            result["venue_name"] = venue.name
            result["venue_coordinates"] = {
                "lat": venue.coordinates.lat,
                "lon": venue.coordinates.lon,
            }
        except (EntityNotFoundError, KeyError):
            result["venue_name"] = event.venue_id
        return result

    def get_calendar(self, city_id: str, year: int, month: int) -> dict:
        """Return events grouped by day for a calendar view."""
        _, last_day = monthrange(year, month)
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year}-{month:02d}-{last_day}"
        events = self.search(city_id, start_date, end_date)
        calendar: dict[str, list[dict]] = {}
        for event in events:
            day = event["start_datetime"][:10]
            calendar.setdefault(day, []).append(event)
        return calendar

    def book_ticket(self, event_id: str, quantity: int, session_id: str) -> dict:
        """Book tickets for an event. Returns confirmation or raises FeasibilityViolationError."""
        success = self._event_layer.book_ticket(event_id, quantity)
        if not success:
            remaining = self._event_layer.get_tickets_remaining(event_id)
            raise FeasibilityViolationError(
                f"Cannot book {quantity} ticket(s): only {remaining} remaining.",
                [f"Requested {quantity}, available {remaining}"]
            )
        event = self._event_layer.get_event(event_id)
        total_cost = round(event.base_ticket_price * quantity, 2)
        return {
            "event_id": event_id,
            "event_name": event.name,
            "quantity": quantity,
            "total_cost": total_cost,
            "start_datetime": event.start_datetime,
            "tickets_remaining": self._event_layer.get_tickets_remaining(event_id),
        }

    def _to_result_dict(self, event) -> dict:
        """Convert an Event entity to an API result dict."""
        venue_name = event.venue_id
        try:
            venue = self._geo_layer.get_location(event.venue_id)
            venue_name = venue.name
        except (EntityNotFoundError, KeyError):
            pass
        return {
            "event_id": event.event_id,
            "name": event.name,
            "category": event.category.value if hasattr(event.category, "value") else str(event.category),
            "venue_id": event.venue_id,
            "venue_name": venue_name,
            "city_id": event.city_id,
            "start_datetime": event.start_datetime,
            "end_datetime": event.end_datetime,
            "base_ticket_price": event.base_ticket_price,
            "requires_booking": getattr(event, "requires_booking", True),
            "is_all_day_entry": getattr(event, "is_all_day_entry", False),
            "tickets_remaining": self._event_layer.get_tickets_remaining(event.event_id),
            "capacity": event.capacity,
            "popularity": event.popularity,
            "description": event.description,
            "tags": event.tags,
            "average_rating": event.ratings.average_rating if event.ratings else None,
            "review_count": event.ratings.review_count if event.ratings else 0,
            "reviews": [
                {"reviewer_id": r.reviewer_id, "rating": r.rating,
                 "positivity": r.positivity, "text": r.text,
                 "date": r.date, "tags": r.tags}
                for r in event.reviews
            ],
        }
