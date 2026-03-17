"""
CLI script: compute and print statistics for an existing world instance.

Usage:
    python scripts/compute_world_stats.py --world-id world_42_20260317_231328
    python scripts/compute_world_stats.py --world-id world_42_20260317_231328 --worlds-root ./worlds
    python scripts/compute_world_stats.py --world-id world_42_20260317_231328 --no-save
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute and display statistics for a saved world instance.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--world-id", required=True, help="World ID to analyse.")
    parser.add_argument("--worlds-root", default="./worlds",
                        help="Root directory where world subdirectories are stored.")
    parser.add_argument("--no-save", action="store_true",
                        help="Print stats without writing stats.json.")
    return parser.parse_args()


def main() -> int:
    # Ensure UTF-8 output on Windows terminals
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    from travel_world.manager.world_manager import WorldManager
    from travel_world.manager.world_stats import compute_and_save, compute

    worlds_root = Path(args.worlds_root)
    manager     = WorldManager(worlds_root)

    try:
        ws = manager.load_world(args.world_id)
    except Exception as exc:
        print(f"ERROR: Could not load world '{args.world_id}': {exc}", file=sys.stderr)
        return 1

    if args.no_save:
        stats = compute(ws)
    else:
        world_dir = manager._world_dir(args.world_id)
        stats     = compute_and_save(ws, world_dir)
        print(f"stats.json written to: {world_dir / 'stats.json'}\n")

    _print_stats(stats)
    return 0


def _print_stats(stats: dict) -> None:
    """Pretty-print the stats dict in a human-readable table format."""
    wid = stats.get("world_id", "?")
    print(f"{'─' * 56}")
    print(f"  World Stats — {wid}")
    print(f"{'─' * 56}")

    geo = stats.get("geo", {})

    # Cities
    c = geo.get("cities", {})
    print(f"\n📍 CITIES  ({c.get('count', 0)} total)")
    print(f"   Avg safety score   : {c.get('avg_safety_score')}")
    print(f"   Avg tourism density: {c.get('avg_tourism_density')}")
    print(f"   With vibe summary  : {c.get('cities_with_vibe_summary')}")
    _print_dist("   Economic tiers", c.get("economic_tier_distribution", {}))
    _print_dist("   Climate zones ", c.get("climate_zone_distribution", {}))
    _print_dist("   Top cuisines  ", c.get("dominant_cuisine_counts", {}), top=5)
    _print_dist("   Top event cats", c.get("dominant_event_cat_counts", {}), top=5)

    # Districts
    d = geo.get("districts", {})
    print(f"\n🏘  DISTRICTS  ({d.get('count', 0)} total)")
    print(f"   Avg safety score: {d.get('avg_safety_score')}")
    print(f"   Avg walkability : {d.get('avg_walkability')}")
    print(f"   Avg cost index  : {d.get('avg_cost_index')}")
    print(f"   Total reviews   : {d.get('total_reviews')}")
    _print_dist("   Types", d.get("type_distribution", {}))

    # Hotels
    h = geo.get("hotels", {})
    print(f"\n🏨 HOTELS  ({h.get('count', 0)} total,  {h.get('total_rooms', 0)} rooms)")
    print(f"   Avg price/night : ${h.get('avg_price_per_night')}")
    print(f"   Avg rating      : {h.get('avg_rating')}")
    print(f"   Total reviews   : {h.get('total_reviews')}")
    print(f"   With shuttle    : {h.get('hotels_with_shuttle')}")
    _print_dist("   Stars      ", h.get("star_distribution", {}))
    _print_dist("   Top amenities", h.get("amenity_counts", {}), top=8)

    # Restaurants
    r = geo.get("restaurants", {})
    print(f"\n🍽  RESTAURANTS  ({r.get('count', 0)} total)")
    print(f"   Avg spend/person     : ${r.get('avg_spend')}")
    print(f"   Avg rating           : {r.get('avg_rating')}")
    print(f"   Total reviews        : {r.get('total_reviews')}")
    print(f"   Michelin starred     : {r.get('michelin_starred')}")
    print(f"   Reservation required : {r.get('reservation_required')}")
    _print_dist("   Top cuisines", r.get("cuisine_counts", {}), top=8)
    _print_dist("   Hours pattern", r.get("opening_hour_patterns", {}))

    # Attractions
    a = geo.get("attractions", {})
    print(f"\n🏛  ATTRACTIONS  ({a.get('count', 0)} total)")
    print(f"   Free entry      : {a.get('free_entry_count')}")
    print(f"   Avg ticket price: ${a.get('avg_ticket_price')}")
    print(f"   Avg duration    : {a.get('avg_duration_hours')} hrs")
    _print_dist("   Categories", a.get("category_distribution", {}))

    # Events
    ev = stats.get("events", {})
    print(f"\n🎭 EVENTS  ({ev.get('total', 0)} total)")
    print(f"   Free events    : {ev.get('free_events')}")
    print(f"   All-day entry  : {ev.get('all_day_entry')}")
    print(f"   Avg ticket     : ${ev.get('avg_ticket_price')}")
    print(f"   Avg popularity : {ev.get('avg_popularity')}")
    print(f"   Avg rating     : {ev.get('avg_rating')}")
    print(f"   Total reviews  : {ev.get('total_reviews')}")
    print(f"   Total capacity : {ev.get('total_capacity', 0):,}")
    _print_dist("   Categories", ev.get("category_distribution", {}))

    # Transport
    t = geo.get("transport", {})
    print(f"\n✈  TRANSPORT  ({t.get('total_edges', 0)} total edges)")
    print(f"   Flight routes  : {t.get('flight_routes_total')}  "
          f"(direct: {t.get('flight_routes_direct')}, "
          f"connecting: {t.get('flight_routes_connecting')})")
    print(f"   Unique city pairs: {t.get('unique_city_pairs')}")
    _print_dist("   By mode", t.get("by_mode", {}))

    # Reviews summary
    rv = stats.get("reviews", {})
    print(f"\n⭐ REVIEWS  ({rv.get('total_reviews_all_entities', 0)} total)")
    for etype in ("hotel", "restaurant", "attraction", "event", "district"):
        er = rv.get(etype, {})
        if er:
            print(f"   {etype:<12}  n={er.get('entities'):>4}  "
                  f"reviews={er.get('total_reviews'):>5}  "
                  f"avg/entity={er.get('avg_reviews_per_entity'):>4}  "
                  f"avg_rating={er.get('avg_rating')}")

    print(f"\n{'─' * 56}\n")


def _print_dist(label: str, dist: dict, top: int | None = None) -> None:
    if not dist:
        return
    items = sorted(dist.items(), key=lambda x: -x[1])
    if top:
        items = items[:top]
    parts = ", ".join(f"{k}: {v}" for k, v in items)
    print(f"   {label.ljust(18)}: {parts}")


if __name__ == "__main__":
    sys.exit(main())
