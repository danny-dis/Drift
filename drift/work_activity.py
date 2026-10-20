"""Best-effort, process-local observations; never a source of work or routing."""
from contextlib import contextmanager
from datetime import datetime, timezone
import re
import shlex
from urllib.parse import unquote, urlsplit, urlunsplit

from drift.privacy import redact_text

_SENSITIVE = re.compile(r"(?i)secret|password|token|api[_-]?key|authorization|credential|private[_-]?key|\.env|\bsk-[a-z0-9]|[a-f0-9]{25,}")


def safe_text(value):
    if not isinstance(value, str) or not value or len(value) > 512:
        return None
    decoded = unquote(value)
    if redact_text(decoded) != decoded or _SENSITIVE.search(decoded):
        return None
    return value


def safe_target(value):
    value = safe_text(value)
    if value is None:
        return None
    try:
        if "://" in value:
            url = urlsplit(value)
            if url.scheme not in ("http", "https") or not url.hostname:
                return None
            if url.username or url.password or "\\" in value:
                return None
            url.port  # Reject malformed ports.
            target = urlunsplit((url.scheme, url.netloc, url.path, "", ""))
            return target if re.fullmatch(r"[A-Za-z0-9/:._~%+@!$&()*;,=\[\]-]+", target) else None
        name = value.replace("\\", "/").rsplit("/", 1)[-1]
        return name if name not in (".", "..") and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,127}", name) else None
    except (ValueError, TypeError):
        return None


def tool_activity(name, arguments):
    args = arguments if isinstance(arguments, dict) else {}
    if name in ("fetch_url", "web_fetch", "web_search"):
        return "browsing", args.get("url")  # Never expose search queries.
    if name in ("read_file", "read_document"):
        return "reading", args.get("path")
    if name in ("write_file", "edit_file", "save_document"):
        return "writing", args.get("path")
    if name == "respond":
        return "waiting", None
    if name == "shell" and isinstance(args.get("command"), str):
        try:
            parts = shlex.split(args["command"])
            if len(parts) == 2 and parts[0] in ("cat", "head", "tail", "type"):
                return "reading", parts[1]
        except ValueError:
            pass
    return None, None


def idle():
    return dict(kind="idle", active=False, task_id=None, project_id=None, target=None, at=None)


def record(brain, kind, task=None, target=None, *, active=False):
    try:
        if kind not in ("thinking", "browsing", "writing", "reading", "waiting"):
            return
        identifier = lambda value: value if safe_text(value) and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value) else None
        action = dict(kind=kind, active=bool(active),
                      task_id=identifier(getattr(task, "id", None)),
                      project_id=identifier(getattr(task, "project_id", None)) if task is not None else None,
                      target=safe_target(target), at=datetime.now(timezone.utc).isoformat())
        previous = snapshot(brain)["last_activity"]
        brain._work_activity = {"activity": action if active else idle(),
                                "last_activity": previous if active else action}
    except Exception:
        pass  # Observation must never change execution or checkpoint outcomes.


@contextmanager
def observe(brain, kind=None, task=None, target=None, *, tool=None, arguments=None):
    try:
        if tool is not None:
            kind, target = tool_activity(tool, arguments)
        record(brain, kind, task, target, active=True)
    except Exception:
        kind = None
    try:
        yield
    finally:
        record(brain, kind, task, target)


def snapshot(brain):
    try:
        state = getattr(brain, "_work_activity", None)
        if isinstance(state, dict) and isinstance(state.get("activity"), dict):
            return {key: dict(value) if isinstance(value, dict) else None for key, value in state.items()
                    if key in ("activity", "last_activity")}
    except Exception:
        pass
    return {"activity": idle(), "last_activity": None}
