"""
Loads review and rating fixtures from JSON database files.

Design: Repository pattern — provides a clean interface for accessing
fixture data without callers needing to know the file format or location.

The fixture database is intentionally small at project start (a few dozen
reviews per category) and is designed to be extended by adding entries to
the JSON files without changing any code.
"""
import json
import random
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "fixtures"


class FixtureLoader:
    """
    Loads review/rating fixtures for random assignment to generated locations.

    Fixture files live in data/fixtures/ and are loaded lazily (on first access).
    Each fixture file is a JSON array of Review-compatible dicts.

    Supported fixture types: hotel, attraction, restaurant, event, flight
    """

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self._cache: dict[str, list[dict]] = {}

    def get_reviews(self, fixture_type: str, n: int, category: str | None = None) -> list[dict]:
        """
        Sample n reviews from the fixture database for the given type.

        Rating is computed from positivity (0–1) with a small random jitter so
        different entities assigned the same review template get slightly varied stars.
        Fixtures should have a `positivity` field instead of (or in addition to) `rating`.

        For event reviews, an optional `category` filter narrows the pool to reviews
        whose `event_categories` list is empty (general) or contains the given category.
        This prevents e.g. acoustics reviews being assigned to food events.

        Args:
            fixture_type: One of "hotel", "attraction", "restaurant", "event", "district".
            n: Number of reviews to sample (with replacement if n > available).
            category: Optional event category string (used only when fixture_type=="event").

        Returns:
            List of Review-compatible dicts with keys: reviewer_id, rating, positivity, text, date, tags.
        """
        data = self._load_fixture(fixture_type)
        if not data:
            return []
        # Category-aware pool selection for event reviews
        if category and fixture_type == "event":
            cat_lower = category.lower()
            pool = [
                r for r in data
                if not r.get("event_categories") or cat_lower in r.get("event_categories", [])
            ]
            if len(pool) < 3:  # fallback to full pool if too few match
                pool = data
        else:
            pool = data
        samples = self.rng.choices(pool, k=n)
        result = []
        for entry in samples:
            d = dict(entry)
            positivity = float(d.get("positivity", 0.5))
            # Derive rating from positivity + noise; fixtures no longer need a rating field
            raw = 1.0 + positivity * 4.0 + self.rng.uniform(-0.3, 0.3)
            d["rating"] = round(max(1.0, min(5.0, raw)), 1)
            d.setdefault("positivity", positivity)
            result.append(d)
        return result

    def _load_fixture(self, fixture_type: str) -> list[dict]:
        """Load a fixture file from DATA_DIR and cache it."""
        if fixture_type in self._cache:
            return self._cache[fixture_type]
        path = DATA_DIR / f"{fixture_type}_reviews.json"
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._cache[fixture_type] = data
        return data

    def list_available_types(self) -> list[str]:
        """Return fixture types that have a corresponding JSON file in DATA_DIR."""
        return [p.stem.replace("_reviews", "") for p in DATA_DIR.glob("*_reviews.json")]
