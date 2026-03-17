"""
ItineraryEvaluator: runs all registered checks and returns a structured report.

Usage:
    from travel_world.evaluation.evaluator import ItineraryEvaluator
    from travel_world.evaluation.checks.origin_destination import OriginDestinationCheck
    from travel_world.evaluation.checks.budget import BudgetCheck

    evaluator = ItineraryEvaluator()
    evaluator.register(OriginDestinationCheck())
    evaluator.register(BudgetCheck())

    report = evaluator.run_all(plan, prefs, context)
    print(report.to_text())  # LLM-ready output
"""
from __future__ import annotations
from dataclasses import dataclass
from travel_world.evaluation.base import CheckResult, ItineraryCheck, Severity


@dataclass
class EvaluationReport:
    """Compiled results from all checks. Designed for both UI display and LLM prompts."""
    results: list[CheckResult]

    @property
    def passed(self) -> bool:
        """True only if no ERROR-severity checks failed."""
        return all(r.passed for r in self.results if r.severity == Severity.ERROR)

    @property
    def any_failed(self) -> bool:
        return any(not r.passed for r in self.results)

    @property
    def failures(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed]

    @property
    def warnings(self) -> list[CheckResult]:
        return [r for r in self.failures if r.severity == Severity.WARNING]

    @property
    def errors(self) -> list[CheckResult]:
        return [r for r in self.failures if r.severity == Severity.ERROR]

    def to_text(self) -> str:
        """
        Produce a structured plain-text summary suitable for inclusion in an LLM prompt.
        """
        lines = ["=== Itinerary Evaluation Report ==="]
        for r in self.results:
            status = "PASS" if r.passed else r.severity.value.upper()
            lines.append(f"[{status}] {r.check_name}: {r.message}")
            if r.details and not r.passed:
                for k, v in r.details.items():
                    lines.append(f"       {k}: {v}")
        overall = "PASSED" if not self.any_failed else (
            "FAILED" if self.errors else "WARNINGS"
        )
        lines.append(f"\nOverall: {overall} ({len(self.failures)} issue(s) found)")
        return "\n".join(lines)


def build_default_evaluator() -> "ItineraryEvaluator":
    """Return an evaluator pre-loaded with all standard checks."""
    from travel_world.evaluation.checks.origin_destination import OriginDestinationCheck
    from travel_world.evaluation.checks.budget import BudgetCheck

    ev = ItineraryEvaluator()
    ev.register(OriginDestinationCheck())
    ev.register(BudgetCheck())
    return ev


class ItineraryEvaluator:
    """
    Runs a collection of ItineraryCheck instances against a trip plan.

    Checks are run in registration order. Additional checks can be registered
    at any time via `register()` — designed for extensibility.
    """

    def __init__(self) -> None:
        self._checks: list[ItineraryCheck] = []

    def register(self, check: ItineraryCheck) -> None:
        """Add a check to the evaluation pipeline."""
        self._checks.append(check)

    def run_all(
        self,
        plan: dict,
        prefs: dict,
        context: dict | None = None,
    ) -> EvaluationReport:
        """
        Execute all registered checks and return a compiled EvaluationReport.

        Args:
            plan:    Full trip plan dict (items list, total_cost, etc.)
            prefs:   Session preferences (origin_city_id, budget_total, etc.)
            context: Optional extra context passed through to each check
                     (e.g. city_labels dict, world_id string).
        """
        ctx = context or {}
        results = [check.run(plan, prefs, ctx) for check in self._checks]
        return EvaluationReport(results=results)
