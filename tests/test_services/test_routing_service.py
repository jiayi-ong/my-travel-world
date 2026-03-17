"""Tests for RoutingService multi-modal routing."""
import pytest
from datetime import datetime

class TestRoutingService:

    def test_plan_returns_routes(self, seeded_world):
        """plan() should return at least one route for connected locations."""
        # TODO: from travel_world.services.routing_service import RoutingService
        # TODO: service = RoutingService(seeded_world)
        # TODO: routes = service.plan(origin_location_id, dest_location_id, datetime.now())
        # TODO: assert len(routes) > 0
        pass

    def test_routes_have_polyline(self, seeded_world):
        """Each RouteOption should include a non-empty polyline list for map rendering."""
        # TODO: routes = service.plan(...)
        # TODO: assert all r["polyline"] for r in routes
        pass

    def test_optimize_for_time_sorts_by_duration(self, seeded_world):
        """optimize_for='time' should return routes sorted by total_duration_min."""
        # TODO: routes = service.plan(..., optimize_for="time")
        # TODO: durations = [r["total_duration_min"] for r in routes]
        # TODO: assert durations == sorted(durations)
        pass
