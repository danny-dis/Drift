"""Entry point — discover Drift organisms, onboard them, and start the service."""

import glob
import json
import logging
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import uvicorn
from drift.brain import Brain
from drift.config import config
from drift.identity import load_identity_from, create_identity
from drift.server import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))


def _organism_id_from_box(box_path: str) -> str:
    dirname = os.path.basename(box_path)
    return dirname[:-4] if dirname.endswith("_box") else dirname


def _discover_organisms() -> dict[str, Brain]:
    """Discover all persisted organisms; legacy crab boxes remain compatible."""
    brains: dict[str, Brain] = {}
    legacy = os.path.join(PROJECT_ROOT, "environment")
    legacy_identity = os.path.join(legacy, "identity.json")
    if os.path.isfile(legacy_identity):
        with open(legacy_identity, "r") as f:
            identity = json.load(f)
        name = identity.get("name", "drift").lower()
        new_path = os.path.join(PROJECT_ROOT, f"{name}_box")
        print(f"\n  Migrating environment/ -> {name}_box/...")
        shutil.move(legacy, new_path)

    boxes = sorted(p for p in glob.glob(os.path.join(PROJECT_ROOT, "*_box")) if os.path.isdir(p))
    for box_path in boxes:
        identity = load_identity_from(box_path)
        if not identity:
            continue
        identity.setdefault("animal", "crab")
        organism_id = _organism_id_from_box(box_path)
        brains[organism_id] = Brain(identity, box_path)
    return brains


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.environ.get("DRIFT_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("DRIFT_PORT", "47116")))
    ap.add_argument("--box", default=os.environ.get("DRIFT_BOX", ""))
    ap.add_argument("--name", default=os.environ.get("DRIFT_NAME", ""))
    args, _ = ap.parse_known_args()

    brains = _discover_organisms()
    # Non-interactive: explicit box/name or existing boxes; never mandate input.
    if args.box:
        os.makedirs(args.box, exist_ok=True)
        from drift.identity import load_identity_from
        ident = load_identity_from(args.box)
        if not ident:
            ident = {"name": args.name or "drift", "animal": "crab"}
            with open(os.path.join(args.box, "identity.json"), "w") as f:
                json.dump(ident, f)
        ident.setdefault("animal", "crab")
        brains[_organism_id_from_box(args.box)] = Brain(ident, args.box)
    elif args.name and not brains:
        box_path = os.path.join(PROJECT_ROOT, f"{args.name.lower()}_box")
        os.makedirs(box_path, exist_ok=True)
        ident = {"name": args.name, "animal": "crab"}
        with open(os.path.join(box_path, "identity.json"), "w") as f:
            json.dump(ident, f)
        brains[args.name.lower()] = Brain(ident, box_path)

    if brains:
        names = [b.identity["name"] for b in brains.values()]
        print(f"\n  Found {len(brains)} Drift organism(s): {', '.join(names)}")
        # Only prompt when interactive AND no explicit flags were given.
        if not args.box and not args.name and sys.stdin.isatty():
            answer = input("  Create a new one? (y/N) > ").strip().lower()
            if answer == "y":
                identity = create_identity()
                identity.setdefault("animal", "crab")
                organism_id = identity["name"].lower()
                box_path = os.path.join(PROJECT_ROOT, f"{organism_id}_box")
                brains[organism_id] = Brain(identity, box_path)
    else:
        if sys.stdin.isatty() and not args.name:
            print("\n  No Drift organisms found. Let's create one!")
            identity = create_identity()
            identity.setdefault("animal", "crab")
            organism_id = identity["name"].lower()
            box_path = os.path.join(PROJECT_ROOT, f"{organism_id}_box")
            brains[organism_id] = Brain(identity, box_path)
        else:
            # Non-interactive default box (existing boxes safe, never touched).
            nm = args.name or "drift"
            box_path = args.box or os.path.join(PROJECT_ROOT, f"{nm.lower()}_box")
            os.makedirs(box_path, exist_ok=True)
            ident = {"name": nm, "animal": "crab"}
            with open(os.path.join(box_path, "identity.json"), "w") as f:
                json.dump(ident, f)
            brains[nm.lower()] = Brain(ident, box_path)

    app = create_app(brains)
    names = [b.identity["name"] for b in brains.values()]
    print(f"\n  Starting {len(brains)} Drift organism(s): {', '.join(names)}")
    print(f"  Open http://{args.host}:{args.port}\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
