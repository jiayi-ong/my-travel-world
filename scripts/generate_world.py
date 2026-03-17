"""
CLI script: generate and save a new world instance.

Usage:
    python scripts/generate_world.py --seed 42
    python scripts/generate_world.py --seed 42 --world-id my_world --worlds-root ./worlds
    python scripts/generate_world.py --seed 42 --num-cities 3 --date-range 90
"""
import argparse
import sys
from pathlib import Path

# Add project root to sys.path so travel_world imports work
sys.path.insert(0, str(Path(__file__).parent.parent))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate and save a new Travel World instance.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--seed",
        type=int,
        required=True,
        help="RNG seed for reproducible world generation.",
    )
    parser.add_argument(
        "--world-id",
        type=str,
        default=None,
        help="Explicit world ID. If omitted, auto-generated as world_<seed>_<timestamp>.",
    )
    parser.add_argument(
        "--worlds-root",
        type=str,
        default="./worlds",
        help="Root directory where world subdirectories are stored.",
    )
    parser.add_argument(
        "--num-cities",
        type=int,
        default=10,
        help="Number of cities to generate in the world.",
    )
    parser.add_argument(
        "--date-range",
        type=int,
        default=90,
        help="Number of days of simulation data to generate (flights, events, etc.).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed generation progress.",
    )
    return parser.parse_args()


def main() -> int:
    """
    Entry point for world generation CLI.

    Returns:
        0 on success, 1 on error.
    """
    args = parse_args()

    from travel_world.manager.world_manager import WorldManager

    worlds_root = Path(args.worlds_root)

    config = {
        "num_cities_per_region": args.num_cities,
        "date_range_days": args.date_range,
    }

    if args.verbose:
        print(f"Generating world with seed={args.seed}, num_cities={args.num_cities}, "
              f"date_range={args.date_range} days ...")
        print(f"Worlds root: {worlds_root.resolve()}")

    try:
        manager = WorldManager(worlds_root)
        world_state = manager.create_world(
            seed=args.seed,
            world_id=args.world_id,
            config=config,
        )
    except Exception as exc:
        print(f"ERROR: World generation failed: {exc}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

    # Print summary
    summary = world_state.summary()
    print(f"\nWorld generated successfully!")
    print(f"  world_id  : {summary['world_id']}")
    print(f"  sim_date  : {summary['sim_date']}")
    print(f"  layers    : {list(summary['layers'].keys())}")

    for layer_id, layer_summary in summary["layers"].items():
        if isinstance(layer_summary, dict):
            counts = {k: v for k, v in layer_summary.items()
                      if isinstance(v, int) and k != "layer_id"}
            if counts:
                count_str = ", ".join(f"{k}={v}" for k, v in counts.items())
                print(f"    [{layer_id}] {count_str}")

    # Write stats.json to the world directory
    from travel_world.manager.world_stats import compute_and_save
    world_dir = manager._world_dir(world_state.world_id)
    stats = compute_and_save(world_state, world_dir)
    print(f"  stats     : {world_dir / 'stats.json'}")

    if args.verbose:
        import json
        print("\nFull summary:")
        print(json.dumps(summary, indent=2, default=str))
        print("\nWorld stats:")
        print(json.dumps(stats, indent=2, default=str))

    return 0


if __name__ == "__main__":
    sys.exit(main())
