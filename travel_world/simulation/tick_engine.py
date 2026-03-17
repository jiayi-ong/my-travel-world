"""
TickEngine: advances all dynamic layers forward by one simulation tick.

Each tick, the engine calls tick_update() on all unfrozen layers in the
active WorldState, then returns the updated WorldState.
"""
from datetime import datetime

from travel_world.simulation.clock import SimClock


class TickEngine:
    """
    Orchestrates simulation ticks across all active world layers.

    Design: Observer-like pattern — TickEngine calls tick_update() on each
    layer, but layers are responsible for their own internal state mutations.
    Frozen layers are silently skipped.

    Attributes:
        clock: SimClock instance driving simulation time.
    """

    def __init__(self, clock: SimClock):
        self._clock = clock

    def tick(self, world_state: object) -> object:
        """
        Advance all unfrozen layers by one clock tick.

        Returns the same WorldState (layers are mutated in-place for dynamic layers).
        Note: this is one of the few places where in-place mutation is intentional
        and documented — it models real-time world state advancement.
        """
        self._clock.tick()
        for layer in world_state.layers.values():
            layer.tick_update(self._clock.current_time)
        return world_state

    def advance_to(self, world_state: object, target: datetime) -> object:
        """Advance simulation to a target datetime by repeatedly ticking."""
        while self._clock.current_time < target:
            self.tick(world_state)
        return world_state
