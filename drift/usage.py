"""Canonical persisted model-call telemetry with honest accounting scopes."""
from drift.runtime_status import call_status


def usage_status(brain):
    value = {
        "available": False,
        "total_calls": None,
        "total_cost": None,
        "failed": None,
        "successful": None,
        "by_capability": None,
        "by_provider": None,
        "calls": None,
        "calls_scope": "current ISO week; admitted attempts include failures and interrupted calls",
        "failures_scope": "lifetime recorded failed attempts in this box",
        "cost_scope": "lifetime known receipt estimates only; not an actual billing total",
        "breakdown_scope": "success, capability and provider breakdowns are not tracked",
    }
    try:
        calls = call_status(brain.env_path)
    except (OSError, ValueError, RuntimeError):
        value["message"] = "Call accounting is unavailable; inference is paused. Saving thoughts is independent."
        return value
    value.update(available=True, total_calls=calls["weekly_calls"],
                 failed=calls["failures"], calls=calls,
                 total_cost=brain.receipts.get_total_estimated_cost())
    return value
