"""
travel_world.layers.economics_layer — dynamic pricing data and demand multipliers.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from travel_world.core.enums import CabinClass
from travel_world.layers.base import BaseLayer, LayerMeta

# Valid bucket strings for days-in-advance multiplier keys.
_VALID_ADVANCE_BUCKETS: frozenset[str] = frozenset({"0-3", "4-7", "8-14", "15-30", "31+"})

# Cabin class price multipliers.
_CABIN_MULTIPLIERS: dict[str, float] = {
    "economy": 1.0,
    "premium_economy": 1.6,
    "business": 3.0,
    "first": 5.0,
    # Also accept uppercase forms that may appear in legacy data.
    "ECONOMY": 1.0,
    "PREMIUM_ECONOMY": 1.6,
    "BUSINESS": 3.0,
    "FIRST": 5.0,
}


class PriceCurve(BaseModel):
    """Flight price curve: how price varies with days-in-advance and season."""

    base_price: float
    days_in_advance_multipliers: dict[str, float]  # "0-3", "4-7", "8-14", "15-30", "31+"
    seasonal_multipliers: dict[str, float]          # month number "1"-"12"


class EconomicsLayer(BaseLayer):
    """
    Dynamic pricing data. Provides multipliers and curves that services
    apply at query time to compute current prices.

    This layer is intentionally separate from AccommodationLayer and GeoLayer
    so that price scenarios can be swapped without regenerating the world.
    Example: swap in a 'high-season' EconomicsLayer to simulate peak pricing.
    """

    LAYER_ID = "economics"

    def __init__(
        self,
        meta: LayerMeta,
        flight_price_curves: dict[str, PriceCurve],
        hotel_demand_factors: dict[str, dict[str, float]],
    ) -> None:
        super().__init__(meta)
        self._flight_price_curves: dict[str, PriceCurve] = flight_price_curves
        self._hotel_demand_factors: dict[str, dict[str, float]] = hotel_demand_factors

    def get_flight_price(
        self,
        route_key: str,
        travel_date: str,
        days_in_advance: int,
        cabin_class: CabinClass,
    ) -> float:
        curve = self._flight_price_curves.get(route_key)
        if curve is None:
            return 0.0

        # Days-in-advance bucket.
        if days_in_advance <= 3:
            bucket = "0-3"
        elif days_in_advance <= 7:
            bucket = "4-7"
        elif days_in_advance <= 14:
            bucket = "8-14"
        elif days_in_advance <= 30:
            bucket = "15-30"
        else:
            bucket = "31+"
        days_mult = curve.days_in_advance_multipliers.get(bucket, 1.0)

        # Seasonal multiplier based on the travel month.
        month = str(datetime.strptime(travel_date, "%Y-%m-%d").month)
        seasonal_mult = curve.seasonal_multipliers.get(month, 1.0)

        # Cabin class multiplier — normalise to lowercase for lookup.
        cabin_key = cabin_class.value if hasattr(cabin_class, "value") else str(cabin_class)
        cabin_mult = _CABIN_MULTIPLIERS.get(cabin_key, 1.0)

        return curve.base_price * days_mult * seasonal_mult * cabin_mult

    def get_hotel_demand_factor(self, hotel_id: str, date_str: str) -> float:
        return self._hotel_demand_factors.get(hotel_id, {}).get(date_str, 1.0)

    def to_dict(self) -> dict:
        return {
            "flight_price_curves": {
                k: v.model_dump(mode="json") for k, v in self._flight_price_curves.items()
            },
            "hotel_demand_factors": self._hotel_demand_factors,
        }

    @classmethod
    def from_dict(cls, meta: LayerMeta, data: dict) -> "EconomicsLayer":
        flight_price_curves: dict[str, PriceCurve] = {
            k: PriceCurve.model_validate(v)
            for k, v in data["flight_price_curves"].items()
        }
        hotel_demand_factors: dict[str, dict[str, float]] = data.get(
            "hotel_demand_factors", {}
        )
        return cls(meta, flight_price_curves, hotel_demand_factors)

    def validate_internal_consistency(self) -> list[str]:
        violations: list[str] = []

        for route_key, curve in self._flight_price_curves.items():
            if curve.base_price <= 0:
                violations.append(
                    f"Route '{route_key}': base_price is not positive ({curve.base_price})"
                )
            for bucket_key, mult in curve.days_in_advance_multipliers.items():
                if bucket_key not in _VALID_ADVANCE_BUCKETS:
                    violations.append(
                        f"Route '{route_key}': unrecognised days_in_advance bucket '{bucket_key}'"
                    )
                if mult <= 0:
                    violations.append(
                        f"Route '{route_key}' bucket '{bucket_key}': multiplier {mult} is not positive"
                    )
            for month_key, mult in curve.seasonal_multipliers.items():
                if month_key not in {str(m) for m in range(1, 13)}:
                    violations.append(
                        f"Route '{route_key}': seasonal_multiplier key '{month_key}' is not a valid month (1-12)"
                    )
                if mult <= 0:
                    violations.append(
                        f"Route '{route_key}' month '{month_key}': seasonal multiplier {mult} is not positive"
                    )

        for hotel_id, dates in self._hotel_demand_factors.items():
            for date_str, factor in dates.items():
                if factor <= 0:
                    violations.append(
                        f"Hotel '{hotel_id}' date '{date_str}': demand_factor {factor} is not positive"
                    )

        return violations

    def summary(self) -> dict:
        all_factors: list[float] = []
        for dates in self._hotel_demand_factors.values():
            all_factors.extend(dates.values())

        mean_demand = sum(all_factors) / len(all_factors) if all_factors else 0.0

        all_base_prices = [c.base_price for c in self._flight_price_curves.values()]
        avg_base_price = (
            sum(all_base_prices) / len(all_base_prices) if all_base_prices else 0.0
        )

        return {
            "layer_id": self.layer_id,
            "num_routes": len(self._flight_price_curves),
            "num_hotels_with_demand_factors": len(self._hotel_demand_factors),
            "mean_demand_factor": round(mean_demand, 4),
            "avg_base_price": round(avg_base_price, 2),
        }
