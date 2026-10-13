"""Local saving readiness and an explicit, accounted inference check."""
import asyncio
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import os
from pathlib import Path
import sqlite3

from drift.config import config
from drift.runtime_status import call_status


def _version():
    try:
        return version("drift")
    except PackageNotFoundError:
        return "source checkout"


def setup_status(brain):
    ready = False
    store = getattr(brain, "captures", None)
    try:
        if store is None:
            from drift.capture_store import CaptureStore
            store = CaptureStore(brain.env_path)
        store.list(limit=1)
        ready = True
    except (OSError, sqlite3.Error, ValueError):
        pass
    processing = dict(getattr(brain, "setup_processing", {
        "state": "unchecked",
        "message": "Saving works without AI. Check the connection when you want suggestions.",
        "checked_at": None,
    }))
    try:
        calls = call_status(brain.env_path)
        if not calls["can_call"]:
            processing.update(state="limited", message=calls["waiting_reason"])
    except (OSError, ValueError, RuntimeError):
        processing.update(state="limited", message="Call accounting needs repair. Saving is still separate from AI.")
    processing["model"] = str(config.get("model", ""))
    return {
        "version": _version(),
        "capture_ready": ready,
        "storage_path": str(Path(brain.env_path).resolve()),
        "auth_required": bool(os.environ.get("DRIFT_API_TOKEN")),
        "free_only": bool(config.get("free_only", True)),
        "shell_enabled": bool(config.get("shell_enabled", False)),
        "processing": processing,
    }


async def check_setup(brain):
    from drift import providers
    lock = getattr(brain, "setup_check_lock", None)
    if lock is None:
        lock = brain.setup_check_lock = asyncio.Lock()
    async with lock:
        state = setup_status(brain)
        if state["processing"]["state"] == "limited":
            return state
        checked_at = datetime.now(timezone.utc).isoformat()
        try:
            result = await asyncio.to_thread(
                providers.chat,
                [{"role": "user", "content": "Reply with DRIFT_READY."}],
                tools=False,
                instructions="This is a connection check only. Reply briefly; do not use tools or perform work.",
                max_tokens=24,
                budget_root=brain.env_path,
            )
            if not isinstance(result.get("text"), str) or not result["text"].strip():
                raise ValueError("empty check response")
            brain.setup_processing = {
                "state": "ready", "checked_at": checked_at,
                "message": "AI answered this check. Suggestions remain unverified; future calls may still fail.",
            }
        except Exception:
            brain.setup_processing = {
                "state": "unavailable", "checked_at": checked_at,
                "message": "AI could not answer. Check that your configured gateway is running, then try again. You can still save thoughts.",
            }
        return setup_status(brain)
