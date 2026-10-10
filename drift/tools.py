"""Sandboxed shell — the agent can run commands, but only inside environment/."""

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import urllib.request
from urllib.error import URLError
from urllib.parse import urlparse

from drift.config import config

logger = logging.getLogger("drift.tools")

OLLAMA_WEB_SEARCH_URL = "https://ollama.com/api/web_search"
OLLAMA_WEB_FETCH_URL = "https://ollama.com/api/web_fetch"

# Commands that should never be run (checked as prefixes after stripping)
BLOCKED_PREFIXES = [
    "sudo",
    "su ",
    "rm -rf /",
    "chmod",
    "chown",
    "kill",
    "pkill",
    "curl",
    "wget",
    "nc ",
    "ncat",
    "ssh",
    "scp",
    "sftp",
    "node",
    "ruby",
    "perl",
    "bash",
    "sh ",
    "zsh",
    "export",
    "source",
    "eval",
    "exec",
    "mount",
    "umount",
    "dd ",
    "mkfs",
    "fdisk",
    "apt",
    "brew",
    "npm",
    "yarn",
    "open ",
    "xdg-open",
]

# Path to the Python sandbox wrapper
_SANDBOX = os.path.join(os.path.dirname(__file__), "pysandbox.py")


def safe_join(env_root: str, rel: str) -> str:
    """Scope a relative path inside env_root. Raises on traversal.

    Uses Path.relative_to/commonpath semantics, not string prefix.
    """
    from pathlib import Path
    root = Path(os.path.realpath(env_root))
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise ValueError(f"Blocked: path escapes environment: {rel!r}")
    return str(target)


def shell_available() -> tuple[bool, str]:
    """Shell is disabled by default. Opt-in via config shell_enabled.

    Blocklists are NOT a sandbox — without the pysandbox wrapper present
    we refuse even when enabled (real isolation required).
    """
    if not bool(config.get("shell_enabled", False)):
        return False, "shell is disabled by default (set shell_enabled=true to opt in)"
    if bool(config.get("shell_require_isolation", True)) and not os.path.isfile(_SANDBOX):
        return False, "shell isolation unavailable (pysandbox missing); refusing"
    return True, ""


def _venv_dir(env_root: str) -> str:
    """Path to the crab's virtual environment."""
    return os.path.join(os.path.realpath(env_root), ".venv")


def _venv_python(env_root: str) -> str:
    """Path to the venv's Python interpreter."""
    venv = _venv_dir(env_root)
    if os.name == "nt":
        return os.path.join(venv, "Scripts", "python.exe")
    return os.path.join(venv, "bin", "python")


def _venv_bin(env_root: str) -> str:
    """Path to the venv's bin directory."""
    return os.path.join(_venv_dir(env_root), "bin")


def ensure_venv(env_root: str):
    """Create the crab's venv if it doesn't exist. Called once on startup."""
    venv = _venv_dir(env_root)
    if os.path.isfile(_venv_python(env_root)):
        return
    logger.info(f"Creating crab venv at {venv}...")
    uv = shutil.which("uv")
    if uv:
        subprocess.run(
            [uv, "venv", venv, "--python", sys.executable, "--seed", "pip"],
            capture_output=True,
            timeout=30,
        )
    else:
        subprocess.run(
            [sys.executable, "-m", "venv", venv], capture_output=True, timeout=30
        )
    # Ensure 'python' exists (some venvs only have python3)
    py_bin = os.path.join(venv, "bin")
    python3_path = os.path.join(py_bin, "python3")
    python_path = os.path.join(py_bin, "python")
    if os.path.isfile(python3_path) and not os.path.isfile(python_path):
        try:
            os.symlink("python3", python_path)
        except OSError:
            pass
    logger.info("Crab venv created.")


def _is_safe_command(command: str) -> str | None:
    """Return an error message if the command is unsafe, else None."""
    stripped = command.strip()

    if not stripped:
        return "Blocked: empty command."

    # Block dangerous command prefixes
    for prefix in BLOCKED_PREFIXES:
        if stripped.startswith(prefix):
            return f"Blocked: '{prefix}' commands are not allowed."

    # Block parent directory traversal — check actual path tokens, not content strings.
    # Split on whitespace and strip shell operators to find path-like tokens.
    for token in stripped.split():
        clean = token.lstrip("><=|;&(")
        if clean == ".." or clean.startswith("../") or "/.." in clean:
            return "Blocked: '..' path traversal is not allowed in commands."

    # Block shell escape tricks
    if "`" in stripped:
        return "Blocked: backtick command substitution is not allowed."
    if "$(" in stripped:
        return "Blocked: command substitution $() is not allowed."
    if "${" in stripped:
        return "Blocked: variable expansion ${} is not allowed."
    if "~" in stripped:
        return "Blocked: '~' (home expansion) is not allowed."

    # Block absolute paths — only relative paths from environment/ are allowed.
    # Check each whitespace-separated token; strip leading shell operators.
    # Only flag tokens where / is followed by a word char (actual paths like /usr/bin),
    # not markup like /> or /' or /" which appear in XML/HTML/SVG content.
    import re

    for token in stripped.split():
        clean = token.lstrip("><=|;&(")
        if re.match(r"/[A-Za-z0-9_]", clean) and not clean.startswith("/dev/null"):
            return "Blocked: absolute paths are not allowed. Use relative paths only."

    return None


def _rewrite_python_cmd(command: str, env_root: str) -> str | None:
    """If command is a python invocation, rewrite to run through the sandbox.

    Uses the crab's venv python so installed packages are available.
    Returns the rewritten command, or None if it's not a python command.
    """
    stripped = command.strip()
    if stripped.startswith("python3"):
        rest = stripped[7:]
    elif stripped.startswith("python"):
        rest = stripped[6:]
    else:
        return None
    real_root = os.path.realpath(env_root)
    python = (
        _venv_python(env_root)
        if os.path.isfile(_venv_python(env_root))
        else sys.executable
    )
    return (
        f"{shlex.quote(python)} {shlex.quote(_SANDBOX)} {shlex.quote(real_root)}{rest}"
    )


def _rewrite_script_cmd(command: str, env_root: str) -> str | None:
    """Route ./script.py through sandbox so network etc. is blocked."""
    stripped = command.strip()
    if stripped.startswith("./") and stripped.endswith(".py"):
        script = stripped[2:].split()[0]  # ./foo.py or ./foo.py arg1
        rest = stripped[2 + len(script) :].strip()  # any args after script
        python = (
            _venv_python(env_root)
            if os.path.isfile(_venv_python(env_root))
            else sys.executable
        )
        real_root = os.path.realpath(env_root)
        return f"{shlex.quote(python)} {shlex.quote(_SANDBOX)} {shlex.quote(real_root)} {shlex.quote(script)}{' ' + rest if rest else ''}"
    return None


def _rewrite_pip_cmd(command: str, env_root: str) -> str | None:
    """If command is pip/uv pip, rewrite to use the venv. Returns rewritten cmd or None."""
    stripped = command.strip()
    if stripped.startswith("uv pip "):
        # Route through venv python
        rest = stripped[7:]  # after "uv pip "
        uv = shutil.which("uv") or "uv"
        return f"{shlex.quote(uv)} pip {rest} --python {shlex.quote(_venv_python(env_root))}"
    if stripped.startswith("pip install") or stripped.startswith("pip3 install"):
        # Use venv pip
        return f"{shlex.quote(_venv_python(env_root))} -m pip {stripped[stripped.index('install'):]}"
    return None


def run_command(command: str, env_root: str) -> str:
    """Run a shell command sandboxed to the environment/ folder."""
    ok, reason = shell_available()
    if not ok:
        return f"Blocked: {reason}."
    real_root = os.path.realpath(env_root)

    # Safety check (runs on original command before any rewriting)
    err = _is_safe_command(command)
    if err:
        return err

    # Route python commands through the sandbox wrapper
    rewritten = _rewrite_python_cmd(command, env_root)
    if rewritten is not None:
        command = rewritten

    # Route ./script.py through sandbox (otherwise shebang bypasses pysandbox)
    script_rewritten = _rewrite_script_cmd(command, env_root)
    if script_rewritten is not None:
        command = script_rewritten
    # Route pip/uv pip through the venv
    pip_rewritten = _rewrite_pip_cmd(command, env_root)
    if pip_rewritten is not None:
        command = pip_rewritten

    # Include venv bin in PATH so installed tools are available
    vbin = _venv_bin(env_root)
    venv_path = f"{vbin}:/usr/bin:/bin" if os.path.isdir(vbin) else "/usr/bin:/bin"

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=real_root,
            capture_output=True,
            text=True,
            timeout=60,  # longer timeout for pip installs
            env={
                "HOME": real_root,
                "PATH": venv_path,
                "TMPDIR": real_root,
                "LANG": "en_US.UTF-8",
                "VIRTUAL_ENV": _venv_dir(env_root),
            },
        )

        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += result.stderr

        if not output.strip():
            output = "(no output)"

        # Truncate very long output
        if len(output) > 3000:
            output = output[:3000] + "\n...(truncated)"

        return output

    except subprocess.TimeoutExpired:
        return "Error: command timed out (15s limit)"
    except Exception as e:
        return f"Error: {e}"


def ollama_web_search(query: str, max_results: int = 5) -> str:
    """Call Ollama cloud web search API. Requires OLLAMA_API_KEY."""
    api_key = config.get("ollama_api_key")
    if not api_key:
        return "Error: OLLAMA_API_KEY is required for web search. Get one at https://ollama.com/settings/keys"
    try:
        data = json.dumps(
            {"query": query, "max_results": min(max_results, 10)}
        ).encode()
        req = urllib.request.Request(
            OLLAMA_WEB_SEARCH_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            out = json.loads(resp.read().decode())
        lines = []
        for r in out.get("results", []):
            lines.append(f"**{r.get('title', '')}**")
            lines.append(f"URL: {r.get('url', '')}")
            lines.append(r.get("content", "")[:2000])
            lines.append("")
        return "\n".join(lines).strip()[:8000] or "No results found."
    except URLError as e:
        return f"Error: {e.reason}"
    except Exception as e:
        return f"Error: {e}"


def ollama_web_fetch(url: str) -> str:
    """Call Ollama cloud web fetch API. Requires OLLAMA_API_KEY."""
    api_key = config.get("ollama_api_key")
    if not api_key:
        return "Error: OLLAMA_API_KEY is required for web fetch. Get one at https://ollama.com/settings/keys"
    try:
        data = json.dumps({"url": url}).encode()
        req = urllib.request.Request(
            OLLAMA_WEB_FETCH_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            out = json.loads(resp.read().decode())
        title = out.get("title", "")
        content = out.get("content", "")[:6000]
        return f"**{title}**\n\n{content}" if title else content
    except URLError as e:
        return f"Error: {e.reason}"
    except Exception as e:
        return f"Error: {e}"


def _ip_is_public(ip: str) -> bool:
    """True only for global public IPs. Denies private/loopback/link-local/etc."""
    import ipaddress
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.is_global and not (
        addr.is_private or addr.is_loopback or addr.is_link_local
        or addr.is_multicast or addr.is_reserved or addr.is_unspecified
    )


def _host_resolves_public(host: str, resolver=None) -> bool:
    """Resolve host and require every addr to be public. Injectable for tests."""
    import socket
    try:
        infos = resolver(host) if resolver else socket.getaddrinfo(host, None)
    except Exception:
        return False
    ips = set()
    for info in infos:
        try:
            ips.add(info[4][0])
        except (IndexError, TypeError):
            continue
    if not ips:
        return False
    return all(_ip_is_public(ip.split("%")[0]) for ip in ips)


def _open_public_url(request, timeout):
    """Connect only to the validated IP; no proxy or implicit redirects."""
    import socket
    import ssl
    from http.client import HTTPConnection, HTTPSConnection
    parsed = urlparse(request.full_url)
    host = parsed.hostname
    if not host or parsed.username or parsed.password:
        raise ValueError("URL credentials are not permitted")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    ips = {info[4][0] for info in infos}
    if not ips or not all(_ip_is_public(ip) for ip in ips):
        raise ValueError("URL resolved to non-public address")
    # Socket uses the IP literal, but TLS and Host retain original hostname.
    context = ssl.create_default_context() if parsed.scheme == "https" else None
    connection = (HTTPSConnection(host, port, timeout=timeout, context=context)
                  if context else HTTPConnection(host, port, timeout=timeout))
    def connect():
        sock = socket.create_connection((sorted(ips)[0], port), timeout=timeout)
        try:
            connection.sock = context.wrap_socket(sock, server_hostname=host) if context else sock
        except Exception:
            sock.close()
            raise
    connection.connect = connect
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    try:
        connection.request("GET", path, headers={"Host": parsed.netloc,
            "User-Agent": "Drift/1.0 (research)", "Connection": "close"})
        response = connection.getresponse()
        response._drift_connection = connection
        return response
    except Exception:
        connection.close()
        raise


def fetch_url(url: str, max_chars: int = 12000, timeout: int = 15,
              opener=None, resolver=None) -> str:
    """Fetch a URL safely. Denies SSRF targets, validates redirects,
    caps bytes BEFORE full read, explicit timeout. Network injectable
    via opener/resolver so tests never need real external calls."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "Error: Only http and https URLs are allowed."
    if parsed.username or parsed.password:
        return "Error: URL credentials are not permitted."
    host = parsed.hostname or ""
    if not host or not _host_resolves_public(host, resolver):
        return "Error: URL host is not public (SSRF guard)."
    max_bytes = min(max(4096, max_chars * 4), 1_000_000)
    current = url
    try:
        for _ in range(4):  # initial + up to 3 redirects, each validated
            req = urllib.request.Request(
                current, headers={"User-Agent": "Drift/1.0 (research)"},
            )
            open_fn = opener or (lambda r: _open_public_url(r, timeout))
            resp = open_fn(req)
            try:
                status = getattr(resp, "status", 200) or 200
                if status in (301, 302, 303, 307, 308):
                    nxt = resp.headers.get("Location", "") if hasattr(resp, "headers") else ""
                    if not nxt:
                        return "Error: redirect without Location."
                    from urllib.parse import urljoin
                    current = urljoin(current, nxt)
                    p2 = urlparse(current)
                    if p2.scheme not in ("http", "https"):
                        return "Error: redirect to non-http(s) denied."
                    if not _host_resolves_public(p2.hostname or "", resolver):
                        return "Error: redirect host is not public (SSRF guard)."
                    continue
                if not 200 <= status < 300:
                    return f"Error: HTTP {status}."
                chunks, total = [], 0
                while True:
                    chunk = resp.read(min(65536, max_bytes - total))
                    if not chunk:
                        break
                    if isinstance(chunk, str):
                        chunk = chunk.encode("utf-8", "replace")
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= max_bytes:
                        break
                body = b"".join(chunks).decode("utf-8", errors="replace")
                break
            finally:
                try:
                    resp.close()
                    connection = getattr(resp, "_drift_connection", None)
                    if connection:
                        connection.close()
                except Exception:
                    pass
        else:
            return "Error: too many redirects."

        # Simple HTML-to-text: strip tags, collapse whitespace
        text = re.sub(r"<script[^>]*>.*?</script>", "", body, flags=re.DOTALL | re.I)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        import html
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars] if len(text) > max_chars else text or body[:max_chars]
    except URLError as e:
        return f"Error fetching URL: {e.reason}"
    except Exception as e:
        return f"Error: {e}"


def execute_tool(name: str, arguments: dict, env_root: str) -> str:
    """Run a tool by name."""
    if name == "shell":
        return run_command(arguments["command"], env_root)
    elif name == "fetch_url":
        return fetch_url(arguments.get("url", ""))
    elif name == "web_search":
        return ollama_web_search(
            arguments.get("query", ""),
            arguments.get("max_results", 5),
        )
    elif name == "web_fetch":
        return ollama_web_fetch(arguments.get("url", ""))
    else:
        return f"Unknown tool: {name}"
