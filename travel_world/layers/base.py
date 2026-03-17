"""
travel_world.layers.base — abstract base class and metadata envelope for all layers.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class LayerMeta(BaseModel):
    """Uniform envelope written around every layer's data payload when serialized to JSON."""

    layer_id: str
    world_id: str
    seed: int
    schema_version: str = "1.0"
    generated_at: datetime
    frozen: bool = False


def _date_range(start: str, end: str) -> list[str]:
    """
    Generate a list of ISO date strings from start (inclusive) to end (exclusive).

    Parameters
    ----------
    start : str
        ISO date string for the first date in the range.
    end : str
        ISO date string for the exclusive upper bound.

    Returns
    -------
    list[str]
        List of ISO date strings ``[start, end)``.
    """
    d = date.fromisoformat(start)
    e = date.fromisoformat(end)
    result: list[str] = []
    while d < e:
        result.append(d.isoformat())
        d += timedelta(days=1)
    return result


class BaseLayer(ABC):
    """
    Abstract base class for all world state layers.

    Design patterns:
    - Template Method: defines the save/load lifecycle; subclasses implement to_dict/from_dict
    - Strategy: each layer is an interchangeable strategy for a slice of world state
    - Null Object friendly: frozen layers silently ignore tick_update calls

    Serialization contract:
        Every layer file is a JSON object with a uniform outer envelope (LayerMeta fields)
        and a "data" key containing the layer-specific payload. This allows WorldManager
        to read the envelope without knowing the layer type, then dispatch to the correct
        subclass for deserialization.
    """

    def __init__(self, meta: LayerMeta) -> None:
        self._meta = meta

    @property
    def layer_id(self) -> str:
        return self._meta.layer_id

    @property
    def world_id(self) -> str:
        return self._meta.world_id

    @property
    def seed(self) -> int:
        return self._meta.seed

    @property
    def frozen(self) -> bool:
        return self._meta.frozen

    def freeze(self) -> None:
        """Mark this layer as frozen. Frozen layers are not mutated by simulation ticks."""
        self._meta.frozen = True

    def unfreeze(self) -> None:
        """Mark this layer as unfrozen, allowing simulation ticks to mutate it."""
        self._meta.frozen = False

    @abstractmethod
    def to_dict(self) -> dict:
        """Serialize the layer-specific payload to a plain Python dict."""

    @classmethod
    @abstractmethod
    def from_dict(cls, meta: LayerMeta, data: dict) -> "BaseLayer":
        """Deserialize a layer from its meta envelope and data dict."""

    @abstractmethod
    def validate_internal_consistency(self) -> list[str]:
        """
        Check that all internal references and constraints are satisfied.
        Returns a list of violation message strings (empty = valid).
        """

    @abstractmethod
    def summary(self) -> dict:
        """Return a dict of summary statistics (entity counts, date ranges, etc.)."""

    def save(self, path: Path) -> None:
        """Serialize this layer and write to a JSON file at the given path."""
        meta_dict = self._meta.model_dump(mode="json")
        envelope = {**meta_dict, "data": self.to_dict()}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(envelope, indent=2, default=str), encoding="utf-8")
        logger.debug("Saved layer '%s' to %s", self._meta.layer_id, path)

    @classmethod
    def load(cls, path: Path) -> "BaseLayer":
        """
        Read a layer JSON file and deserialize to the appropriate BaseLayer subclass.

        Note: callers should use WorldManager.load_layer rather than calling this directly,
        as WorldManager knows which subclass to dispatch to based on layer_id.
        """
        raw = json.loads(path.read_text(encoding="utf-8"))
        data = raw.pop("data")
        meta = LayerMeta.model_validate(raw)
        return cls.from_dict(meta, data)

    def tick_update(self, sim_datetime: datetime) -> None:
        """
        Apply one simulation time-step mutation to this layer.
        No-op if layer is frozen. Override in subclasses that support dynamics.
        """
        if self._meta.frozen:
            return
        self._on_tick(sim_datetime)

    def _on_tick(self, sim_datetime: datetime) -> None:
        """Override in subclasses to implement dynamic updates per simulation tick."""
        pass
