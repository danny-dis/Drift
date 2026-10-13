"""Human-readable model admission, separate from estimated monetary cost."""
from datetime import datetime, timedelta, timezone

from drift.config import config
from drift.providers import CallBudget


def call_status(root, settings=None, now=None):
    settings = config if settings is None else settings
    now = now or datetime.now(timezone.utc)
    state = CallBudget(root).status()
    daily_limit = int(settings.get('daily_max_model_calls', 40))
    weekly_limit = int(settings.get('weekly_max_model_calls', 200))
    reasons, resets = [], []
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    if state['daily_calls'] >= daily_limit:
        reasons.append('daily model-call allowance exhausted')
        resets.append(tomorrow)
    if state['weekly_calls'] >= weekly_limit:
        reasons.append('weekly model-call allowance exhausted')
        resets.append((now + timedelta(days=7 - now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0))
    return {**state, 'daily_limit': daily_limit, 'weekly_limit': weekly_limit,
            'daily_remaining': max(0, daily_limit - state['daily_calls']),
            'weekly_remaining': max(0, weekly_limit - state['weekly_calls']),
            'can_call': not reasons,
            'waiting_reason': '; '.join(reasons),
            'next_admission_at': max(resets).isoformat() if resets else None}


def budget_status(brain):
    monetary = brain.attention.get_status() if hasattr(brain, 'attention') else {}
    try:
        calls = call_status(brain.env_path)
    except (OSError, ValueError, RuntimeError):
        calls = {'can_call': False, 'waiting_reason': 'Model-call accounting needs repair; inference paused.'}
    return {**monetary, 'calls': calls, 'waiting_reason': calls['waiting_reason'],
            'capture_available': True, 'cost_scope': 'monetary estimates; free calls still consume call allowance'}
