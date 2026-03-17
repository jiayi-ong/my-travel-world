"""
Compute summary statistics for a generated world and write them to stats.json.

Called automatically by generate_world.py after every successful generation.
Can also be run standalone via scripts/compute_world_stats.py.

Covers:
    Geographic layer  — cities, districts, locations by type, amenities,
                        cuisines, transport edges by mode
    Event layer       — events by category, pricing, all-day entries
    Accommodation     — availability slots
    Reviews           — counts and average ratings by entity type
"""
import json
from collections import Counter
from pathlib import Path
from typing import Any

STATS_FILENAME = "stats.json"


# ── Public API ────────────────────────────────────────────────────────────────

def compute_and_save(world_state, world_dir: Path) -> dict:
    """
    Compute full statistics for *world_state* and write stats.json to *world_dir*.

    Returns the stats dict so the caller can print / log it.
    """
    stats = compute(world_state)
    out_path = world_dir / STATS_FILENAME
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(stats, fh, indent=2, default=str)
    return stats


def compute(world_state) -> dict:
    """Return a plain dict of world statistics (no I/O)."""
    stats: dict[str, Any] = {
        "world_id": world_state.world_id,
        "sim_date": str(world_state.sim_date),
    }
    stats["geo"]           = _geo_stats(world_state)
    stats["events"]        = _event_stats(world_state)
    stats["accommodation"] = _accommodation_stats(world_state)
    stats["reviews"]       = _review_stats(world_state)
    return stats


# ── Layer-level helpers ───────────────────────────────────────────────────────

def _geo_stats(ws) -> dict:
    try:
        geo = ws.get_layer("geo")
    except Exception:
        return {}

    # ── Cities ────────────────────────────────────────────────────────────
    cities = list(geo.cities.values())
    city_stats: dict[str, Any] = {
        "count": len(cities),
        "economic_tier_distribution": dict(Counter(c.economic_tier for c in cities)),
        "climate_zone_distribution":  dict(Counter(c.climate_zone.value for c in cities)),
        "avg_safety_score":           _avg(c.safety_score for c in cities),
        "avg_tourism_density":        _avg(c.tourism_density for c in cities),
        "cities_with_vibe_summary":   sum(1 for c in cities if c.vibe_summary),
        "dominant_cuisine_counts":    dict(
            Counter(cuisine for c in cities for cuisine in c.dominant_cuisines)
        ),
        "dominant_event_cat_counts":  dict(
            Counter(cat for c in cities for cat in c.dominant_event_categories)
        ),
    }

    # ── Districts ─────────────────────────────────────────────────────────
    districts = list(geo.districts.values())
    dist_stats: dict[str, Any] = {
        "count": len(districts),
        "type_distribution": dict(Counter(d.district_type.value for d in districts)),
        "avg_safety_score":  _avg(d.safety_score for d in districts),
        "avg_walkability":   _avg(d.walkability_score for d in districts),
        "avg_cost_index":    _avg(d.cost_index for d in districts),
        "total_reviews":     sum(len(d.reviews) for d in districts),
    }

    # ── Locations ─────────────────────────────────────────────────────────
    locations = list(geo.locations.values())
    by_type   = _group_by(locations, lambda l: l.location_type.value)

    hotels      = by_type.get("hotel", [])
    restaurants = by_type.get("restaurant", [])
    attractions = by_type.get("attraction", [])
    venues      = by_type.get("event_venue", [])
    hubs        = by_type.get("transport_hub", [])

    hotel_stats: dict[str, Any] = {
        "count":              len(hotels),
        "star_distribution":  dict(Counter(h.star_rating for h in hotels)),
        "amenity_counts":     dict(Counter(
            a.value for h in hotels for a in h.amenities
        )),
        "avg_price_per_night": _avg(h.price_per_night for h in hotels),
        "hotels_with_shuttle": sum(1 for h in hotels if h.airport_shuttle),
        "total_rooms":         sum(h.total_rooms for h in hotels),
        "total_reviews":       sum(len(h.reviews) for h in hotels),
        "avg_rating":          _avg(
            h.ratings.average_rating for h in hotels if h.ratings and h.ratings.review_count
        ),
    }

    restaurant_stats: dict[str, Any] = {
        "count":              len(restaurants),
        "cuisine_counts":     dict(Counter(
            c for r in restaurants for c in r.cuisine_types
        )),
        "michelin_starred":   sum(1 for r in restaurants if r.michelin_stars > 0),
        "michelin_distribution": dict(Counter(
            r.michelin_stars for r in restaurants if r.michelin_stars > 0
        )),
        "avg_spend":          _avg(r.average_spend for r in restaurants),
        "reservation_required": sum(1 for r in restaurants if r.reservation_required),
        "total_reviews":      sum(len(r.reviews) for r in restaurants),
        "avg_rating":         _avg(
            r.ratings.average_rating for r in restaurants if r.ratings and r.ratings.review_count
        ),
        "opening_hour_patterns": _opening_hour_patterns(restaurants),
    }

    attraction_stats: dict[str, Any] = {
        "count":             len(attractions),
        "category_distribution": dict(Counter(a.category.value for a in attractions)),
        "free_entry_count":  sum(1 for a in attractions if a.free_entry),
        "avg_ticket_price":  _avg(a.ticket_price for a in attractions if not a.free_entry),
        "avg_duration_hours": _avg(a.duration_hours for a in attractions),
    }

    # ── Transport edges ───────────────────────────────────────────────────
    edges       = list(geo.transport_edges.values())
    edge_by_mode = _group_by(edges, lambda e: e.mode.value)
    flight_edges = edge_by_mode.get("flight", [])
    direct_flights    = sum(1 for e in flight_edges if e.metadata.get("is_direct", True))
    connecting_flights = len(flight_edges) - direct_flights

    transport_stats: dict[str, Any] = {
        "total_edges":       len(edges),
        "by_mode":           {m: len(es) for m, es in edge_by_mode.items()},
        "flight_routes_total":   len(flight_edges),
        "flight_routes_direct":  direct_flights,
        "flight_routes_connecting": connecting_flights,
        "unique_city_pairs":  len({
            (e.metadata.get("origin_city_id"), e.metadata.get("destination_city_id"))
            for e in flight_edges
            if e.metadata.get("origin_city_id")
        }),
    }

    return {
        "cities":      city_stats,
        "districts":   dist_stats,
        "hotels":      hotel_stats,
        "restaurants": restaurant_stats,
        "attractions": attraction_stats,
        "event_venues": {"count": len(venues)},
        "transport_hubs": {"count": len(hubs)},
        "transport":   transport_stats,
    }


def _event_stats(ws) -> dict:
    try:
        evlyr = ws.get_layer("event")
        events = list(evlyr._events.values())
    except Exception:
        return {}

    return {
        "total":              len(events),
        "category_distribution": dict(Counter(e.category.value for e in events)),
        "free_events":        sum(1 for e in events if e.base_ticket_price == 0),
        "all_day_entry":      sum(1 for e in events if e.is_all_day_entry),
        "requires_booking":   sum(1 for e in events if e.requires_booking),
        "avg_ticket_price":   _avg(e.base_ticket_price for e in events if e.base_ticket_price > 0),
        "avg_popularity":     _avg(e.popularity for e in events),
        "total_capacity":     sum(e.capacity for e in events),
        "total_reviews":      sum(len(e.reviews) for e in events),
        "avg_rating":         _avg(
            e.ratings.average_rating for e in events if e.ratings and e.ratings.review_count
        ),
    }


def _accommodation_stats(ws) -> dict:
    try:
        acc = ws.get_layer("accommodation")
        return {
            "hotels_with_availability": len(acc._availability),
            "total_availability_slots": sum(
                len(slots) for slots in acc._availability.values()
            ),
        }
    except Exception:
        return {}


def _review_stats(ws) -> dict:
    """Aggregate review counts and average ratings across all reviewable entities."""
    try:
        geo = ws.get_layer("geo")
    except Exception:
        return {}

    summary: dict[str, dict] = {}
    entity_groups = {
        "hotel":      [l for l in geo.locations.values() if l.location_type.value == "hotel"],
        "restaurant": [l for l in geo.locations.values() if l.location_type.value == "restaurant"],
        "attraction": [l for l in geo.locations.values() if l.location_type.value == "attraction"],
        "district":   list(geo.districts.values()),
    }

    try:
        evlyr = ws.get_layer("event")
        entity_groups["event"] = list(evlyr._events.values())
    except Exception:
        pass

    total_reviews = 0
    for etype, entities in entity_groups.items():
        counts   = [len(e.reviews) for e in entities]
        total    = sum(counts)
        total_reviews += total
        ratings  = [
            e.ratings.average_rating
            for e in entities
            if hasattr(e, "ratings") and e.ratings and e.ratings.review_count
        ]
        summary[etype] = {
            "entities": len(entities),
            "total_reviews": total,
            "avg_reviews_per_entity": round(total / len(entities), 2) if entities else 0,
            "avg_rating": round(sum(ratings) / len(ratings), 3) if ratings else None,
        }

    summary["total_reviews_all_entities"] = total_reviews
    return summary


# ── Utility helpers ───────────────────────────────────────────────────────────

def _avg(iterable) -> float | None:
    vals = [v for v in iterable if v is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def _group_by(items: list, key_fn) -> dict:
    groups: dict = {}
    for item in items:
        k = key_fn(item)
        groups.setdefault(k, []).append(item)
    return groups


def _opening_hour_patterns(restaurants: list) -> dict[str, int]:
    """Classify each restaurant's opening hours into a named pattern."""
    patterns: Counter = Counter()
    for r in restaurants:
        hours = r.opening_hours or {}
        open_days = [v for v in hours.values() if v]
        if not open_days:
            patterns["closed"] += 1
            continue
        sample = open_days[0]
        if sample.startswith("07") or sample.startswith("08"):
            patterns["breakfast_brunch"] += 1
        elif sample.startswith("20") or sample.startswith("21"):
            patterns["late_night"] += 1
        elif sample.startswith("17") or sample.startswith("18"):
            patterns["dinner_only"] += 1
        elif sample.endswith("15:30") or sample.endswith("16:00"):
            patterns["lunch_only"] += 1
        else:
            patterns["full_day"] += 1
    return dict(patterns)
