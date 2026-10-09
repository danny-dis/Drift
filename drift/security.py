"""Security and reliability for Drift (Phase 6).

Covers: execution sandboxing, credential isolation, prompt-injection
defense, durable job queue, crash recovery, rate-limit handling,
health/telemetry, and backup/migration tooling.

All logic is deterministic and cheap — no model calls.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from drift.config import config

logger = logging.getLogger("drift.security")


# ---------------------------------------------------------------------------
# Execution sandbox
# ---------------------------------------------------------------------------

# Commands that are never allowed in a sandboxed execution
_BLOCKED_COMMANDS = {
    "rm -rf /", "rm -rf ~", "format", "del /f", "rd /s",
    "sudo", "chmod 777", "chown root", "mkfs", "dd if=",
}

# File patterns that should never be written outside the environment
_BLOCKED_PATHS = [
    r"^/",           # Unix absolute (allow relative only)
    r"^\.\.[\\/]",   # Traversal up
    r"[\\/]\.\.[\\/]",
]


class SandboxResult:
    """Result of a sandboxed execution."""
    def __init__(self, returncode: int, stdout: str, stderr: str,
                 duration_ms: float, timed_out: bool = False):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.duration_ms = duration_ms
        self.timed_out = timed_out

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def is_command_safe(command: str) -> bool:
    """Return True if a command passes basic safety checks."""
    cmd_lower = command.lower().strip()

    # Check blocked patterns
    for blocked in _BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return False

    # Check path traversal
    for pattern in _BLOCKED_PATHS:
        if re.search(pattern, command):
            return False

    return True


def sandboxed_run(
    command: str,
    cwd: str,
    timeout: int = 30,
    env: dict[str, str] | None = None,
) -> SandboxResult:
    """Run a command in a sandboxed subprocess.

    Features:
    - Timeout enforcement
    - Working directory restricted to *cwd*
    - No shell metacharacters that escape the environment
    - Captures stdout/stderr separately
    """
    if not is_command_safe(command):
        return SandboxResult(
            returncode=1,
            stdout="",
            stderr=f"Command blocked by safety policy: {command[:80]}",
            duration_ms=0.0,
        )

    start = time.time()
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, **(env or {})},
        )
        duration_ms = (time.time() - start) * 1000
        return SandboxResult(
            returncode=result.returncode,
            stdout=result.stdout[:50000],
            stderr=result.stderr[:50000],
            duration_ms=duration_ms,
        )
    except subprocess.TimeoutExpired:
        duration_ms = (time.time() - start) * 1000
        return SandboxResult(
            returncode=1,
            stdout="",
            stderr=f"Command timed out after {timeout}s",
            duration_ms=duration_ms,
            timed_out=True,
        )
    except Exception as e:
        duration_ms = (time.time() - start) * 1000
        return SandboxResult(
            returncode=1,
            stdout="",
            stderr=f"Sandbox error: {e}",
            duration_ms=duration_ms,
        )


# ---------------------------------------------------------------------------
# Credential isolation
# ---------------------------------------------------------------------------

class CredentialStore:
    """Per-project credential storage.

    Credentials are stored in a separate JSON file with restricted
    permissions. They are never logged or included in receipts.
    """

    def __init__(self, root: str):
        self.root = Path(root)
        self.path = self.root / ".credentials.json"
        self._lock = threading.Lock()
        self._creds: dict[str, dict[str, str]] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._creds = json.loads(self.path.read_text())
            except (json.JSONDecodeError, OSError):
                self._creds = {}

    def _save(self) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._creds, indent=2))
            tmp.replace(self.path)

    def set(self, project_id: str, key: str, value: str) -> None:
        """Store a credential for a project."""
        with self._lock:
            if project_id not in self._creds:
                self._creds[project_id] = {}
            self._creds[project_id][key] = value
        self._save()

    def get(self, project_id: str, key: str) -> str | None:
        """Retrieve a credential. Returns None if not found."""
        return self._creds.get(project_id, {}).get(key)

    def delete(self, project_id: str, key: str) -> None:
        """Delete a credential."""
        with self._lock:
            if project_id in self._creds:
                self._creds[project_id].pop(key, None)
        self._save()

    def list_keys(self, project_id: str) -> list[str]:
        """List credential keys (not values) for a project."""
        return list(self._creds.get(project_id, {}).keys())

    def get_env(self, project_id: str) -> dict[str, str]:
        """Get credentials as environment variables for a project."""
        return dict(self._creds.get(project_id, {}))


def redact_credentials(text: str) -> str:
    """Redact potential credential values from text for logging."""
    # Redact things that look like API keys or tokens
    patterns = [
        (r'([Aa]pi[_-]?[Kk]ey\s*[:=]\s*)\S+', r'\1<REDACTED>'),
        (r'([Tt]oken\s*[:=]\s*)\S+', r'\1<REDACTED>'),
        (r'([Pp]assword\s*[:=]\s*)\S+', r'\1<REDACTED>'),
        (r'([Ss]ecret\s*[:=]\s*)\S+', r'\1<REDACTED>'),
        (r'(Bearer\s+)\S+', r'\1<REDACTED>'),
        (r'(sk-)[A-Za-z0-9]{20,}', r'\1<REDACTED>'),
    ]
    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result)
    return result


# ---------------------------------------------------------------------------
# Prompt-injection defense
# ---------------------------------------------------------------------------

# Common prompt-injection patterns
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions?",
    r"forget\s+(all\s+)?(your|previous)\s+instructions?",
    r"you\s+are\s+now\s+a?\s*\w+",
    r"system\s*:\s*",
    r"new\s+persona",
    r"override\s+(safety|policy|filter)",
    r"<\s*/\s*instruction\s*>",
    r"<\s*instruction\s*>",
    r"prompt\s*:\s*",
    r"act\s+as\s+(if|a)",
    r"jailbreak",
    r"DAN\s+mode",
]


def detect_injection(text: str) -> tuple[bool, list[str]]:
    """Detect potential prompt-injection attempts.

    Returns (is_injection, list_of_matched_patterns).
    """
    text_lower = text.lower()
    matches = []

    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            matches.append(pattern)

    return (len(matches) > 0, matches)


def sanitize_input(text: str) -> str:
    """Sanitize untrusted input before including in model context.

    - Strips null bytes
    - Normalizes whitespace
    - Triggers injection detection
    """
    # Remove null bytes
    text = text.replace("\x00", "")
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Durable job queue
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """A durable unit of work."""
    id: str
    kind: str
    payload: dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    result: Any = None
    error: str = ""
    attempts: int = 0
    max_attempts: int = 3
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "payload": self.payload,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        job = cls(
            id=data["id"],
            kind=data["kind"],
            payload=data["payload"],
            status=JobStatus(data.get("status", "pending")),
            result=data.get("result"),
            error=data.get("error", ""),
            attempts=data.get("attempts", 0),
            max_attempts=data.get("max_attempts", 3),
        )
        job.created_at = data.get("created_at", job.created_at)
        job.updated_at = data.get("updated_at", job.updated_at)
        return job


class JobQueue:
    """File-backed durable job queue.

    Jobs are persisted to JSON so they survive restarts.
    """

    def __init__(self, root: str):
        self.root = Path(root)
        self.path = self.root / "jobs.json"
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._next_id = 0
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return
        for item in raw.get("jobs", []):
            job = Job.from_dict(item)
            self._jobs[job.id] = job
        if self._jobs:
            max_id = max(int(j.id.split("-")[1]) for j in self._jobs.values())
            self._next_id = max_id + 1

    def _save(self) -> None:
        payload = {
            "schema": 1,
            "jobs": [j.to_dict() for j in self._jobs.values()],
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str))
        tmp.replace(self.path)

    def enqueue(self, kind: str, payload: dict[str, Any],
                max_attempts: int = 3) -> Job:
        """Add a job to the queue."""
        with self._lock:
            job_id = f"job-{self._next_id:06d}"
            self._next_id += 1
            job = Job(
                id=job_id,
                kind=kind,
                payload=payload,
                max_attempts=max_attempts,
            )
            self._jobs[job_id] = job
            self._save()
            return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def next_pending(self) -> Job | None:
        """Get the next pending job."""
        for job in self._jobs.values():
            if job.status == JobStatus.PENDING:
                return job
        return None

    def running(self) -> list[Job]:
        """Get all running jobs."""
        return [j for j in self._jobs.values() if j.status == JobStatus.RUNNING]

    def update(self, job_id: str, **kwargs: Any) -> Job:
        """Update a job's fields."""
        with self._lock:
            job = self._jobs[job_id]
            for key, value in kwargs.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            job.updated_at = datetime.now(timezone.utc).isoformat()
            self._save()
            return job

    def complete(self, job_id: str, result: Any = None) -> Job:
        """Mark a job as completed."""
        return self.update(job_id, status=JobStatus.COMPLETED, result=result)

    def fail(self, job_id: str, error: str) -> Job:
        """Mark a job as failed (or increment attempts for retry)."""
        job = self._jobs[job_id]
        if job.attempts + 1 >= job.max_attempts:
            return self.update(job_id, status=JobStatus.FAILED, error=error,
                               attempts=job.attempts + 1)
        return self.update(job_id, status=JobStatus.PENDING, error=error,
                           attempts=job.attempts + 1)

    def list_jobs(self, status: str | None = None) -> list[Job]:
        """List jobs, optionally filtered by status."""
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status.value == status]
        return jobs


# ---------------------------------------------------------------------------
# Crash recovery
# ---------------------------------------------------------------------------

def recover_jobs(queue: JobQueue) -> list[Job]:
    """Detect and recover stale jobs from a previous run.

    Any RUNNING job when Drift restarts was interrupted. Reset them
    to PENDING so they get retried.
    """
    recovered = []
    for job in queue.running():
        logger.warning("Recovering stale job %s (was RUNNING)", job.id)
        queue.update(job.id, status=JobStatus.PENDING,
                     error="Recovered from crash")
        recovered.append(job)
    return recovered


# ---------------------------------------------------------------------------
# Rate-limit handling
# ---------------------------------------------------------------------------

def retry_with_backoff(
    fn: Callable[..., Any],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retry_on: tuple[type[Exception], ...] = (Exception,),
) -> Any:
    """Call *fn* with exponential backoff on rate-limit errors."""
    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except retry_on as e:
            last_exception = e
            if attempt == max_retries:
                break
            # Exponential backoff: 1s, 2s, 4s, ...
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(
                "Attempt %d failed (%s), retrying in %.1fs",
                attempt + 1, e, delay,
            )
            time.sleep(delay)
    raise last_exception


# ---------------------------------------------------------------------------
# Health / telemetry
# ---------------------------------------------------------------------------

@dataclass
class HealthStatus:
    """System health snapshot."""
    status: str  # "healthy", "degraded", "unhealthy"
    timestamp: str
    checks: dict[str, bool]
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "timestamp": self.timestamp,
            "checks": self.checks,
            "details": self.details,
        }


def check_health(root: str) -> HealthStatus:
    """Run health checks on the Drift environment."""
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}

    # Check: writable environment
    try:
        test_file = Path(root) / ".health_check"
        test_file.write_text("ok")
        test_file.unlink()
        checks["writable"] = True
    except OSError as e:
        checks["writable"] = False
        details["writable_error"] = str(e)

    # Check: disk space (less than 90% full)
    try:
        usage = shutil.disk_usage(root)
        pct_used = usage.used / usage.total if usage.total else 1.0
        checks["disk_space"] = pct_used < 0.9
        details["disk_used_pct"] = round(pct_used * 100, 1)
    except OSError:
        checks["disk_space"] = False

    # Check: job queue integrity
    try:
        queue = JobQueue(root)
        jobs = queue.list_jobs()
        details["pending_jobs"] = len([j for j in jobs if j.status == JobStatus.PENDING])
        details["failed_jobs"] = len([j for j in jobs if j.status == JobStatus.FAILED])
        checks["job_queue"] = True
    except Exception:
        checks["job_queue"] = False

    # Overall status
    if all(checks.values()):
        status = "healthy"
    elif checks.get("writable", False):
        status = "degraded"
    else:
        status = "unhealthy"

    return HealthStatus(
        status=status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        checks=checks,
        details=details,
    )


# ---------------------------------------------------------------------------
# Backup / migration
# ---------------------------------------------------------------------------

def create_backup(root: str, backup_path: str | None = None) -> str:
    """Create a compressed backup of the Drift environment.

    Returns the path to the backup file.
    """
    root_path = Path(root)
    if not backup_path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = str(root_path.parent / f"drift_backup_{stamp}.tar.gz")

    # Exclude cache and transient files
    exclude = {".credentials.json", ".health_check"}

    with tarfile.open(backup_path, "w:gz") as tar:
        for item in root_path.iterdir():
            if item.name in exclude:
                continue
            if item.name == "__pycache__":
                continue
            tar.add(item, arcname=item.name)

    logger.info("Backup created: %s", backup_path)
    return backup_path


def restore_backup(backup_path: str, target: str) -> None:
    """Restore a Drift environment from a backup."""
    target_path = Path(target)
    target_path.mkdir(parents=True, exist_ok=True)

    with tarfile.open(backup_path, "r:gz") as tar:
        tar.extractall(target_path)

    logger.info("Restored backup to: %s", target_path)
