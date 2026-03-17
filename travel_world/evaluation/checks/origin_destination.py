"""Check that the itinerary starts and ends in the configured origin/destination cities."""
from travel_world.evaluation.base import CheckResult, ItineraryCheck, Severity


class OriginDestinationCheck(ItineraryCheck):
    """
    Verifies the first flight departs from the origin city and the last flight
    arrives at the destination city as configured in Trip Setup.
    """
    name = "Origin/Destination Continuity"
    severity = Severity.WARNING

    def run(self, plan: dict, prefs: dict, context: dict) -> CheckResult:
        origin = prefs.get("origin_city_id", "")
        dest_list = prefs.get("destination_city_ids", [])
        dest = dest_list[0] if dest_list else prefs.get("destination_city_id", "")
        city_labels: dict = context.get("city_labels", {})

        items = plan.get("items", [])
        flights = [i for i in items if i.get("item_type") == "flight"]

        if not flights:
            return CheckResult(
                check_name=self.name,
                passed=False,
                severity=self.severity,
                message="No flights in itinerary — cannot verify origin/destination continuity.",
                details={"expected_origin": origin, "expected_destination": dest},
            )

        # Sort by departure datetime
        def _dep(f):
            m = f.get("metadata", {}) or {}
            return m.get("departure_datetime", f.get("date", ""))

        flights_sorted = sorted(flights, key=_dep)
        first_meta = flights_sorted[0].get("metadata", {}) or {}
        last_meta = flights_sorted[-1].get("metadata", {}) or {}
        first_origin = first_meta.get("origin_city_id", "")
        last_dest = last_meta.get("destination_city_id", "")

        def _label(city_id: str) -> str:
            return city_labels.get(city_id, city_id) if city_id else "(unknown)"

        issues = []
        if origin and first_origin and first_origin != origin:
            issues.append(
                f"First flight departs from {_label(first_origin)}, expected {_label(origin)}"
            )
        if dest and last_dest and last_dest != dest:
            issues.append(
                f"Last flight arrives at {_label(last_dest)}, expected {_label(dest)}"
            )

        if issues:
            return CheckResult(
                check_name=self.name,
                passed=False,
                severity=self.severity,
                message="; ".join(issues),
                details={
                    "expected_origin": origin,
                    "expected_destination": dest,
                    "actual_first_origin": first_origin,
                    "actual_last_destination": last_dest,
                },
            )

        return CheckResult(
            check_name=self.name,
            passed=True,
            severity=self.severity,
            message=(
                f"Itinerary correctly starts in {_label(origin)} "
                f"and ends in {_label(dest)}."
            ),
        )
