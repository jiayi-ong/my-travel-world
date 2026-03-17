"""Tests for WeatherLayer generation and access patterns."""
import pytest

class TestWeatherLayerAccess:

    def test_get_weather_returns_snapshot(self, seeded_world):
        """get_weather should return a WeatherSnapshot for a valid city and date."""
        # TODO: weather_layer = seeded_world.get_layer("weather")
        # TODO: city_id = first city in geo_layer
        # TODO: first_date = first date in forecast
        # TODO: snapshot = weather_layer.get_weather(city_id, first_date)
        # TODO: assert snapshot is not None
        # TODO: assert -60 <= snapshot.temperature_c <= 60
        pass

    def test_affects_travel_stormy_returns_high_multiplier(self, seeded_world):
        """STORMY weather should return a disruption multiplier >= 2.0."""
        # TODO: inject a STORMY snapshot into weather_layer
        # TODO: multiplier = weather_layer.affects_travel(city_id, date)
        # TODO: assert multiplier >= 2.0
        pass
