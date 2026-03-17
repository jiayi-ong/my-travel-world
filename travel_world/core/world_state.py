"""
travel_world.core.world_state — runtime snapshot of all active world layers.

WorldState is assembled by WorldManager at request time and injected into
services via FastAPI dependency injection. It is never serialised directly;
only its constituent layers are persisted to disk.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from travel_world.core.exceptions import LayerNotLoadedError


class WorldState:
    """
    Immutable composed snapshot of active layers for a world instance.

    WorldState is NOT persisted directly — only its constituent layers are.
    It is assembled by WorldManager and injected into services via FastAPI
    dependency injection.

    Design pattern: Composite + Facade
    - Composite: assembles multiple independent layer objects
    - Facade: provides a single access point to all world data for services
    """

    def __init__(
        self,
        world_id: str,
        composed_at: datetime,
        sim_date: date,
        layers: dict[str, Any],
    ) -> None:
        self.world_id = world_id
        self.composed_at = composed_at
        self.sim_date = sim_date
        self.layers = layers

    # ------------------------------------------------------------------
    # Layer access helpers
    # ------------------------------------------------------------------

    def get_layer(self, layer_id: str) -> Any:
        """Retrieve a specific layer by ID. Raises KeyError if not loaded."""
        if layer_id not in self.layers:
            raise KeyError(
                f"Layer '{layer_id}' is not loaded in WorldState for world '{self.world_id}'. "
                f"Available layers: {list(self.layers.keys())}"
            )
        return self.layers[layer_id]

    def has_layer(self, layer_id: str) -> bool:
        """Check if a specific layer is loaded in this WorldState."""
        return layer_id in self.layers

    def require_layers(self, *layer_ids: str) -> None:
        """
        Assert that all named layers are present; raise LayerNotLoadedError
        listing every missing layer ID if any are absent.
        """
        missing = [lid for lid in layer_ids if lid not in self.layers]
        if missing:
            raise LayerNotLoadedError(missing_layer_ids=missing, world_id=self.world_id)

    # ------------------------------------------------------------------
    # Introspection / summary
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        """
        Return a combined stats dict for each loaded layer.

        Each layer is expected to expose a ``summary()`` method that returns
        a plain dict. If a layer does not implement ``summary()``, a minimal
        placeholder is included so that the overall call never raises.
        """
        result: dict[str, Any] = {
            "world_id": self.world_id,
            "composed_at": self.composed_at.isoformat(),
            "sim_date": self.sim_date.isoformat(),
            "layers": {},
        }
        for layer_id, layer in self.layers.items():
            if hasattr(layer, "summary") and callable(layer.summary):
                result["layers"][layer_id] = layer.summary()
            else:
                result["layers"][layer_id] = {"layer_id": layer_id, "note": "no summary available"}
        return result

    # ------------------------------------------------------------------
    # Immutable update
    # ------------------------------------------------------------------

    def with_layer(self, layer: Any) -> "WorldState":
        """
        Return a new WorldState with the given layer replaced (immutable swap).

        The layer object must expose a ``layer_id`` attribute so that the
        correct key in the layers dict can be identified.
        """
        layer_id: str = layer.layer_id
        new_layers = {**self.layers, layer_id: layer}
        return WorldState(
            world_id=self.world_id,
            composed_at=self.composed_at,
            sim_date=self.sim_date,
            layers=new_layers,
        )

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        layer_ids = list(self.layers.keys())
        return (
            f"WorldState(world_id={self.world_id!r}, sim_date={self.sim_date}, "
            f"layers={layer_ids})"
        )
