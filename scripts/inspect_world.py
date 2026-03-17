"""
CLI script: print a summary of an existing world instance.

Usage:
    python scripts/inspect_world.py --world-id world_42
    python scripts/inspect_world.py --world-id world_42 --layer geo
"""
import argparse
import sys
from pathlib import Path

# Add project root to sys.path so travel_world imports work
sys.path.insert(0, str(Path(__file__).parent.parent))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect and summarize an existing Travel World instance.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--world-id",
        type=str,
        required=True,
        help="ID of the world to inspect (subdirectory name under worlds-root).",
    )
    parser.add_argument(
        "--worlds-root",
        type=str,
        default="./worlds",
        help="Root directory where world subdirectories are stored.",
    )
    parser.add_argument(
        "--layer",
        type=str,
        default=None,
        help="Inspect a specific layer only (e.g. geo, accommodation, event).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output the summary as formatted JSON instead of a human-readable table.",
    )
    return parser.parse_args()


def _print_table(summary: dict) -> None:
    """Pretty-print world summary as a human-readable table."""
    print(f"\n{'='*60}")
    print(f"  World ID  : {summary.get('world_id', 'N/A')}")
    print(f"  Sim Date  : {summary.get('sim_date', 'N/A')}")
    print(f"  Composed  : {summary.get('composed_at', 'N/A')}")
    print(f"{'='*60}")

    layers = summary.get("layers", {})
    if not layers:
        print("  No layers loaded.")
        return

    for layer_id, layer_summary in layers.items():
        print(f"\n  Layer: {layer_id}")
        print(f"  {'-'*40}")
        if isinstance(layer_summary, dict):
            for key, value in layer_summary.items():
                if key == "layer_id":
                    continue
                if isinstance(value, (int, float, str, bool)):
                    print(f"    {key:<30}: {value}")
                elif isinstance(value, list):
                    print(f"    {key:<30}: [{len(value)} items]")
                elif isinstance(value, dict):
                    print(f"    {key:<30}: {{{len(value)} keys}}")
                else:
                    print(f"    {key:<30}: {value}")
        else:
            print(f"    {layer_summary}")

    print(f"\n{'='*60}\n")


def main() -> int:
    args = parse_args()

    from travel_world.manager.world_manager import WorldManager

    worlds_root = Path(args.worlds_root)

    layer_ids = [args.layer] if args.layer else None

    try:
        manager = WorldManager(worlds_root)
        world_state = manager.load_world(args.world_id, layer_ids=layer_ids)
    except Exception as exc:
        print(f"ERROR: Could not load world '{args.world_id}': {exc}", file=sys.stderr)
        return 1

    summary = world_state.summary()

    if args.output_json:
        import json
        print(json.dumps(summary, indent=2, default=str))
    else:
        _print_table(summary)

    return 0


if __name__ == "__main__":
    sys.exit(main())
