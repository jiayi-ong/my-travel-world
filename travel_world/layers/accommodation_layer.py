"""
travel_world.layers.accommodation_layer — hotels and their availability calendars.
"""

from __future__ import annotations

from pydantic import BaseModel

from travel_world.core.entities import Hotel
from travel_world.core.exceptions import EntityNotFoundError
from travel_world.layers.base import BaseLayer, LayerMeta, _date_range


class AvailabilitySlot(BaseModel):
    """Availability and pricing for a single hotel on a single night."""

    date_str: str
    rooms_available: int
    price_tonight: float  # base price * demand multiplier


class AccommodationLayer(BaseLayer):
    """
    Hotels and their availability calendars.

    Availability is pre-computed at generation time for the world's date range.
    Price tonight reflects demand factors from EconomicsLayer applied at generation.

    This layer can be frozen (fixed availability scenario) or dynamic (availability
    decreases as the simulation advances and bookings are recorded).
    """

    LAYER_ID = "accommodation"

    def __init__(
        self,
        meta: LayerMeta,
        hotels: dict[str, Hotel],
        availability: dict[str, dict[str, AvailabilitySlot]],
    ) -> None:
        super().__init__(meta)
        self._hotels: dict[str, Hotel] = hotels
        self._availability: dict[str, dict[str, AvailabilitySlot]] = availability

    def get_hotel(self, hotel_id: str) -> Hotel:
        if hotel_id not in self._hotels:
            raise EntityNotFoundError(hotel_id, "Hotel")
        return self._hotels[hotel_id]

    def get_hotels_in_city(self, city_id: str) -> list[Hotel]:
        return [h for h in self._hotels.values() if h.city_id == city_id]

    def get_availability(self, hotel_id: str, date_str: str) -> AvailabilitySlot | None:
        return self._availability.get(hotel_id, {}).get(date_str)

    def get_availability_range(
        self, hotel_id: str, check_in: str, check_out: str
    ) -> list[AvailabilitySlot]:
        dates = _date_range(check_in, check_out)
        hotel_avail = self._availability.get(hotel_id, {})
        result: list[AvailabilitySlot] = []
        for d in dates:
            slot = hotel_avail.get(d)
            if slot is not None:
                result.append(slot)
        return result

    def is_available(
        self, hotel_id: str, check_in: str, check_out: str, guests: int
    ) -> bool:
        dates = _date_range(check_in, check_out)
        num_nights = len(dates)
        if num_nights == 0:
            return False
        slots = self.get_availability_range(hotel_id, check_in, check_out)
        # Need at least 1 slot and all found slots must have rooms
        if not slots:
            return False
        return all(slot.rooms_available >= 1 for slot in slots)

    def record_booking(self, hotel_id: str, check_in: str, check_out: str) -> None:
        """Decrement availability for each night. No-op if layer is frozen."""
        if self._meta.frozen:
            return
        dates = _date_range(check_in, check_out)
        hotel_avail = self._availability.get(hotel_id, {})
        for d in dates:
            slot = hotel_avail.get(d)
            if slot is not None:
                slot.rooms_available = max(0, slot.rooms_available - 1)

    def to_dict(self) -> dict:
        return {
            "hotels": {k: v.model_dump(mode="json") for k, v in self._hotels.items()},
            "availability": {
                hotel_id: {
                    date_str: slot.model_dump(mode="json")
                    for date_str, slot in dates.items()
                }
                for hotel_id, dates in self._availability.items()
            },
        }

    @classmethod
    def from_dict(cls, meta: LayerMeta, data: dict) -> "AccommodationLayer":
        hotels: dict[str, Hotel] = {
            k: Hotel.model_validate(v) for k, v in data["hotels"].items()
        }
        availability: dict[str, dict[str, AvailabilitySlot]] = {
            hotel_id: {
                date_str: AvailabilitySlot.model_validate(slot_dict)
                for date_str, slot_dict in dates.items()
            }
            for hotel_id, dates in data["availability"].items()
        }
        return cls(meta, hotels, availability)

    def validate_internal_consistency(self) -> list[str]:
        violations: list[str] = []
        for hotel_id, dates in self._availability.items():
            if hotel_id not in self._hotels:
                violations.append(
                    f"Availability references unknown hotel_id '{hotel_id}'"
                )
            for date_str, slot in dates.items():
                if slot.rooms_available < 0:
                    violations.append(
                        f"Hotel '{hotel_id}' date '{date_str}': rooms_available is negative ({slot.rooms_available})"
                    )
                if slot.price_tonight <= 0:
                    violations.append(
                        f"Hotel '{hotel_id}' date '{date_str}': price_tonight is not positive ({slot.price_tonight})"
                    )
        return violations

    def summary(self) -> dict:
        city_ids: set[str] = {h.city_id for h in self._hotels.values()}
        total_slots = sum(len(dates) for dates in self._availability.values())

        by_star_count: dict[int, int] = {}
        for hotel in self._hotels.values():
            by_star_count[hotel.star_rating] = by_star_count.get(hotel.star_rating, 0) + 1

        return {
            "layer_id": self.layer_id,
            "num_hotels": len(self._hotels),
            "num_cities": len(city_ids),
            "total_availability_slots": total_slots,
            "hotels_by_star_rating": by_star_count,
        }
