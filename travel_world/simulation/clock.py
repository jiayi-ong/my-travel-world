"""
SimClock: manages simulation time for a world instance.

The simulation clock tracks the current datetime within the world's timeline.
It is not wall-clock time — it advances only when tick_engine.advance() is called.
"""
from datetime import datetime, timedelta


class SimClock:
    """
    Tracks and advances simulation time.

    Design: Value Object pattern — SimClock holds a single datetime value
    and provides controlled advancement. It does not mutate world state
    directly; that is the responsibility of TickEngine.

    Attributes:
        _current_time: The current simulation datetime.
        _start_time: The time the simulation started (immutable after init).
        _tick_duration: How much time each tick advances (default: 1 hour).
    """

    def __init__(self, start_time: datetime, tick_duration: timedelta = timedelta(hours=1)):
        self._start_time = start_time
        self._current_time = start_time
        self._tick_duration = tick_duration

    @property
    def current_time(self) -> datetime:
        return self._current_time

    @property
    def elapsed(self) -> timedelta:
        return self._current_time - self._start_time

    def tick(self) -> datetime:
        """Advance simulation time by one tick duration. Returns new current time."""
        self._current_time += self._tick_duration
        return self._current_time

    def advance_to(self, target: datetime) -> None:
        """Jump to a specific datetime. Raises ValueError if target is before current."""
        if target < self._current_time:
            raise ValueError(
                f"Cannot advance to {target}: already at {self._current_time}"
            )
        self._current_time = target

    def reset(self) -> None:
        """Reset clock to start time."""
        self._current_time = self._start_time
