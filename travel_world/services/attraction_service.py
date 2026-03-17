"""
Attraction lookup, filtering, and crowding simulation service.
"""
import math
from datetime import datetime
from typing import Optional

from travel_world.core.enums import AttractionCategory, LocationType, WeatherCondition
from travel_world.core.exceptions import EntityNotFoundError
from travel_world.layers.geo_layer import GeoLayer
from travel_world.layers.weather_layer import WeatherLayer


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in km between two coordinate pairs."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


class AttractionService:
    """
    Handles attraction queries including real-time crowding estimates.

    Crowding model:
        Base crowding from attraction.crowding_base.
        Multiplied by time-of-day factor (peak: 10am-4pm on weekends).
        Multiplied by weather factor (bad weather reduces outdoor crowding).
    """

    # Weather condition -> crowding multiplier (bad weather suppresses outdoor crowds)
    _WEATHER_CROWDING_MULTIPLIERS = {
        WeatherCondition.SUNNY: 1.2,
        WeatherCondition.PARTLY_CLOUDY: 1.0,
        WeatherCondition.OVERCAST: 0.9,
        WeatherCondition.RAINY: 0.6,
        WeatherCondition.STORMY: 0.3,
        WeatherCondition.SNOWY: 0.5,
        WeatherCondition.FOGGY: 0.7,
    }

    def __init__(self, world_state):
        self._world_state = world_state
        self._geo: GeoLayer = world_state.get_layer("geo")
        try:
            self._weather: Optional[WeatherLayer] = world_state.get_layer("weather")
        except KeyError:
            self._weather = None

    def search(
        self,
        city_id: str,
        category: Optional[AttractionCategory] = None,
        district_id: Optional[str] = None,
        max_ticket_price: Optional[float] = None,
        free_only: bool = False,
        session_id: Optional[str] = None,
    ) -> list[dict]:
        """Search attractions with optional filters. Returns list of AttractionResult dicts."""
        from travel_world.core.entities import Attraction

        all_locations = self._geo.get_locations_by_type(city_id, LocationType.ATTRACTION)
        attractions = [loc for loc in all_locations if isinstance(loc, Attraction)]

        results: list[dict] = []
        now = datetime.now()

        for attraction in attractions:
            # Filter by category
            if category is not None and attraction.category != category:
                continue

            # Filter by district
            if district_id is not None and attraction.district_id != district_id:
                continue

            # Filter by ticket price
            if max_ticket_price is not None and attraction.ticket_price > max_ticket_price:
                continue

            # Filter by free entry
            if free_only and not attraction.free_entry:
                continue

            # Get current crowding estimate using sim_date at noon
            sim_dt = datetime(
                self._world_state.sim_date.year,
                self._world_state.sim_date.month,
                self._world_state.sim_date.day,
                12, 0,
            )
            crowding_info = self.get_crowding(attraction.location_id, sim_dt)

            district_name = ""
            district = self._geo.districts.get(attraction.district_id)
            if district is not None:
                district_name = district.name

            results.append({
                "attraction_id": attraction.location_id,
                "name": attraction.name,
                "city_id": attraction.city_id,
                "district_id": attraction.district_id,
                "district_name": district_name,
                "category": attraction.category.value,
                "ticket_price": attraction.ticket_price,
                "free_entry": attraction.free_entry,
                "duration_hours": attraction.duration_hours,
                "weather_sensitivity": attraction.weather_sensitivity,
                "popularity_score": attraction.popularity_score,
                "crowding_level": crowding_info["crowding_level"],
                "wait_time_min": crowding_info["wait_time_min"],
                "crowding_recommendation": crowding_info["recommendation"],
                "average_rating": attraction.ratings.average_rating if attraction.ratings else None,
                "review_count": attraction.ratings.review_count if attraction.ratings else 0,
                "description": attraction.description,
                "tags": attraction.tags,
                "coordinates": {
                    "lat": attraction.coordinates.lat,
                    "lon": attraction.coordinates.lon,
                },
            })

        return results

    def get_detail(self, attraction_id: str) -> dict:
        """Return full attraction record with current crowding and weather sensitivity note."""
        from travel_world.core.entities import Attraction

        location = self._geo.get_location(attraction_id)
        if not isinstance(location, Attraction):
            raise EntityNotFoundError(attraction_id, "Attraction")

        attraction = location

        sim_dt = datetime(
            self._world_state.sim_date.year,
            self._world_state.sim_date.month,
            self._world_state.sim_date.day,
            12, 0,
        )
        crowding_info = self.get_crowding(attraction_id, sim_dt)

        # Get weather for city on sim_date
        weather_note = ""
        if self._weather is not None:
            snapshot = self._weather.get_weather(
                attraction.city_id, self._world_state.sim_date.isoformat()
            )
            if snapshot is not None:
                if attraction.weather_sensitivity > 0.7:
                    weather_note = (
                        f"This attraction is highly weather-sensitive. "
                        f"Current condition: {snapshot.condition.value}."
                    )
                elif attraction.weather_sensitivity > 0.3:
                    weather_note = f"Current weather: {snapshot.condition.value}."

        district_name = ""
        district = self._geo.districts.get(attraction.district_id)
        if district is not None:
            district_name = district.name

        return {
            "attraction_id": attraction.location_id,
            "name": attraction.name,
            "city_id": attraction.city_id,
            "district_id": attraction.district_id,
            "district_name": district_name,
            "category": attraction.category.value,
            "ticket_price": attraction.ticket_price,
            "free_entry": attraction.free_entry,
            "duration_hours": attraction.duration_hours,
            "weather_sensitivity": attraction.weather_sensitivity,
            "popularity_score": attraction.popularity_score,
            "capacity": attraction.capacity,
            "opening_hours": attraction.opening_hours,
            "crowding_level": crowding_info["crowding_level"],
            "wait_time_min": crowding_info["wait_time_min"],
            "crowding_recommendation": crowding_info["recommendation"],
            "weather_note": weather_note,
            "average_rating": attraction.ratings.average_rating if attraction.ratings else None,
            "review_count": attraction.ratings.review_count if attraction.ratings else 0,
            "rating_distribution": (
                attraction.ratings.rating_distribution if attraction.ratings else {}
            ),
            "description": attraction.description,
            "tags": attraction.tags,
            "coordinates": {
                "lat": attraction.coordinates.lat,
                "lon": attraction.coordinates.lon,
            },
        }

    def get_nearby(
        self,
        location_id: str,
        radius_km: float = 1.0,
        location_types: Optional[list] = None,
    ) -> list[dict]:
        """Return attractions within radius_km of a given location."""
        origin = self._geo.get_location(location_id)
        origin_lat = origin.coordinates.lat
        origin_lon = origin.coordinates.lon
        city_id = origin.city_id

        from travel_world.core.entities import Attraction

        # Determine which location types to include
        if location_types is not None:
            target_types = set(
                lt.value if hasattr(lt, "value") else lt for lt in location_types
            )
        else:
            target_types = None

        nearby: list[dict] = []

        for loc in self._geo.get_locations_in_city(city_id):
            if loc.location_id == location_id:
                continue

            if target_types is not None:
                loc_type_val = loc.location_type.value if hasattr(loc.location_type, "value") else loc.location_type
                if loc_type_val not in target_types:
                    continue

            distance_km = _haversine(
                origin_lat, origin_lon,
                loc.coordinates.lat, loc.coordinates.lon,
            )

            if distance_km > radius_km:
                continue

            entry: dict = {
                "location_id": loc.location_id,
                "name": loc.name,
                "location_type": loc.location_type.value,
                "distance_km": round(distance_km, 3),
                "coordinates": {
                    "lat": loc.coordinates.lat,
                    "lon": loc.coordinates.lon,
                },
                "description": loc.description,
                "tags": loc.tags,
            }

            # Attach attraction-specific crowding if applicable
            if isinstance(loc, Attraction):
                sim_dt = datetime(
                    self._world_state.sim_date.year,
                    self._world_state.sim_date.month,
                    self._world_state.sim_date.day,
                    12, 0,
                )
                crowding_info = self.get_crowding(loc.location_id, sim_dt)
                entry["crowding_level"] = crowding_info["crowding_level"]
                entry["ticket_price"] = loc.ticket_price
                entry["category"] = loc.category.value

            nearby.append(entry)

        nearby.sort(key=lambda r: r["distance_km"])
        return nearby

    def get_crowding(self, attraction_id: str, visit_datetime: datetime) -> dict:
        """
        Estimate crowding level at a given datetime.

        Returns {crowding_level: float 0-1, wait_time_min: int, recommendation: str}
        """
        from travel_world.core.entities import Attraction

        location = self._geo.locations.get(attraction_id)
        if location is None or not isinstance(location, Attraction):
            return {
                "crowding_level": 0.0,
                "wait_time_min": 0,
                "recommendation": "No crowding data available.",
            }

        attraction = location
        base_crowding = attraction.crowding_base
        time_mult = self._time_of_day_multiplier(visit_datetime)

        # Weather multiplier: bad weather reduces outdoor crowding proportionally
        weather_mult = 1.0
        if self._weather is not None:
            date_str = visit_datetime.date().isoformat()
            snapshot = self._weather.get_weather(attraction.city_id, date_str)
            if snapshot is not None:
                raw_mult = self._WEATHER_CROWDING_MULTIPLIERS.get(snapshot.condition, 1.0)
                # Blend by weather_sensitivity: high sensitivity = full weather effect
                weather_mult = 1.0 + (raw_mult - 1.0) * attraction.weather_sensitivity

        crowding_level = min(1.0, max(0.0, base_crowding * time_mult * weather_mult))
        wait_time_min = int(crowding_level * 60)

        if crowding_level < 0.3:
            recommendation = "Best time to visit — very quiet."
        elif crowding_level < 0.6:
            recommendation = "Moderately busy — reasonable wait times expected."
        else:
            recommendation = "Very crowded — expect long queues."

        return {
            "crowding_level": round(crowding_level, 3),
            "wait_time_min": wait_time_min,
            "recommendation": recommendation,
        }

    def _time_of_day_multiplier(self, dt: datetime) -> float:
        """Return crowding multiplier based on hour and day of week."""
        hour = dt.hour
        is_weekend = dt.weekday() >= 5  # Saturday=5, Sunday=6

        if hour < 9:
            # Early morning: minimal crowds
            return 0.4
        elif 10 <= hour <= 16:
            # Peak hours
            return 1.8 if is_weekend else 1.4
        elif hour > 18:
            # Late evening
            return 0.6
        else:
            # Shoulder hours (9, 17, 18)
            return 1.0
