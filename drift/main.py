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
from drift.context_guard import install as install_context_guard
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
        # Existing identities are upgraded lazily; no data migration is required.
        identity.setdefault("animal", "crab")
        organism_id = _organism_id_from_box(box_path)
        brains[organism_id] = Brain(identity, box_path)
    return brains


# Install the context boundary before any Brain instance starts thinking.
install_context_guard(Brain)

if __name__ == "__main__":
    brains = _discover_organisms()

    if brains:
        names = [b.identity["name"] for b in brains.values()]
        print(f"\n  Found {len(brains)} Drift organism(s): {', '.join(names)}")
        answer = input("  Create a new one? (y/N) > ").strip().lower()
        if answer == "y":
            identity = create_identity()
            identity.setdefault("animal", "crab")
            organism_id = identity["name"].lower()
            box_path = os.path.join(PROJECT_ROOT, f"{organism_id}_box")
            brains[organism_id] = Brain(identity, box_path)
    else:
        print("\n  No Drift organisms found. Let's create one!")
        identity = create_identity()
        identity.setdefault("animal", "crab")
        organism_id = identity["name"].lower()
        box_path = os.path.join(PROJECT_ROOT, f"{organism_id}_box")
        brains[organism_id] = Brain(identity, box_path)

    app = create_app(brains)
    names = [b.identity["name"] for b in brains.values()]
    print(f"\n  Starting {len(brains)} Drift organism(s): {', '.join(names)}")
    print("  Open http://localhost:8000\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
