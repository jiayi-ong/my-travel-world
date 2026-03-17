"""
travel_world.layers.weather_layer — per-city, per-date weather state layer.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from travel_world.core.enums import WeatherCondition
from travel_world.layers.base import BaseLayer, LayerMeta, _date_range


class WeatherSnapshot(BaseModel):
    """Weather conditions at a specific city and datetime."""

    temperature_c: float
    precipitation_mm: float
    wind_speed_kmh: float
    visibility_km: float
    condition: WeatherCondition
    humidity_pct: float


class WeatherLayer(BaseLayer):
    """
    Per-city, per-date weather state layer.

    Stores a forecast grid indexed by (city_id, date_str). Can be swapped
    independently of GeoLayer to create experimental weather scenarios
    (e.g., train on sunny worlds, test on rainy worlds).

    Dynamic: supports tick_update to advance weather state forward in time.
    """

    LAYER_ID = "weather"

    # Travel disruption multipliers keyed by WeatherCondition.
    _DISRUPTION_MULTIPLIERS: dict[WeatherCondition, float] = {
        WeatherCondition.STORMY: 2.5,
        WeatherCondition.SNOWY: 2.0,
        WeatherCondition.FOGGY: 1.5,
        WeatherCondition.RAINY: 1.3,
    }

    def __init__(
        self,
        meta: LayerMeta,
        forecasts: dict[str, dict[str, WeatherSnapshot]],
    ) -> None:
        super().__init__(meta)
        self._forecasts: dict[str, dict[str, WeatherSnapshot]] = forecasts

    def get_weather(self, city_id: str, date_str: str) -> WeatherSnapshot | None:
        return self._forecasts.get(city_id, {}).get(date_str)

    def get_weather_range(
        self, city_id: str, start_date: str, end_date: str
    ) -> list[tuple[str, WeatherSnapshot]]:
        dates = _date_range(start_date, end_date)
        city_forecasts = self._forecasts.get(city_id, {})
        result: list[tuple[str, WeatherSnapshot]] = []
        for d in dates:
            snap = city_forecasts.get(d)
            if snap is not None:
                result.append((d, snap))
        return result

    def affects_travel(self, city_id: str, date_str: str) -> float:
        """Return a travel disruption multiplier (1.0 = normal, >1.0 = disrupted)."""
        snapshot = self.get_weather(city_id, date_str)
        if snapshot is None:
            return 1.0
        return self._DISRUPTION_MULTIPLIERS.get(snapshot.condition, 1.0)

    def to_dict(self) -> dict:
        return {
            city_id: {
                date_str: snap.model_dump(mode="json")
                for date_str, snap in dates.items()
            }
            for city_id, dates in self._forecasts.items()
        }

    @classmethod
    def from_dict(cls, meta: LayerMeta, data: dict) -> "WeatherLayer":
        forecasts: dict[str, dict[str, WeatherSnapshot]] = {
            city_id: {
                date_str: WeatherSnapshot.model_validate(snap_dict)
                for date_str, snap_dict in dates.items()
            }
            for city_id, dates in data.items()
        }
        return cls(meta, forecasts)

    def validate_internal_consistency(self) -> list[str]:
        violations: list[str] = []
        for city_id, dates in self._forecasts.items():
            for date_str, snap in dates.items():
                if not (-80.0 <= snap.temperature_c <= 60.0):
                    violations.append(
                        f"City '{city_id}' date '{date_str}': temperature_c {snap.temperature_c} "
                        f"out of range [-80, 60]"
                    )
                if not (0.0 <= snap.humidity_pct <= 100.0):
                    violations.append(
                        f"City '{city_id}' date '{date_str}': humidity_pct {snap.humidity_pct} "
                        f"out of range [0, 100]"
                    )
        return violations

    def summary(self) -> dict:
        all_dates: list[str] = []
        condition_distribution: dict[str, int] = {}
        for dates in self._forecasts.values():
            for date_str, snap in dates.items():
                all_dates.append(date_str)
                key = snap.condition.value
                condition_distribution[key] = condition_distribution.get(key, 0) + 1

        date_range_str: str | None = None
        if all_dates:
            date_range_str = f"{min(all_dates)} to {max(all_dates)}"

        return {
            "layer_id": self.layer_id,
            "num_cities": len(self._forecasts),
            "total_forecast_days": len(all_dates),
            "date_range": date_range_str,
            "condition_distribution": condition_distribution,
        }

    def _on_tick(self, sim_datetime: datetime) -> None:
        # No-op for now; future implementation could expire past forecasts.
        pass
