"""
WorldManager: central authority for all layer I/O and WorldState composition.

Design patterns:
    Repository: single access point for reading/writing world data on disk
    Factory: create_world() orchestrates generators and returns ready WorldState
    Builder: load_world() assembles WorldState from persisted layers
"""
import json
import shutil
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from travel_world.core.world_state import WorldState
from travel_world.core.exceptions import WorldNotFoundError, LayerNotLoadedError, LayerValidationError
from travel_world.layers.base import BaseLayer, LayerMeta
from travel_world.layers.geo_layer import GeoLayer
from travel_world.layers.weather_layer import WeatherLayer
from travel_world.layers.traffic_layer import TrafficLayer
from travel_world.layers.accommodation_layer import AccommodationLayer
from travel_world.layers.event_layer import EventLayer
from travel_world.layers.economics_layer import EconomicsLayer


class WorldManager:
    """
    Manages the lifecycle of world instances: creation, persistence, loading, and layer swapping.

    Each world instance lives in worlds/<world_id>/ as a directory of JSON layer files.
    WorldManager is the ONLY component that reads/writes those files.
    It is instantiated once at FastAPI startup and held in app.state.
    """

    LAYER_REGISTRY: dict[str, type] = {
        "geo": GeoLayer,
        "weather": WeatherLayer,
        "traffic": TrafficLayer,
        "accommodation": AccommodationLayer,
        "event": EventLayer,
        "economics": EconomicsLayer,
    }

    META_FILENAME = "meta.json"

    def __init__(self, worlds_root: Path):
        self.worlds_root = Path(worlds_root)
        self.worlds_root.mkdir(parents=True, exist_ok=True)

    # ── World lifecycle ──────────────────────────────────────────────────────

    def create_world(self, seed: int, world_id: Optional[str] = None, config: Optional[dict] = None) -> WorldState:
        """Generate a complete new world from a seed and persist all layers to disk."""
        from travel_world.generation.world_generator import WorldGenerator

        if world_id is None:
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            world_id = f"world_{seed}_{ts}"

        world_dir = self._world_dir(world_id)
        world_dir.mkdir(parents=True, exist_ok=True)

        generator = WorldGenerator(seed=seed, config=config)
        layers: dict[str, BaseLayer] = generator.generate_all(world_id)

        for layer in layers.values():
            self.save_layer(world_id, layer)

        self._write_meta(world_id, seed, list(layers.keys()))

        sim_date = date.today()
        return WorldState(
            world_id=world_id,
            composed_at=datetime.utcnow(),
            sim_date=sim_date,
            layers=layers,
        )

    def load_world(self, world_id: str, layer_ids: Optional[list[str]] = None) -> WorldState:
        """Load an existing world from disk, optionally loading only specific layers."""
        world_dir = self._world_dir(world_id)
        if not world_dir.exists():
            raise WorldNotFoundError(world_id)

        meta = self._read_meta(world_id)
        available_layer_ids: list[str] = meta.get("layer_ids", [])

        if layer_ids is None:
            to_load = available_layer_ids
        else:
            # Always include geo
            to_load = list(set(layer_ids) | {"geo"})
            to_load = [lid for lid in available_layer_ids if lid in to_load]

        layers: dict[str, BaseLayer] = {}
        violations_all: list[str] = []

        for layer_id in to_load:
            layer = self._load_layer(world_id, layer_id)
            violations = layer.validate_internal_consistency()
            if violations:
                violations_all.extend([f"[{layer_id}] {v}" for v in violations])
            layers[layer_id] = layer

        if violations_all:
            raise LayerValidationError(
                layer_id=", ".join(to_load),
                reason="; ".join(violations_all[:5])  # show first 5
            )

        sim_date_str = meta.get("sim_date", date.today().isoformat())
        sim_date = date.fromisoformat(sim_date_str)

        return WorldState(
            world_id=world_id,
            composed_at=datetime.utcnow(),
            sim_date=sim_date,
            layers=layers,
        )

    def save_layer(self, world_id: str, layer: BaseLayer) -> None:
        """Persist a single layer to disk, overwriting any existing file."""
        path = self._layer_path(world_id, layer.layer_id)
        layer.save(path)

    def swap_layer(self, world_state: WorldState, new_layer: BaseLayer) -> WorldState:
        """Return a new WorldState with one layer replaced (immutable swap)."""
        return world_state.with_layer(new_layer)

    def list_worlds(self) -> list[dict]:
        """Return metadata for all world directories under worlds_root."""
        result = []
        for d in sorted(self.worlds_root.iterdir()):
            if not d.is_dir():
                continue
            meta_path = d / self.META_FILENAME
            if not meta_path.exists():
                continue
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                result.append(meta)
            except (json.JSONDecodeError, OSError):
                continue
        return result

    def delete_world(self, world_id: str) -> None:
        """Delete all files for a world. Irreversible."""
        world_dir = self._world_dir(world_id)
        if not world_dir.exists():
            raise WorldNotFoundError(world_id)
        shutil.rmtree(world_dir)

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _world_dir(self, world_id: str) -> Path:
        return self.worlds_root / world_id

    def _layer_path(self, world_id: str, layer_id: str) -> Path:
        return self._world_dir(world_id) / f"{layer_id}_layer.json"

    def _load_layer(self, world_id: str, layer_id: str) -> BaseLayer:
        """Dispatch to the correct BaseLayer subclass for deserialization."""
        path = self._layer_path(world_id, layer_id)
        if not path.exists():
            raise LayerNotLoadedError([layer_id], world_id)

        subclass = self.LAYER_REGISTRY.get(layer_id)
        if subclass is None:
            raise LayerNotLoadedError([layer_id], world_id)

        return subclass.load(path)

    def _write_meta(self, world_id: str, seed: int, layer_ids: list[str]) -> None:
        meta = {
            "world_id": world_id,
            "seed": seed,
            "created_at": datetime.utcnow().isoformat(),
            "sim_date": date.today().isoformat(),
            "layer_ids": layer_ids,
        }
        path = self._world_dir(world_id) / self.META_FILENAME
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

    def _read_meta(self, world_id: str) -> dict:
        path = self._world_dir(world_id) / self.META_FILENAME
        if not path.exists():
            raise WorldNotFoundError(world_id)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
