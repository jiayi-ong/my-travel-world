"""
HTTP client wrapper for all calls to the Travel World FastAPI backend.

Design: Facade pattern — all HTTP details are hidden behind typed methods.
Tabs call api_client methods, never httpx directly.

Caching:
    GET endpoints use @st.cache_data(ttl=5) to avoid re-fetching on every
    Streamlit re-render while still reflecting recent changes.
    POST/PUT/DELETE calls are never cached.

Error handling:
    All methods catch httpx.HTTPStatusError and raise APIError with a
    user-friendly message. Tabs display these as st.error() messages.
"""
import httpx
import os
import streamlit as st
from typing import Any

API_BASE_URL = os.getenv("TRAVEL_WORLD_API_URL", "http://localhost:8000")

class APIError(Exception):
    """Raised when the backend returns a non-2xx response."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)

class TravelWorldClient:
    """
    HTTP client for the Travel World API.

    Instantiated once in app.py and passed to each tab render function.
    Uses httpx.Client (sync) for simplicity with Streamlit's synchronous model.
    """

    def __init__(self, base_url: str = API_BASE_URL, timeout: float = 10.0):
        self.base_url = base_url
        self._client = httpx.Client(base_url=base_url, timeout=timeout, follow_redirects=True)

    # ── World management ────────────────────────────────────────────────────

    @st.cache_data(ttl=30, show_spinner=False)
    def list_worlds(_self) -> list[dict]:
        """List available world instances."""
        return _self._get("/world")

    @st.cache_data(ttl=60, show_spinner=False)
    def list_cities(_self, world_id: str) -> list[dict]:
        """List cities in a world. Returns [{city_id, name, region_id}]."""
        return _self._get(f"/world/{world_id}/cities")

    def load_world(self, world_id: str) -> dict:
        """Set the active world on the backend."""
        return self._post(f"/world/{world_id}/load")

    @st.cache_data(ttl=300, show_spinner=False)
    def get_map_data(_self, world_id: str) -> dict:
        """Return all geographic data for the interactive map (cities, districts, locations, flight routes)."""
        return _self._get(f"/world/{world_id}/map_data")

    # ── Session management ──────────────────────────────────────────────────

    def create_session(self, world_id: str) -> str:
        """Create a session and return the session_id."""
        result = self._post("/session/", params={"world_id": world_id})
        return result.get("session_id", result)

    def update_preferences(self, session_id: str, preferences: dict) -> dict:
        """Update session preferences. Returns updated session dict."""
        return self._put(f"/session/{session_id}/preferences", json=preferences)

    @st.cache_data(ttl=5, show_spinner=False)
    def get_trip_plan(_self, session_id: str) -> dict:
        """Get full trip plan including all items."""
        return _self._get(f"/session/{session_id}/trip_plan")

    @st.cache_data(ttl=5, show_spinner=False)
    def get_trip_plan_summary(_self, session_id: str) -> dict:
        """Get current trip plan cost summary."""
        return _self._get(f"/session/{session_id}/trip_plan/summary")

    def add_trip_item(self, session_id: str, item: dict) -> dict:
        """Add an item to the session trip plan."""
        return self._post(f"/session/{session_id}/trip_plan/add", json=item)

    def delete_trip_item(self, session_id: str, item_id: str) -> dict:
        """Remove an item from the trip plan by item_id."""
        return self._delete(f"/session/{session_id}/trip_plan/{item_id}")

    def post_chat_message(self, session_id: str, role: str, content: str) -> dict:
        """Post a chat message to the session."""
        return self._post(
            f"/session/{session_id}/chat_message",
            json={"role": role, "content": content},
        )

    def poll_llm_status(self, session_id: str) -> dict:
        """Poll whether an LLM agent is connected to this session."""
        return self._get(f"/session/{session_id}/llm_status")

    # ── Flights ─────────────────────────────────────────────────────────────

    @st.cache_data(ttl=5, show_spinner=False)
    def search_flights(_self, origin_city_id: str, destination_city_id: str,
                       departure_date: str, passengers: int = 1,
                       cabin_class: str | None = None,
                       session_id: str | None = None) -> dict:
        """Search flights. Returns FlightSearchResponse dict."""
        params = {
            "origin_city_id": origin_city_id,
            "destination_city_id": destination_city_id,
            "departure_date": departure_date,
            "passengers": passengers,
        }
        if cabin_class is not None:
            params["cabin_class"] = cabin_class
        if session_id is not None:
            params["session_id"] = session_id
        return _self._get("/flights/search", params=params)

    # ── Hotels ──────────────────────────────────────────────────────────────

    @st.cache_data(ttl=5, show_spinner=False)
    def search_hotels(_self, city_id: str, check_in: str, check_out: str,
                      guests: int = 1, max_price_per_night: float | None = None,
                      min_stars: int | None = None,
                      session_id: str | None = None) -> dict:
        """Search hotels. Returns HotelSearchResponse dict."""
        params = {
            "city_id": city_id,
            "check_in": check_in,
            "check_out": check_out,
            "guests": guests,
        }
        if max_price_per_night is not None:
            params["max_price_per_night"] = max_price_per_night
        if min_stars is not None:
            params["min_stars"] = min_stars
        if session_id is not None:
            params["session_id"] = session_id
        return _self._get("/hotels/search", params=params)

    def book_hotel(self, hotel_id: str, check_in: str, check_out: str, session_id: str) -> dict:
        """Book a hotel room."""
        return self._post(
            f"/hotels/{hotel_id}/book",
            params={
                "check_in": check_in,
                "check_out": check_out,
                "session_id": session_id,
            },
        )

    # ── Routing ─────────────────────────────────────────────────────────────

    @st.cache_data(ttl=5, show_spinner=False)
    def compare_routes(_self, origin_location_id: str, destination_location_id: str,
                       departure_datetime: str) -> dict:
        """Get all transport mode options side-by-side."""
        params = {
            "origin_location_id": origin_location_id,
            "destination_location_id": destination_location_id,
            "departure_datetime": departure_datetime,
        }
        return _self._get("/routing/compare", params=params)

    # ── Events ──────────────────────────────────────────────────────────────

    @st.cache_data(ttl=5, show_spinner=False)
    def search_events(_self, city_id: str, start_date: str | None = None,
                      end_date: str | None = None, category: str | None = None,
                      session_id: str | None = None) -> list[dict]:
        """Search events in a city."""
        params: dict = {"city_id": city_id}
        if start_date is not None:
            params["start_date"] = start_date
        if end_date is not None:
            params["end_date"] = end_date
        if category is not None:
            params["category"] = category
        if session_id is not None:
            params["session_id"] = session_id
        return _self._get("/events/search", params=params)

    def book_event_ticket(self, event_id: str, quantity: int, session_id: str) -> dict:
        """Book event tickets."""
        return self._post(
            "/events/book",
            params={"event_id": event_id, "quantity": quantity, "session_id": session_id},
        )

    # ── Weather ─────────────────────────────────────────────────────────────

    @st.cache_data(ttl=30, show_spinner=False)
    def get_weather_forecast(_self, city_id: str, start_date: str, end_date: str) -> list[dict]:
        """Get daily weather forecast for a city."""
        return _self._get("/weather/forecast", params={
            "city_id": city_id, "start_date": start_date, "end_date": end_date
        })

    @st.cache_data(ttl=30, show_spinner=False)
    def get_weather_snapshot(_self, city_id: str, date: str) -> dict | None:
        """Get weather for a single city/date. Returns None if not available."""
        try:
            return _self._get("/weather/snapshot", params={"city_id": city_id, "date": date})
        except Exception:
            return None

    # ── Attractions ─────────────────────────────────────────────────────────

    @st.cache_data(ttl=30, show_spinner=False)
    def search_attractions(_self, city_id: str, category: str | None = None,
                            free_only: bool = False) -> list[dict]:
        """Search attractions in a city."""
        params: dict = {"city_id": city_id, "free_only": free_only}
        if category is not None:
            params["category"] = category
        return _self._get("/attractions/search", params=params)

    # ── Restaurants ─────────────────────────────────────────────────────────

    @st.cache_data(ttl=5, show_spinner=False)
    def search_restaurants(_self, city_id: str, cuisine: str | None = None,
                           max_avg_spend: float | None = None,
                           reservation_required: bool | None = None,
                           session_id: str | None = None) -> list[dict]:
        """Search restaurants in a city."""
        params: dict = {"city_id": city_id}
        if cuisine is not None:
            params["cuisine"] = cuisine
        if max_avg_spend is not None:
            params["max_avg_spend"] = max_avg_spend
        if reservation_required is not None:
            params["reservation_required"] = reservation_required
        if session_id is not None:
            params["session_id"] = session_id
        result = _self._get("/restaurants/search", params=params)
        return result.get("restaurants", result) if isinstance(result, dict) else result

    @st.cache_data(ttl=30, show_spinner=False)
    def get_restaurant_detail(_self, restaurant_id: str) -> dict:
        """Get full details for a restaurant including reviews."""
        return _self._get(f"/restaurants/{restaurant_id}")

    # ── Internal helpers ────────────────────────────────────────────────────

    def _get(self, path: str, params: dict | None = None) -> Any:
        """Make a GET request, raise APIError on non-2xx."""
        try:
            response = self._client.get(path, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise APIError(
                status_code=exc.response.status_code,
                message=f"API error {exc.response.status_code}: {exc.response.text}",
            ) from exc
        except httpx.RequestError as exc:
            raise APIError(
                status_code=0,
                message=f"Connection error: {exc}",
            ) from exc

    def _post(self, path: str, json: dict | None = None, params: dict | None = None) -> Any:
        """Make a POST request, raise APIError on non-2xx."""
        try:
            response = self._client.post(path, json=json, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise APIError(
                status_code=exc.response.status_code,
                message=f"API error {exc.response.status_code}: {exc.response.text}",
            ) from exc
        except httpx.RequestError as exc:
            raise APIError(
                status_code=0,
                message=f"Connection error: {exc}",
            ) from exc

    def _put(self, path: str, json: dict | None = None) -> Any:
        """Make a PUT request, raise APIError on non-2xx."""
        try:
            response = self._client.put(path, json=json)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise APIError(
                status_code=exc.response.status_code,
                message=f"API error {exc.response.status_code}: {exc.response.text}",
            ) from exc
        except httpx.RequestError as exc:
            raise APIError(
                status_code=0,
                message=f"Connection error: {exc}",
            ) from exc

    def _delete(self, path: str, params: dict | None = None) -> Any:
        """Make a DELETE request, raise APIError on non-2xx."""
        try:
            response = self._client.delete(path, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise APIError(
                status_code=exc.response.status_code,
                message=f"API error {exc.response.status_code}: {exc.response.text}",
            ) from exc
        except httpx.RequestError as exc:
            raise APIError(
                status_code=0,
                message=f"Connection error: {exc}",
            ) from exc

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()
