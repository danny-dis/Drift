"""Entry point — multi-crab discovery + onboarding + starts the server."""

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))


def _crab_id_from_box(box_path: str) -> str:
    """Derive crab ID from box directory name: coral_box -> coral."""
    dirname = os.path.basename(box_path)
    if dirname.endswith("_box"):
        return dirname[:-4]
    return dirname


def _discover_crabs() -> dict[str, Brain]:
    """Discover all *_box/ dirs, migrate legacy environment/, return brains dict."""
    brains: dict[str, Brain] = {}

    # Migrate legacy environment/ if found
    legacy = os.path.join(PROJECT_ROOT, "environment")
    legacy_identity = os.path.join(legacy, "identity.json")
    if os.path.isfile(legacy_identity):
        with open(legacy_identity, "r") as f:
            identity = json.load(f)
        name = identity.get("name", "crab").lower()
        new_path = os.path.join(PROJECT_ROOT, f"{name}_box")
        print(f"\n  Migrating environment/ -> {name}_box/...")
        shutil.move(legacy, new_path)

    # Scan for *_box/ directories
    pattern = os.path.join(PROJECT_ROOT, "*_box")
    boxes = sorted(p for p in glob.glob(pattern) if os.path.isdir(p))

    for box_path in boxes:
        identity = load_identity_from(box_path)
        if not identity:
            continue
        crab_id = _crab_id_from_box(box_path)
        brain = Brain(identity, box_path)
        brains[crab_id] = brain

    return brains


if __name__ == "__main__":
    # Discover existing crabs
    brains = _discover_crabs()

    if brains:
        names = [b.identity["name"] for b in brains.values()]
        print(f"\n  Found {len(brains)} crab(s): {', '.join(names)}")
        answer = input("  Create a new one? (y/N) > ").strip().lower()
        if answer == "y":
            identity = create_identity()
            crab_id = identity["name"].lower()
            box_path = os.path.join(PROJECT_ROOT, f"{crab_id}_box")
            brain = Brain(identity, box_path)
            brains[crab_id] = brain
    else:
        print("\n  No crabs found. Let's create one!")
        identity = create_identity()
        crab_id = identity["name"].lower()
        box_path = os.path.join(PROJECT_ROOT, f"{crab_id}_box")
        brain = Brain(identity, box_path)
        brains[crab_id] = brain

    # Initialize the app with all brains
    app = create_app(brains)

    names = [b.identity["name"] for b in brains.values()]
    print(f"\n  Starting {len(brains)} crab(s): {', '.join(names)}")
    print(f"  Open http://localhost:8000 to watch them think\n")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
