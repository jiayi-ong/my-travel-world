"""Integration tests for /session API endpoints."""
import pytest

class TestSessionLifecycle:

    def test_create_session_returns_session_id(self, test_client, seeded_world):
        """POST /session should return a session_id."""
        # TODO: response = test_client.post("/session", params={"world_id": seeded_world.world_id})
        # TODO: assert response.status_code == 200
        # TODO: assert "session_id" in response.json()
        pass

    def test_get_session_returns_preferences(self, test_client, seeded_world):
        """GET /session/{session_id} should return preferences and trip plan."""
        # TODO: create session, then GET it
        # TODO: assert "preferences" in data
        # TODO: assert "trip_plan" in data
        pass

    def test_update_preferences_persists(self, test_client, seeded_world):
        """PUT /session/{id}/preferences should update and return new preferences."""
        # TODO: create session, PUT new preferences, GET session again
        # TODO: assert updated fields match what was sent
        pass

    def test_add_trip_item_updates_cost(self, test_client, seeded_world):
        """POST /session/{id}/trip_plan/add should increase total_cost."""
        # TODO: create session, add an item with cost=100
        # TODO: GET /session/{id}/trip_plan/summary
        # TODO: assert summary["total_cost"] >= 100
        pass
