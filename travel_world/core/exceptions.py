"""
travel_world.core.exceptions — custom exception hierarchy for the simulation.

All exceptions derive from TravelWorldError so that callers can catch the
entire family with a single except clause when needed.
"""
from __future__ import annotations


class TravelWorldError(Exception):
    """Base exception for all travel_world errors."""


class LayerNotLoadedError(TravelWorldError):
    """Raised when a required layer is missing from WorldState."""

    def __init__(self, missing_layer_ids: list[str], world_id: str | None = None) -> None:
        where = f" in world '{world_id}'" if world_id else ""
        ids = ", ".join(f"'{lid}'" for lid in missing_layer_ids)
        super().__init__(
            f"Required layer(s) not loaded{where}: {ids}"
        )
        self.missing_layer_ids: list[str] = missing_layer_ids
        self.world_id: str | None = world_id


class LayerValidationError(TravelWorldError):
    """Raised when a layer fails its internal consistency check."""

    def __init__(self, layer_id: str, reason: str) -> None:
        super().__init__(f"Layer '{layer_id}' failed validation: {reason}")
        self.layer_id: str = layer_id
        self.reason: str = reason


class WorldNotFoundError(TravelWorldError):
    """Raised when a world_id cannot be located in the worlds directory."""

    def __init__(self, world_id: str) -> None:
        super().__init__(f"World not found: '{world_id}'")
        self.world_id: str = world_id


class EntityNotFoundError(TravelWorldError):
    """Raised when an entity ID lookup fails inside a layer."""

    def __init__(self, entity_id: str, entity_type: str | None = None) -> None:
        kind = f"{entity_type} " if entity_type else ""
        super().__init__(f"{kind}entity not found: '{entity_id}'")
        self.entity_id: str = entity_id
        self.entity_type: str | None = entity_type


class FeasibilityViolationError(TravelWorldError):
    """
    Raised when a plan or action violates one or more hard constraints.

    Attributes
    ----------
    violations : list[str]
        Human-readable descriptions of each constraint that was violated.
    """

    def __init__(self, message: str, violations: list[str] | None = None) -> None:
        super().__init__(message)
        self.violations: list[str] = violations or []


class BudgetExceededError(FeasibilityViolationError):
    """
    Raised when a plan exceeds the user's total budget hard constraint.

    Attributes
    ----------
    spent : float
        Total amount spent (or projected to be spent) by the plan.
    budget : float
        The user's total budget hard limit.
    violations : list[str]
        Human-readable descriptions of each budget line that was exceeded.
    """

    def __init__(
        self,
        spent: float,
        budget: float,
        message: str | None = None,
        violations: list[str] | None = None,
    ) -> None:
        if message is None:
            message = (
                f"Budget exceeded: spent {spent:.2f} against a budget of {budget:.2f} "
                f"(overage: {spent - budget:.2f})"
            )
        super().__init__(message, violations)
        self.spent: float = spent
        self.budget: float = budget


class SessionNotFoundError(TravelWorldError):
    """Raised when a session_id cannot be found in the session store."""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"Session not found: '{session_id}'")
        self.session_id: str = session_id
