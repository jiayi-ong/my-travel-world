"""Integration tests for /flights API endpoints."""
import pytest

class TestFlightsSearchEndpoint:

    def test_search_returns_200(self, test_client):
        """GET /flights/search with valid params should return 200."""
        # TODO: response = test_client.get("/flights/search", params={origin, destination, date})
        # TODO: assert response.status_code == 200
        # TODO: data = response.json()
        # TODO: assert "flights" in data
        # TODO: assert "total_results" in data
        pass

    def test_search_missing_params_returns_422(self, test_client):
        """GET /flights/search without required params should return 422."""
        # TODO: response = test_client.get("/flights/search")
        # TODO: assert response.status_code == 422
        pass

class TestFlightDetailEndpoint:

    def test_get_flight_returns_200(self, test_client):
        """GET /flights/{flight_id} with a valid ID should return 200."""
        # TODO: first search to get a flight_id, then GET /flights/{flight_id}
        # TODO: assert response.status_code == 200
        pass
