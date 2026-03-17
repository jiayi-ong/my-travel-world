"""
Generates per-city weather forecasts for the world's date range.

Uses a seasonal sinusoidal model per climate zone with added
random perturbations for day-to-day variation.
"""
import random
import math
from datetime import date, timedelta

from travel_world.core.enums import WeatherCondition, ClimateZone
from travel_world.layers.base import LayerMeta
from travel_world.layers.weather_layer import WeatherLayer, WeatherSnapshot


class WeatherGenerator:
    """
    Generates WeatherLayer with per-city, per-date weather forecasts.

    Climate model:
        Temperature follows a sinusoidal seasonal curve parameterized by ClimateZone.
        Precipitation is sampled from a zone-specific distribution.
        Extreme events (storms, blizzards) are inserted with low probability.
    """

    CLIMATE_PROFILES = {
        # ClimateZone -> {base_temp_c, temp_amplitude, precip_base_mm, storm_probability}
        "TROPICAL":    {"base_temp": 28, "amplitude": 3,  "precip": 8,  "storm_prob": 0.05},
        "SUBTROPICAL": {"base_temp": 22, "amplitude": 8,  "precip": 4,  "storm_prob": 0.03},
        "TEMPERATE":   {"base_temp": 14, "amplitude": 12, "precip": 3,  "storm_prob": 0.02},
        "CONTINENTAL": {"base_temp": 8,  "amplitude": 18, "precip": 2,  "storm_prob": 0.03},
        "ARID":        {"base_temp": 25, "amplitude": 10, "precip": 0.5, "storm_prob": 0.01},
        "POLAR":       {"base_temp": -5, "amplitude": 20, "precip": 1,  "storm_prob": 0.04},
    }

    def __init__(self, seed: int, config: dict):
        self.rng = random.Random(seed)
        self.config = config

    def generate(self, world_id: str, meta: LayerMeta, geo_layer) -> WeatherLayer:
        """Generate weather forecasts for all cities in geo_layer."""
        start = date.today()
        days = self.config.get("date_range_days", 90)
        all_dates = [(start + timedelta(days=i)).isoformat() for i in range(days)]
        forecasts: dict = {}
        for city in geo_layer.cities.values():
            forecasts[city.city_id] = self._generate_city_forecast(city, all_dates)
        return WeatherLayer(meta, forecasts)

    def _generate_city_forecast(self, city, dates: list[str]) -> dict:
        """Generate per-date weather snapshots for a single city."""
        # Look up climate profile using uppercase enum value
        climate_key = city.climate_zone.value.upper()
        profile = self.CLIMATE_PROFILES.get(climate_key, self.CLIMATE_PROFILES["TEMPERATE"])
        result: dict = {}
        for date_str in dates:
            d = date.fromisoformat(date_str)
            # Sinusoidal temperature: peak in July (month 7), trough in January
            day_of_year = d.timetuple().tm_yday
            temp = (
                profile["base_temp"]
                + profile["amplitude"] * math.sin(2 * math.pi * (day_of_year - 80) / 365)
            )
            temp += self.rng.gauss(0, 2)
            precip = max(0.0, self.rng.expovariate(1 / max(0.1, profile["precip"])))
            wind = abs(self.rng.gauss(15, 8))
            visibility = self.rng.uniform(5, 30)
            humidity = self.rng.uniform(30, 95)
            # Determine condition
            if self.rng.random() < profile["storm_prob"]:
                condition = WeatherCondition.STORMY if temp > 5 else WeatherCondition.SNOWY
            elif precip > 10:
                condition = WeatherCondition.RAINY
            elif precip > 3:
                condition = WeatherCondition.PARTLY_CLOUDY
            elif visibility < 5:
                condition = WeatherCondition.FOGGY
            else:
                condition = WeatherCondition.SUNNY
            result[date_str] = WeatherSnapshot(
                temperature_c=round(temp, 1),
                precipitation_mm=round(precip, 1),
                wind_speed_kmh=round(wind, 1),
                visibility_km=round(visibility, 1),
                condition=condition,
                humidity_pct=round(humidity, 1),
            )
        return result
