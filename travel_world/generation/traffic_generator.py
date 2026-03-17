"""
Generates edge-level congestion profiles for the transport graph.

Produces a 168-slot (hour-of-week) congestion multiplier array per edge,
capturing rush-hour, weekend, and overnight traffic patterns.
"""
import random

from travel_world.core.enums import TransportMode
from travel_world.layers.base import LayerMeta
from travel_world.layers.traffic_layer import TrafficLayer


class TrafficGenerator:
    """
    Generates TrafficLayer with per-edge, per-hour-of-week congestion multipliers.

    Congestion model:
        Base profile depends on edge transport mode (road = high variation, rail = low).
        Urban edges have morning (8-9am) and evening (5-7pm) rush-hour peaks.
        Weekend edges have reduced peaks but higher midday leisure traffic.
    """

    def __init__(self, seed: int, config: dict):
        self.rng = random.Random(seed)
        self.config = config

    def generate(self, world_id: str, meta: LayerMeta, geo_layer) -> TrafficLayer:
        """Generate 168-slot congestion profiles for all transport graph edges."""
        profiles: dict[str, list[float]] = {}
        for edge_id, edge in geo_layer.transport_edges.items():
            profiles[edge_id] = self._generate_edge_profile(edge)
        return TrafficLayer(meta, profiles)

    def _generate_edge_profile(self, edge) -> list[float]:
        """Generate a 168-element list of congestion multipliers for one edge."""
        profile: list[float] = []
        for hour_of_week in range(168):
            day = hour_of_week // 24   # 0 = Monday, 6 = Sunday
            hour = hour_of_week % 24
            if edge.mode in (TransportMode.FLIGHT, TransportMode.RAIL):
                # Scheduled services: flat congestion, minimal variation
                base = 1.0
            else:
                base = 1.0
                is_weekend = day >= 5
                # Rush hours on weekdays
                if not is_weekend and hour in (7, 8, 9, 17, 18, 19):
                    base = self.rng.uniform(1.6, 2.2)
                elif not is_weekend and hour in (10, 11, 12, 13, 14, 15, 16):
                    base = self.rng.uniform(1.1, 1.4)
                elif is_weekend and hour in (11, 12, 13, 14, 15, 16):
                    base = self.rng.uniform(1.2, 1.6)
                elif hour in (0, 1, 2, 3, 4, 5):
                    base = self.rng.uniform(0.5, 0.8)
            noise = self.rng.gauss(0, 0.05)
            profile.append(round(max(0.5, min(3.0, base + noise)), 3))
        return profile
