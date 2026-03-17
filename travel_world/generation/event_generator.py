"""
Generates events at venue locations within the world's date range.

Events introduce temporal constraints that force agents to plan around
fixed start/end times and capacity limits.

Event templates are loaded from data/fixtures/event_templates.json.
Add entries to that file to introduce new events without modifying code.
"""
import json
import random
from datetime import date, timedelta, datetime as dt
from pathlib import Path

from travel_world.core.entities import Event, Review, RatingsSummary
from travel_world.core.enums import EventCategory, LocationType
from travel_world.layers.base import LayerMeta
from travel_world.layers.event_layer import EventLayer
from travel_world.generation.fixture_loader import FixtureLoader

_TEMPLATES_PATH = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "event_templates.json"


def _load_templates() -> dict[str, list[dict]]:
    """Load event templates from JSON, grouped by category."""
    templates: dict[str, list[dict]] = {}
    with open(_TEMPLATES_PATH, encoding="utf-8") as fh:
        entries = json.load(fh)
    for entry in entries:
        cat = entry["category"].lower()
        templates.setdefault(cat, []).append(entry)
    return templates


class EventGenerator:
    """
    Generates EventLayer with events distributed across city venues.

    Event model:
        Events are generated per city based on config["num_events_per_city"].
        Each event is assigned to a random EventVenue location in the city.
        Dates are distributed across the date range with clustering (festivals
        cluster on weekends; exhibitions span multiple days; concerts are single nights).

    Templates are loaded from data/fixtures/event_templates.json.
    Add new entries to that JSON file to extend the event catalogue — no code change needed.
    """

    def __init__(self, seed: int, config: dict):
        self.rng = random.Random(seed)
        self.config = config
        self.fixture_loader = FixtureLoader(self.rng)
        self._templates = _load_templates()

    def generate(self, world_id: str, meta: LayerMeta, geo_layer) -> EventLayer:
        """Generate events for all cities in geo_layer.

        Template selection is weighted toward each city's dominant_event_categories
        (3× weight), so cities with distinct cultural characters produce distinct
        event mixes. All templates still appear, just proportionally more of the
        dominant categories.
        """
        all_templates = [t for ts in self._templates.values() for t in ts]

        events: dict = {}
        start = date.today()
        days = self.config.get("date_range_days", 90)
        date_range = [(start + timedelta(days=i)).isoformat() for i in range(days)]
        event_idx = 0

        for city in geo_layer.cities.values():
            venues = geo_layer.get_locations_by_type(city.city_id, LocationType.EVENT_VENUE)
            if not venues:
                continue

            # Build per-city weighted template list: dominant categories get 3× weight
            dominant = set(getattr(city, "dominant_event_categories", []))
            if dominant:
                weighted: list[dict] = []
                for t in all_templates:
                    weight = 3 if t["category"].lower() in dominant else 1
                    weighted.extend([t] * weight)
            else:
                weighted = all_templates

            n_events = self.config.get("num_events_per_city", 20)
            for _ in range(n_events):
                event_id = f"event_{world_id}_{event_idx:04d}"
                template = self.rng.choice(weighted)
                event = self._generate_event(event_id, city, venues, date_range, template)
                events[event_id] = event
                event_idx += 1

        return EventLayer(meta, events)

    def _generate_event(self, event_id: str, city, venues: list, date_range: list[str],
                        template: dict | None = None) -> Event:
        """Generate a single event entity using a rich template from JSON."""
        if template is None:
            all_templates = [t for ts in self._templates.values() for t in ts]
            template = self.rng.choice(all_templates)

        cat_key = template["category"].lower()
        try:
            category = EventCategory(cat_key)
        except ValueError:
            category = self.rng.choice(list(EventCategory))
        name = template["name"]
        description = template["description"]
        template_rating = float(template.get("rating", 4.0))

        # Read attraction flags from template (default to regular event behaviour)
        is_attraction = category == EventCategory.ATTRACTION
        requires_booking = bool(template.get("requires_booking", not is_attraction))
        is_all_day_entry = bool(template.get("is_all_day_entry", is_attraction))

        venue = self.rng.choice(venues)
        # Leave at least 3 slots so end_dt stays within range
        start_date = self.rng.choice(date_range[:-3])

        if is_all_day_entry:
            # Attractions open in the morning and close in the evening
            open_hour = self.rng.randint(8, 10)
            close_hour = self.rng.randint(18, 21)
            start_dt = dt.fromisoformat(f"{start_date}T{open_hour:02d}:00:00")
            end_dt = dt.fromisoformat(f"{start_date}T{close_hour:02d}:00:00")
        else:
            start_dt = dt.fromisoformat(
                f"{start_date}T{self.rng.randint(17, 21):02d}:00:00"
            )
            if category == EventCategory.FESTIVAL:
                duration_hours = self.rng.randint(24, 72)
            elif category == EventCategory.MARKET:
                duration_hours = self.rng.randint(6, 12)
            else:
                duration_hours = self.rng.randint(2, 4)
            end_dt = start_dt + timedelta(hours=duration_hours)

        capacity = self.rng.randint(50, 5000)
        if is_attraction and not requires_booking:
            base_price = 0.0  # free-entry attractions
        elif is_attraction:
            base_price = round(self.rng.uniform(5, 30), 2)  # paid attractions are cheaper than events
        else:
            base_price = round(self.rng.uniform(10, 200), 2)
        popularity = round(self.rng.uniform(0.3, 1.0), 2)

        # Assign reviews filtered to matching event category
        raw_reviews = self.fixture_loader.get_reviews("event", self.rng.randint(3, 10), category=cat_key)
        reviews = [Review(**r) for r in raw_reviews]
        ratings = RatingsSummary.from_reviews(reviews)
        # Override aggregate rating with template value (jitter ±0.2) clamped 0–5
        jittered = round(min(5.0, max(0.0, template_rating + self.rng.uniform(-0.2, 0.2))), 1)
        ratings = RatingsSummary(
            average_rating=jittered,
            review_count=ratings.review_count,
            rating_distribution=ratings.rating_distribution,
        )

        return Event(
            event_id=event_id,
            name=name,
            venue_id=venue.location_id,
            city_id=city.city_id,
            category=category,
            start_datetime=start_dt.isoformat(),
            end_datetime=end_dt.isoformat(),
            capacity=capacity,
            base_ticket_price=base_price,
            requires_booking=requires_booking,
            is_all_day_entry=is_all_day_entry,
            popularity=popularity,
            description=description,
            tags=[category.value.lower()],
            ratings=ratings,
            reviews=reviews,
        )
