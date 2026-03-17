"""
Base classes for itinerary evaluation.

Design: Each check is a self-contained class implementing ItineraryCheck.
The ItineraryEvaluator collects checks and runs them, returning an
EvaluationReport with both UI-friendly accessors and a text summary
suitable for LLM evaluation prompts.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class CheckResult:
    """Result of a single itinerary check."""
    check_name: str
    passed: bool
    severity: Severity
    message: str
    details: dict = field(default_factory=dict)


class ItineraryCheck(ABC):
    """
    Abstract base for a single deterministic or heuristic itinerary check.

    Subclass and implement `run()`. Register instances with ItineraryEvaluator.
    """
    name: str = "Unnamed Check"
    severity: Severity = Severity.WARNING

    @abstractmethod
    def run(self, plan: dict, prefs: dict, context: dict) -> CheckResult:
        """
        Evaluate the itinerary plan against this check.

        Args:
            plan:    Trip plan dict (items, total_cost, etc.)
            prefs:   Session preferences (origin_city_id, budget_total, etc.)
            context: Optional extra context (city_labels, world_id, etc.)

        Returns:
            CheckResult with passed/failed status and a human-readable message.
        """
        ...
