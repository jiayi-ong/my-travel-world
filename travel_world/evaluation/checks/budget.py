"""Check that the itinerary total cost does not exceed the configured budget."""
from travel_world.evaluation.base import CheckResult, ItineraryCheck, Severity


class BudgetCheck(ItineraryCheck):
    """
    Verifies the trip plan total cost is within the budget set in Trip Setup.
    Passes if no budget is configured.
    """
    name = "Budget Constraint"
    severity = Severity.WARNING

    def run(self, plan: dict, prefs: dict, context: dict) -> CheckResult:
        budget = prefs.get("budget_total")
        total_cost = float(plan.get("total_cost", 0))

        if not budget:
            return CheckResult(
                check_name=self.name,
                passed=True,
                severity=self.severity,
                message="No budget configured — constraint skipped.",
            )

        budget_f = float(budget)

        if total_cost > budget_f:
            overage = total_cost - budget_f
            return CheckResult(
                check_name=self.name,
                passed=False,
                severity=self.severity,
                message=(
                    f"Over budget by ${overage:,.2f} "
                    f"(plan: ${total_cost:,.2f}, budget: ${budget_f:,.2f})"
                ),
                details={
                    "total_cost": total_cost,
                    "budget": budget_f,
                    "overage": overage,
                },
            )

        remaining = budget_f - total_cost
        return CheckResult(
            check_name=self.name,
            passed=True,
            severity=self.severity,
            message=f"Within budget — ${remaining:,.2f} remaining of ${budget_f:,.2f}.",
            details={"total_cost": total_cost, "budget": budget_f, "remaining": remaining},
        )
