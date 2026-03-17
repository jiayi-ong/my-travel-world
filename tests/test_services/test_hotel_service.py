"""Tests for HotelService search and booking logic."""
import pytest

class TestHotelServiceSearch:

    def test_search_returns_available_hotels(self, seeded_world):
        """search() should return hotels with availability for the requested range."""
        # TODO: from travel_world.services.hotel_service import HotelService
        # TODO: service = HotelService(seeded_world)
        # TODO: results = service.search(city_id, check_in, check_out, guests=1)
        # TODO: assert len(results) > 0
        # TODO: assert all r["rooms_available"] >= 1 for r in results
        pass

    def test_min_stars_filter(self, seeded_world):
        """search() with min_stars=4 should only return 4 and 5 star hotels."""
        # TODO: results = service.search(city_id, check_in, check_out, min_stars=4)
        # TODO: assert all r["star_rating"] >= 4 for r in results
        pass

class TestHotelServiceBooking:

    def test_booking_reduces_availability(self, seeded_world):
        """After booking, the same hotel should show one fewer room available."""
        # TODO: service = HotelService(seeded_world)
        # TODO: before = service.get_availability_calendar(hotel_id, check_in, check_out)
        # TODO: service.book(hotel_id, check_in, check_out, "test_session")
        # TODO: after = service.get_availability_calendar(...)
        # TODO: assert after[0]["rooms_available"] == before[0]["rooms_available"] - 1
        pass
