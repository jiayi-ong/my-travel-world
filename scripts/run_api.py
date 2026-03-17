"""
CLI script: launch the FastAPI backend with uvicorn.

Usage:
    python scripts/run_api.py
    python scripts/run_api.py --port 8080 --reload
    python scripts/run_api.py --worlds-root /path/to/worlds
"""
import argparse
import os
import sys
from pathlib import Path

# Add project root to sys.path so travel_world imports work
sys.path.insert(0, str(Path(__file__).parent.parent))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch the Travel World FastAPI backend server.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host address to bind the server to.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port number to listen on.",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable hot-reload for development (watches source files for changes).",
    )
    parser.add_argument(
        "--worlds-root",
        type=str,
        default="./worlds",
        help="Root directory where world subdirectories are stored.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # Set env var so app.py and dependencies can read it
    worlds_root_abs = str(Path(args.worlds_root).resolve())
    os.environ["WORLDS_ROOT"] = worlds_root_abs

    print(f"Starting Travel World API server...")
    print(f"  Host        : {args.host}")
    print(f"  Port        : {args.port}")
    print(f"  Reload      : {args.reload}")
    print(f"  Worlds root : {worlds_root_abs}")
    print(f"  Docs        : http://{args.host if args.host != '0.0.0.0' else 'localhost'}:{args.port}/docs")

    try:
        import uvicorn
    except ImportError:
        print("ERROR: uvicorn is not installed. Run: pip install uvicorn", file=sys.stderr)
        return 1

    uvicorn.run(
        "travel_world.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
