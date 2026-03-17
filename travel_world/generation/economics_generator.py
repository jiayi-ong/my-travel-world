"""
Generates price curves and demand factors for dynamic pricing.

Intentionally separated from physical world generation so that pricing
scenarios can be swapped without regenerating geography or accommodations.
"""
import random
from datetime import date, timedelta

from travel_world.core.enums import TransportMode
from travel_world.layers.base import LayerMeta
from travel_world.layers.economics_layer import EconomicsLayer, PriceCurve


class EconomicsGenerator:
    """
    Generates EconomicsLayer: flight price curves and hotel demand factors.

    Pricing model:
        Flight prices follow a demand curve: higher prices close to departure
        and during peak season. Cabin class multipliers are fixed constants.
        Hotel demand factors spike around events and peak season months.
    """

    PEAK_MONTHS = [6, 7, 8, 12]        # June, July, August, December
    SHOULDER_MONTHS = [3, 4, 5, 9, 10, 11]
    LOW_MONTHS = [1, 2]

    def __init__(self, seed: int, config: dict):
        self.rng = random.Random(seed)
        self.config = config

    def generate(
        self,
        world_id: str,
        meta: LayerMeta,
        geo_layer,
        accommodation_layer,
        event_layer,
    ) -> EconomicsLayer:
        """Generate flight price curves and hotel demand factors."""
        # Flight price curves for all FLIGHT edges
        flight_price_curves: dict = {}
        for edge in geo_layer.transport_edges.values():
            if edge.mode == TransportMode.FLIGHT:
                route_key = f"{edge.origin_node_id}_{edge.destination_node_id}"
                flight_price_curves[route_key] = self._generate_flight_price_curve(edge)

        # Hotel demand factors
        start = date.today()
        days = self.config.get("date_range_days", 90)
        all_dates = [(start + timedelta(days=i)).isoformat() for i in range(days)]
        hotel_demand_factors: dict = {}
        for hotel_id, hotel in accommodation_layer._hotels.items():
            hotel_demand_factors[hotel_id] = self._generate_hotel_demand_factors(
                hotel, all_dates, event_layer, geo_layer
            )
        return EconomicsLayer(meta, flight_price_curves, hotel_demand_factors)

    def _generate_flight_price_curve(self, edge) -> PriceCurve:
        """Build a PriceCurve for one flight edge."""
        base_price = edge.base_cost * self.rng.uniform(0.8, 1.2)
        return PriceCurve(
            base_price=round(base_price, 2),
            days_in_advance_multipliers={
                "0-3":  2.5,
                "4-7":  1.8,
                "8-14": 1.4,
                "15-30": 1.1,
                "31+":  1.0,
            },
            seasonal_multipliers={
                **{str(m): 1.4 for m in self.PEAK_MONTHS},
                **{str(m): 1.0 for m in self.SHOULDER_MONTHS},
                **{str(m): 0.8 for m in self.LOW_MONTHS},
            },
        )

    def _generate_hotel_demand_factors(
        self, hotel, dates: list[str], event_layer, geo_layer
    ) -> dict:
        """Generate per-date demand multipliers for a single hotel."""
        factors: dict = {}
        for date_str in dates:
            month = date.fromisoformat(date_str).month
            if month in self.PEAK_MONTHS:
                base = 1.4
            elif month in self.SHOULDER_MONTHS:
                base = 1.0
            else:
                base = 0.8
            # Check for nearby events in the same city on this date
            city_events = event_layer.get_events_in_city(
                hotel.city_id, date_str, date_str
            )
            if city_events:
                base *= 1.5
            noise = self.rng.gauss(0, 0.05)
            factors[date_str] = round(max(0.5, min(2.5, base + noise)), 3)
        return factors
