"""
Flight search, pricing, and booking service.

Queries the transport graph in GeoLayer for air routes, applies dynamic
pricing from EconomicsLayer, and simulates delays via stochastic sampling.
"""
import random
from datetime import date, datetime
from typing import Optional

from travel_world.core.enums import CabinClass, TransportMode
from travel_world.core.exceptions import EntityNotFoundError
from travel_world.layers.geo_layer import GeoLayer
from travel_world.layers.economics_layer import EconomicsLayer


class FlightService:
    """
    Handles all flight-related queries.

    Design: Service Layer pattern — all business logic for flights lives here.
    Routes are never called directly; they go through this service.
    The service is stateless between calls; all state comes from world_state.

    Args:
        world_state: The active WorldState (injected via FastAPI dependency).
        rng_seed: Optional seed for delay simulation (for reproducible test runs).
    """

    def __init__(self, world_state, rng_seed: Optional[int] = None):
        self._world_state = world_state
        self.rng = random.Random(rng_seed)
        self._geo: GeoLayer = world_state.get_layer("geo")
        try:
            self._econ: Optional[EconomicsLayer] = world_state.get_layer("economics")
        except KeyError:
            self._econ = None

    def search(
        self,
        origin_city_id: str,
        destination_city_id: str,
        departure_date: date,
        passengers: int = 1,
        cabin_class: Optional[CabinClass] = None,
        session_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Search for available flights between two cities on a given date.

        Args:
            origin_city_id: Departure city.
            destination_city_id: Arrival city.
            departure_date: Date of travel.
            passengers: Number of passengers (affects total price calculation).
            cabin_class: Filter by cabin class; None returns all classes.
            session_id: Optional session ID for interaction logging.

        Returns:
            List of FlightResult dicts sorted by price ascending.
        """
        self._world_state.require_layers("geo")

        origin_hubs = self._geo.get_transport_hubs(origin_city_id)
        dest_hubs = self._geo.get_transport_hubs(destination_city_id)

        departure_date_str = (
            departure_date.isoformat()
            if isinstance(departure_date, date)
            else str(departure_date)
        )

        today = self._world_state.sim_date
        if isinstance(departure_date, date):
            days_in_advance = (departure_date - today).days
        else:
            try:
                dep = date.fromisoformat(str(departure_date))
                days_in_advance = (dep - today).days
            except (ValueError, TypeError):
                days_in_advance = 0
        days_in_advance = max(0, days_in_advance)

        results: list[dict] = []

        for origin_hub in origin_hubs:
            for dest_hub in dest_hubs:
                flight_edges = self._geo.get_edges_between(
                    origin_hub.location_id,
                    dest_hub.location_id,
                    TransportMode.FLIGHT,
                )
                for edge in flight_edges:
                    # Determine which cabin classes to generate results for
                    if cabin_class is not None:
                        cabin_classes = [cabin_class]
                    else:
                        cabin_classes = [
                            CabinClass.ECONOMY,
                            CabinClass.PREMIUM_ECONOMY,
                            CabinClass.BUSINESS,
                            CabinClass.FIRST,
                        ]

                    # Build route key: origin_hub -> dest_hub
                    route_key = f"{origin_hub.location_id}_{dest_hub.location_id}"

                    for cab in cabin_classes:
                        if self._econ is not None:
                            price = self._econ.get_flight_price(
                                route_key,
                                departure_date_str,
                                days_in_advance,
                                cab,
                            )
                            # Fall back to edge base_cost if no curve exists
                            if price == 0.0:
                                price = edge.base_cost
                        else:
                            price = edge.base_cost
                        # Apply per-flight price multiplier for variation within a route
                        price *= edge.metadata.get("price_multiplier", 1.0)

                        # Add ±$50 uniform noise (minor dynamic pricing variation)
                        price += self.rng.uniform(-50, 50)
                        price = max(10.0, price)

                        delay = self._simulate_delay(edge)
                        seats = max(0, self.rng.randint(5, 100))

                        result = self._build_flight_result(
                            edge, price, delay, passengers, departure_date_str
                        )
                        result["seats_available"] = seats
                        result["cabin_class"] = cab.value if hasattr(cab, "value") else cab
                        results.append(result)

        # Sort by price ascending
        results.sort(key=lambda r: r.get("price_per_person", 0.0))
        return results

    def get_flight_detail(self, flight_id: str) -> dict:
        """Return full flight details for a specific flight_id."""
        edge = self._geo.transport_edges.get(flight_id)
        if edge is None:
            raise EntityNotFoundError(flight_id, "Flight")

        today = self._world_state.sim_date
        departure_date_str = today.isoformat()
        days_in_advance = 0

        route_key = f"{edge.origin_node_id}_{edge.destination_node_id}"
        if self._econ is not None:
            price = self._econ.get_flight_price(
                route_key, departure_date_str, days_in_advance, CabinClass.ECONOMY
            )
            if price == 0.0:
                price = edge.base_cost
        else:
            price = edge.base_cost

        delay = self._simulate_delay(edge)
        result = self._build_flight_result(edge, price, delay, 1, departure_date_str)
        result["edge_id"] = edge.edge_id
        result["distance_km"] = edge.distance_km
        result["mode"] = edge.mode.value
        result["carrier"] = edge.carrier
        result["frequency_per_day"] = edge.frequency_per_day
        return result

    def get_available_routes(self) -> list[dict]:
        """Return all city-pair routes that have at least one flight edge."""
        seen: set[tuple[str, str]] = set()
        routes: list[dict] = []

        for edge in self._geo.transport_edges.values():
            if edge.mode != TransportMode.FLIGHT:
                continue

            # Resolve city IDs for each hub
            origin_loc = self._geo.locations.get(edge.origin_node_id)
            dest_loc = self._geo.locations.get(edge.destination_node_id)
            if origin_loc is None or dest_loc is None:
                continue

            origin_city_id = origin_loc.city_id
            dest_city_id = dest_loc.city_id
            pair = (origin_city_id, dest_city_id)

            if pair in seen:
                continue
            seen.add(pair)

            origin_city = self._geo.cities.get(origin_city_id)
            dest_city = self._geo.cities.get(dest_city_id)

            routes.append({
                "origin_city_id": origin_city_id,
                "origin_city_name": origin_city.name if origin_city else origin_city_id,
                "destination_city_id": dest_city_id,
                "destination_city_name": dest_city.name if dest_city else dest_city_id,
                "origin_hub_id": edge.origin_node_id,
                "destination_hub_id": edge.destination_node_id,
            })

        return routes

    def _simulate_delay(self, flight_edge) -> int:
        """
        Simulate expected delay in minutes using edge's delay distribution.

        Returns a non-negative delay sampled from a normal distribution.
        """
        mean = flight_edge.metadata.get("mean_delay_min", 15)
        std = flight_edge.metadata.get("std_delay_min", 20)
        return max(0, int(self.rng.gauss(mean, std)))

    def _build_flight_result(
        self,
        edge,
        price: float,
        delay_min: int,
        passengers: int,
        departure_date_str: str = "",
    ) -> dict:
        """Build a FlightResult dict from edge data and computed values."""
        meta = edge.metadata or {}
        airline = meta.get("airline") or edge.carrier or "Unknown Airline"
        flight_number = meta.get("flight_number", edge.edge_id[:8])
        departure_time = meta.get("departure_time", "08:00")
        arrival_time = meta.get("arrival_time", "")
        duration_min = meta.get("duration_min", int(edge.base_travel_time_min))

        # Compute departure datetime string
        dep_dt_str = f"{departure_date_str}T{departure_time}:00" if departure_date_str else ""

        # Compute arrival datetime from departure + duration
        if dep_dt_str and not arrival_time:
            try:
                dep_dt = datetime.fromisoformat(dep_dt_str)
                from datetime import timedelta
                arr_dt = dep_dt + timedelta(minutes=duration_min)
                arrival_time = arr_dt.strftime("%H:%M")
                arr_dt_str = arr_dt.isoformat()
            except (ValueError, TypeError):
                arr_dt_str = ""
        elif dep_dt_str and arrival_time:
            # Reconstruct arrival datetime from same date + arrival_time
            try:
                dep_dt = datetime.fromisoformat(dep_dt_str)
                arr_dt_str = f"{dep_dt.date().isoformat()}T{arrival_time}:00"
            except (ValueError, TypeError):
                arr_dt_str = ""
        else:
            arr_dt_str = ""

        total_price = price * passengers

        return {
            "edge_id": edge.edge_id,
            "origin_hub_id": edge.origin_node_id,
            "destination_hub_id": edge.destination_node_id,
            "airline": airline,
            "flight_number": flight_number,
            "departure_datetime": dep_dt_str,
            "arrival_datetime": arr_dt_str,
            "departure_time": departure_time,
            "arrival_time": arrival_time,
            "duration_min": duration_min,
            "price_per_person": round(price, 2),
            "total_price": round(total_price, 2),
            "passengers": passengers,
            "expected_delay_min": delay_min,
            "distance_km": edge.distance_km,
            "baggage_included": meta.get("baggage_included", True),
        }
