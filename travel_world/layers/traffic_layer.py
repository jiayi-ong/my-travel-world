"""
travel_world.layers.traffic_layer — edge-level congestion profiles for the transport graph.
"""

from __future__ import annotations

from datetime import datetime

from travel_world.layers.base import BaseLayer, LayerMeta


class TrafficLayer(BaseLayer):
    """
    Edge-level congestion profiles for the transport graph.

    Stores congestion multipliers indexed by (edge_id, hour_of_week).
    hour_of_week ranges 0-167 (Mon 00:00 = 0, Sun 23:00 = 167).

    Formula: actual_travel_time = base_travel_time * congestion_multiplier
    """

    LAYER_ID = "traffic"

    _DEFAULT_PROFILE: list[float] = [1.0] * 168

    def __init__(
        self,
        meta: LayerMeta,
        congestion_profiles: dict[str, list[float]],
    ) -> None:
        super().__init__(meta)
        self._congestion_profiles: dict[str, list[float]] = congestion_profiles

    def get_multiplier(self, edge_id: str, hour_of_week: int) -> float:
        profile = self._congestion_profiles.get(edge_id, self._DEFAULT_PROFILE)
        return profile[hour_of_week]

    def get_multiplier_for_datetime(self, edge_id: str, dt: datetime) -> float:
        hour_of_week = dt.weekday() * 24 + dt.hour
        return self.get_multiplier(edge_id, hour_of_week)

    def to_dict(self) -> dict:
        return {"congestion_profiles": self._congestion_profiles}

    @classmethod
    def from_dict(cls, meta: LayerMeta, data: dict) -> "TrafficLayer":
        return cls(meta, data["congestion_profiles"])

    def validate_internal_consistency(self) -> list[str]:
        violations: list[str] = []
        for edge_id, profile in self._congestion_profiles.items():
            if len(profile) != 168:
                violations.append(
                    f"Edge '{edge_id}': congestion profile has {len(profile)} entries, expected 168"
                )
            for hour, value in enumerate(profile):
                if not (0.1 <= value <= 5.0):
                    violations.append(
                        f"Edge '{edge_id}' hour {hour}: multiplier {value} out of range [0.1, 5.0]"
                    )
        return violations

    def summary(self) -> dict:
        all_values: list[float] = []
        for profile in self._congestion_profiles.values():
            all_values.extend(profile)

        mean_congestion = sum(all_values) / len(all_values) if all_values else 0.0
        max_congestion = max(all_values) if all_values else 0.0
        min_congestion = min(all_values) if all_values else 0.0

        return {
            "layer_id": self.layer_id,
            "num_edges": len(self._congestion_profiles),
            "mean_congestion": round(mean_congestion, 4),
            "max_congestion": max_congestion,
            "min_congestion": min_congestion,
        }

    def _on_tick(self, sim_datetime: datetime) -> None:
        # No-op for static congestion profiles; override for dynamic traffic simulation.
        pass
