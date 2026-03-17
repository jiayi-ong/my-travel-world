"""
travel_world.layers.event_layer — events and their ticket availability.
"""

from __future__ import annotations

from travel_world.core.entities import Event
from travel_world.core.enums import EventCategory
from travel_world.core.exceptions import EntityNotFoundError
from travel_world.layers.base import BaseLayer, LayerMeta


class EventLayer(BaseLayer):
    """
    Events and their ticket availability.

    Events introduce temporal constraints that agents must plan around.
    Ticket prices are influenced by EconomicsLayer demand factors.
    """

    LAYER_ID = "event"

    def __init__(
        self,
        meta: LayerMeta,
        events: dict[str, Event],
    ) -> None:
        super().__init__(meta)
        self._events: dict[str, Event] = events
        # Initialise remaining ticket counts from each event's capacity.
        self._tickets_remaining: dict[str, int] = {
            eid: e.capacity for eid, e in events.items()
        }

    def get_event(self, event_id: str) -> Event:
        if event_id not in self._events:
            raise EntityNotFoundError(event_id, "Event")
        return self._events[event_id]

    def get_events_in_city(
        self,
        city_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[Event]:
        result: list[Event] = []
        for event in self._events.values():
            if event.city_id != city_id:
                continue
            if start_date is not None and event.start_datetime[:10] < start_date:
                continue
            if end_date is not None and event.start_datetime[:10] > end_date:
                continue
            result.append(event)
        return result

    def get_events_by_category(
        self, city_id: str, category: EventCategory
    ) -> list[Event]:
        return [
            e
            for e in self._events.values()
            if e.city_id == city_id and e.category == category
        ]

    def get_tickets_remaining(self, event_id: str) -> int:
        event = self._events.get(event_id)
        default = event.capacity if event is not None else 0
        return self._tickets_remaining.get(event_id, default)

    def book_ticket(self, event_id: str, quantity: int = 1) -> bool:
        """Attempt to book tickets. Returns True if successful, False if sold out."""
        if self._meta.frozen:
            return False
        remaining = self._tickets_remaining.get(event_id, 0)
        if remaining < quantity:
            return False
        self._tickets_remaining[event_id] = remaining - quantity
        return True

    def to_dict(self) -> dict:
        return {
            "events": {k: v.model_dump(mode="json") for k, v in self._events.items()},
            "tickets_remaining": dict(self._tickets_remaining),
        }

    @classmethod
    def from_dict(cls, meta: LayerMeta, data: dict) -> "EventLayer":
        events: dict[str, Event] = {
            k: Event.model_validate(v) for k, v in data["events"].items()
        }
        layer = cls(meta, events)
        # Restore persisted ticket counts, overwriting the defaults set in __init__.
        if "tickets_remaining" in data:
            layer._tickets_remaining = {
                k: int(v) for k, v in data["tickets_remaining"].items()
            }
        return layer

    def validate_internal_consistency(self) -> list[str]:
        violations: list[str] = []
        for event_id, remaining in self._tickets_remaining.items():
            if event_id not in self._events:
                violations.append(
                    f"tickets_remaining references unknown event_id '{event_id}'"
                )
                continue
            event = self._events[event_id]
            if remaining < 0:
                violations.append(
                    f"Event '{event_id}': tickets_remaining is negative ({remaining})"
                )
            if remaining > event.capacity:
                violations.append(
                    f"Event '{event_id}': tickets_remaining ({remaining}) exceeds capacity ({event.capacity})"
                )
        for event_id, event in self._events.items():
            if event.capacity < 0:
                violations.append(
                    f"Event '{event_id}': capacity is negative ({event.capacity})"
                )
        return violations

    def summary(self) -> dict:
        city_ids: set[str] = {e.city_id for e in self._events.values()}
        by_category: dict[str, int] = {}
        total_capacity = 0
        for event in self._events.values():
            key = event.category.value
            by_category[key] = by_category.get(key, 0) + 1
            total_capacity += event.capacity

        total_tickets_remaining = sum(self._tickets_remaining.values())

        return {
            "layer_id": self.layer_id,
            "num_events": len(self._events),
            "num_cities": len(city_ids),
            "events_by_category": by_category,
            "total_capacity": total_capacity,
            "total_tickets_remaining": total_tickets_remaining,
        }
