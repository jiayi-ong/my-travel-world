"""Tests for FlightService search and pricing logic."""
import pytest

class TestFlightServiceSearch:

    def test_search_returns_results(self, seeded_world):
        """search() should return at least one flight for a valid city pair."""
        # TODO: from travel_world.services.flight_service import FlightService
        # TODO: service = FlightService(seeded_world)
        # TODO: results = service.search(origin_city_id, destination_city_id, departure_date)
        # TODO: assert len(results) > 0
        pass

    def test_results_sorted_by_price(self, seeded_world):
        """search() results should be sorted by price ascending."""
        # TODO: results = service.search(...)
        # TODO: prices = [r["price_per_person"] for r in results]
        # TODO: assert prices == sorted(prices)
        pass

    def test_invalid_city_raises_entity_not_found(self, seeded_world):
        """search() with a non-existent city_id should raise EntityNotFoundError."""
        # TODO: with pytest.raises(EntityNotFoundError):
        #           service.search("NONEXISTENT", destination, date)
        pass
