"""
Multi-modal route planning service using the NetworkX transport graph.

Applies real-time congestion factors from TrafficLayer when computing
travel times, producing accurate departure-time-aware route estimates.
"""
import math
from datetime import datetime
from typing import Optional

import networkx as nx

from travel_world.core.enums import TransportMode
from travel_world.layers.geo_layer import GeoLayer
from travel_world.layers.traffic_layer import TrafficLayer


class RoutingService:
    """
    Plans multi-modal routes between locations using NetworkX shortest-path algorithms.

    Route computation:
        1. Load the transport graph from GeoLayer.
        2. For each requested transport mode, filter the graph to edges of that mode.
        3. Apply congestion multipliers from TrafficLayer based on departure hour-of-week.
        4. Run Dijkstra shortest path on the weighted subgraph.
        5. Compute total cost by summing edge cost attributes.
        6. Return RouteOption with polyline coordinates for map rendering.

    Optimize_for modes:
        "time"     — minimize total_duration_min (Dijkstra weight = congested travel time)
        "cost"     — minimize total_cost (Dijkstra weight = edge cost)
        "balanced" — minimize time + 0.5 * normalized_cost (weighted composite)
    """

    def __init__(self, world_state):
        self._world_state = world_state
        self._geo: GeoLayer = world_state.get_layer("geo")
        self._graph: nx.MultiDiGraph = self._geo.get_graph()
        try:
            self._traffic: Optional[TrafficLayer] = world_state.get_layer("traffic")
        except KeyError:
            self._traffic = None

    def plan(
        self,
        origin_location_id: str,
        destination_location_id: str,
        departure_datetime: datetime,
        modes: Optional[list] = None,
        optimize_for: str = "time",
        session_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Plan routes between two locations using all requested transport modes.

        Returns list of RouteOption dicts (one per available mode), each with:
        segments, total_duration_min, total_cost, total_distance_km, polyline.
        """
        self._world_state.require_layers("geo")

        if modes is None:
            modes = list(TransportMode)

        results: list[dict] = []
        for mode in modes:
            route = self._plan_single_mode(
                origin_location_id,
                destination_location_id,
                departure_datetime,
                mode,
                optimize_for,
            )
            if route is not None:
                results.append(route)

        # Sort by the requested optimization metric
        if optimize_for == "time":
            results.sort(key=lambda r: r.get("total_duration_min", float("inf")))
        elif optimize_for == "cost":
            results.sort(key=lambda r: r.get("total_cost", float("inf")))
        else:  # balanced
            results.sort(
                key=lambda r: r.get("total_duration_min", float("inf"))
                + 0.5 * r.get("total_cost", float("inf"))
            )

        return results

    def compare_modes(
        self,
        origin_location_id: str,
        destination_location_id: str,
        departure_datetime: datetime,
    ) -> list[dict]:
        """Return all available modes side-by-side for comparison."""
        return self.plan(
            origin_location_id,
            destination_location_id,
            departure_datetime,
            modes=None,
            optimize_for="time",
        )

    def get_travel_time(
        self,
        origin_id: str,
        destination_id: str,
        mode: TransportMode,
        departure_datetime: datetime,
    ) -> dict:
        """Return estimated travel time and cost for a specific mode."""
        route = self._plan_single_mode(
            origin_id, destination_id, departure_datetime, mode, "time"
        )
        if route is None:
            return {
                "duration_min": None,
                "cost": None,
                "congestion_applied": False,
                "available": False,
            }
        return {
            "duration_min": route.get("total_duration_min"),
            "cost": route.get("total_cost"),
            "congestion_applied": self._traffic is not None,
            "available": True,
        }

    def _plan_single_mode(
        self,
        origin_id: str,
        dest_id: str,
        departure_dt: datetime,
        mode: TransportMode,
        optimize_for: str,
    ) -> Optional[dict]:
        """
        Plan a route for a single transport mode. Returns None if no path exists.
        """
        mode_value = mode.value if hasattr(mode, "value") else str(mode)

        # Build a simple DiGraph subgraph for this mode only
        subgraph = nx.DiGraph()

        # Add nodes that participate in edges of this mode
        for u, v, key, data in self._graph.edges(keys=True, data=True):
            if data.get("mode") != mode_value:
                continue

            edge_id = data.get("edge_id", key)
            base_time = float(data.get("base_travel_time_min", 0.0))
            base_cost = float(data.get("base_cost", 0.0))
            distance_km = float(data.get("distance_km", 0.0))

            if optimize_for == "time":
                congested_time = self._apply_congestion_weight(edge_id, base_time, departure_dt)
                weight = congested_time
            elif optimize_for == "cost":
                weight = base_cost
            else:  # balanced
                congested_time = self._apply_congestion_weight(edge_id, base_time, departure_dt)
                weight = congested_time + 0.5 * base_cost

            # If there is already an edge (u, v), keep the minimum weight option
            if subgraph.has_edge(u, v):
                existing = subgraph[u][v]
                if weight < existing.get("weight", float("inf")):
                    subgraph[u][v].update({
                        "weight": weight,
                        "base_time": base_time,
                        "base_cost": base_cost,
                        "distance_km": distance_km,
                        "edge_id": edge_id,
                        "mode": mode_value,
                    })
            else:
                subgraph.add_edge(
                    u, v,
                    weight=weight,
                    base_time=base_time,
                    base_cost=base_cost,
                    distance_km=distance_km,
                    edge_id=edge_id,
                    mode=mode_value,
                )

        # Copy node coordinate data
        for node in subgraph.nodes():
            if self._graph.has_node(node):
                node_data = self._graph.nodes[node]
                subgraph.nodes[node].update(node_data)

        # Attempt shortest path
        try:
            path = nx.shortest_path(subgraph, origin_id, dest_id, weight="weight")
        except (nx.NetworkXNoPath, nx.NodeNotFound, nx.exception.NodeNotFound):
            return None
        except Exception:
            return None

        if len(path) < 2:
            return None

        # Build segments from path
        segments: list[dict] = []
        total_duration_min = 0.0
        total_cost = 0.0
        total_distance_km = 0.0

        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            edge_data = subgraph[u][v]

            base_time = edge_data.get("base_time", 0.0)
            base_cost = edge_data.get("base_cost", 0.0)
            distance_km = edge_data.get("distance_km", 0.0)
            edge_id = edge_data.get("edge_id", "")

            congested_time = self._apply_congestion_weight(edge_id, base_time, departure_dt)

            total_duration_min += congested_time
            total_cost += base_cost
            total_distance_km += distance_km

            # Get coordinates for origin / destination of this segment
            u_data = subgraph.nodes.get(u, {})
            v_data = subgraph.nodes.get(v, {})

            segments.append({
                "origin_id": u,
                "destination_id": v,
                "mode": mode_value,
                "duration_min": round(congested_time, 1),
                "cost": round(base_cost, 2),
                "distance_km": round(distance_km, 2),
                "edge_id": edge_id,
                "origin_coords": {
                    "lat": u_data.get("lat"),
                    "lon": u_data.get("lon"),
                },
                "destination_coords": {
                    "lat": v_data.get("lat"),
                    "lon": v_data.get("lon"),
                },
            })

        polyline = self._build_polyline(path, subgraph)

        return {
            "mode": mode_value,
            "origin_id": origin_id,
            "destination_id": dest_id,
            "segments": segments,
            "total_duration_min": round(total_duration_min, 1),
            "total_cost": round(total_cost, 2),
            "total_distance_km": round(total_distance_km, 2),
            "polyline": polyline,
            "num_transfers": len(path) - 2,
            "optimize_for": optimize_for,
        }

    def _apply_congestion_weight(
        self, edge_id: str, base_time: float, departure_dt: datetime
    ) -> float:
        """Multiply base travel time by the congestion factor at departure time."""
        if self._traffic is None:
            return base_time
        multiplier = self._traffic.get_multiplier_for_datetime(edge_id, departure_dt)
        return base_time * multiplier

    def _build_polyline(
        self, path_node_ids: list[str], subgraph: Optional[nx.DiGraph] = None
    ) -> list[list[float]]:
        """Extract lat/lon coordinates for each node in the path for map rendering."""
        polyline: list[list[float]] = []
        for node_id in path_node_ids:
            # Try geo layer location first
            location = self._geo.locations.get(node_id)
            if location is not None:
                polyline.append([location.coordinates.lat, location.coordinates.lon])
                continue
            # Fall back to graph node attributes
            if subgraph is not None and subgraph.has_node(node_id):
                node_data = subgraph.nodes[node_id]
                lat = node_data.get("lat")
                lon = node_data.get("lon")
                if lat is not None and lon is not None:
                    polyline.append([float(lat), float(lon)])
                    continue
            if self._graph.has_node(node_id):
                node_data = self._graph.nodes[node_id]
                lat = node_data.get("lat")
                lon = node_data.get("lon")
                if lat is not None and lon is not None:
                    polyline.append([float(lat), float(lon)])
        return polyline
