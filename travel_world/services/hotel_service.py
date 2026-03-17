"""
Hotel search, availability checking, and booking service.
"""
import uuid
from typing import Optional

from travel_world.core.exceptions import EntityNotFoundError, FeasibilityViolationError
from travel_world.layers.accommodation_layer import AccommodationLayer
from travel_world.layers.economics_layer import EconomicsLayer
from travel_world.layers.geo_layer import GeoLayer


class HotelService:
    """
    Handles all hotel-related queries and bookings.

    Computes tonight's price by combining hotel base price with
    EconomicsLayer demand factors.
    """

    def __init__(self, world_state):
        self._world_state = world_state
        self._geo: GeoLayer = world_state.get_layer("geo")
        self._accomm: AccommodationLayer = world_state.get_layer("accommodation")
        try:
            self._econ: Optional[EconomicsLayer] = world_state.get_layer("economics")
        except KeyError:
            self._econ = None

    def search(
        self,
        city_id: str,
        check_in: str,
        check_out: str,
        guests: int = 1,
        max_price_per_night: Optional[float] = None,
        min_stars: Optional[int] = None,
        required_amenities: Optional[list] = None,
        session_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Search available hotels in a city for a date range.

        Returns list of HotelResult dicts sorted by price_per_night ascending.
        Only hotels with availability for ALL nights in the range are returned.
        """
        self._world_state.require_layers("geo", "accommodation")
        accomm = self._accomm
        econ = self._econ

        hotels = accomm.get_hotels_in_city(city_id)

        results: list[dict] = []

        for hotel in hotels:
            # Filter by min_stars
            if min_stars is not None and hotel.star_rating < min_stars:
                continue

            # Filter by required_amenities
            if required_amenities:
                hotel_amenity_values = {a.value if hasattr(a, "value") else a for a in hotel.amenities}
                if not all(
                    (req.value if hasattr(req, "value") else req) in hotel_amenity_values
                    for req in required_amenities
                ):
                    continue

            # Filter by full-range availability
            if not accomm.is_available(hotel.location_id, check_in, check_out, guests):
                continue

            # Compute average nightly price over the date range
            slots = accomm.get_availability_range(hotel.location_id, check_in, check_out)
            if not slots:
                continue

            nightly_prices: list[float] = []
            for slot in slots:
                base = slot.price_tonight
                if econ is not None:
                    demand_factor = econ.get_hotel_demand_factor(hotel.location_id, slot.date_str)
                    nightly_prices.append(base * demand_factor)
                else:
                    nightly_prices.append(base)

            avg_price_per_night = sum(nightly_prices) / len(nightly_prices)
            num_nights = len(slots)
            total_cost = sum(nightly_prices)

            # Filter by max_price_per_night
            if max_price_per_night is not None and avg_price_per_night > max_price_per_night:
                continue

            # Resolve district name from geo layer
            district_name = ""
            district = self._geo.districts.get(hotel.district_id)
            if district is not None:
                district_name = district.name

            results.append({
                "hotel_id": hotel.location_id,
                "name": hotel.name,
                "city_id": hotel.city_id,
                "district_id": hotel.district_id,
                "district_name": district_name,
                "star_rating": hotel.star_rating,
                "price_per_night": round(avg_price_per_night, 2),
                "total_cost": round(total_cost, 2),
                "num_nights": num_nights,
                "check_in": check_in,
                "check_out": check_out,
                "amenities": [a.value if hasattr(a, "value") else a for a in hotel.amenities],
                "average_rating": hotel.ratings.average_rating if hotel.ratings else None,
                "review_count": hotel.ratings.review_count if hotel.ratings else 0,
                "description": hotel.description,
                "check_in_time": hotel.check_in_time,
                "check_out_time": hotel.check_out_time,
                "coordinates": {
                    "lat": hotel.coordinates.lat,
                    "lon": hotel.coordinates.lon,
                },
                "tags": hotel.tags,
                "neighborhood_score": round(hotel.neighborhood_score, 2),
            })

        # Sort by average price per night ascending
        results.sort(key=lambda r: r["price_per_night"])
        return results

    def get_hotel_detail(self, hotel_id: str) -> dict:
        """Return full hotel record including current availability summary."""
        hotel = self._accomm.get_hotel(hotel_id)

        # Get upcoming availability (from sim_date forward for 30 days)
        today = self._world_state.sim_date.isoformat()
        from datetime import date, timedelta
        end_date = (self._world_state.sim_date + timedelta(days=30)).isoformat()
        slots = self._accomm.get_availability_range(hotel_id, today, end_date)

        available_dates = [s.date_str for s in slots if s.rooms_available > 0]
        avg_price = (
            sum(s.price_tonight for s in slots) / len(slots) if slots else hotel.price_per_night
        )

        district_name = ""
        district = self._geo.districts.get(hotel.district_id)
        if district is not None:
            district_name = district.name

        return {
            "hotel_id": hotel.location_id,
            "name": hotel.name,
            "city_id": hotel.city_id,
            "district_id": hotel.district_id,
            "district_name": district_name,
            "star_rating": hotel.star_rating,
            "base_price_per_night": hotel.price_per_night,
            "avg_price_per_night": round(avg_price, 2),
            "amenities": [a.value if hasattr(a, "value") else a for a in hotel.amenities],
            "room_types": hotel.room_types,
            "total_rooms": hotel.total_rooms,
            "neighborhood_score": hotel.neighborhood_score,
            "check_in_time": hotel.check_in_time,
            "check_out_time": hotel.check_out_time,
            "average_rating": hotel.ratings.average_rating if hotel.ratings else None,
            "review_count": hotel.ratings.review_count if hotel.ratings else 0,
            "description": hotel.description,
            "coordinates": {
                "lat": hotel.coordinates.lat,
                "lon": hotel.coordinates.lon,
            },
            "tags": hotel.tags,
            "upcoming_available_dates_count": len(available_dates),
        }

    def get_availability_calendar(
        self, hotel_id: str, check_in: str, check_out: str
    ) -> list[dict]:
        """Return per-night availability and price for a date range."""
        hotel = self._accomm.get_hotel(hotel_id)
        slots = self._accomm.get_availability_range(hotel_id, check_in, check_out)
        econ = self._econ

        calendar: list[dict] = []
        for slot in slots:
            price = slot.price_tonight
            if econ is not None:
                demand_factor = econ.get_hotel_demand_factor(hotel_id, slot.date_str)
                price = price * demand_factor

            calendar.append({
                "date": slot.date_str,
                "rooms_available": slot.rooms_available,
                "price_tonight": round(price, 2),
                "available": slot.rooms_available > 0,
            })

        return calendar

    def book(
        self,
        hotel_id: str,
        check_in: str,
        check_out: str,
        session_id: str,
    ) -> dict:
        """
        Record a hotel booking: decrement availability and add to session trip plan.

        Returns booking confirmation dict.
        Raises FeasibilityViolationError if hotel not available for full range.
        """
        accomm = self._accomm

        if not accomm.is_available(hotel_id, check_in, check_out, 1):
            raise FeasibilityViolationError(
                f"Hotel '{hotel_id}' is not available from {check_in} to {check_out}",
                violations=[f"No rooms available at hotel '{hotel_id}' for the requested dates"],
            )

        hotel = accomm.get_hotel(hotel_id)
        accomm.record_booking(hotel_id, check_in, check_out)

        # Compute total cost for the stay
        slots = accomm.get_availability_range(hotel_id, check_in, check_out)
        econ = self._econ
        nightly_prices: list[float] = []
        for slot in slots:
            price = slot.price_tonight
            if econ is not None:
                demand_factor = econ.get_hotel_demand_factor(hotel_id, slot.date_str)
                price = price * demand_factor
            nightly_prices.append(price)

        total_cost = sum(nightly_prices)
        num_nights = len(nightly_prices)

        booking_id = str(uuid.uuid4())

        return {
            "booking_id": booking_id,
            "hotel_id": hotel_id,
            "hotel_name": hotel.name,
            "check_in": check_in,
            "check_out": check_out,
            "num_nights": num_nights,
            "total_cost": round(total_cost, 2),
            "price_per_night": round(total_cost / num_nights, 2) if num_nights > 0 else 0.0,
            "session_id": session_id,
            "status": "confirmed",
        }

    def compare(self, hotel_ids: list[str], check_in: str, check_out: str) -> list[dict]:
        """Return side-by-side comparison dicts for a list of hotel IDs."""
        comparisons: list[dict] = []

        for hotel_id in hotel_ids:
            try:
                detail = self.get_hotel_detail(hotel_id)
            except Exception:
                continue

            slots = self._accomm.get_availability_range(hotel_id, check_in, check_out)
            econ = self._econ
            nightly_prices: list[float] = []
            for slot in slots:
                price = slot.price_tonight
                if econ is not None:
                    demand_factor = econ.get_hotel_demand_factor(hotel_id, slot.date_str)
                    price = price * demand_factor
                nightly_prices.append(price)

            total_cost = sum(nightly_prices)
            num_nights = len(nightly_prices)
            available = self._accomm.is_available(hotel_id, check_in, check_out, 1)

            comparisons.append({
                **detail,
                "check_in": check_in,
                "check_out": check_out,
                "num_nights": num_nights,
                "total_cost": round(total_cost, 2),
                "available": available,
            })

        comparisons.sort(key=lambda r: r.get("total_cost", float("inf")))
        return comparisons
