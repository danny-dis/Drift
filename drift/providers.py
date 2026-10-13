"""LLM provider routing — Responses API (OpenAI) or Chat Completions (everything else)."""

import json
import logging
import os

import httpx
import openai
from drift.config import config

logger = logging.getLogger("drift.providers")

# Max chars of tool result content sent to the model.
# Longer results are truncated to avoid hitting cloud API limits.
MAX_TOOL_CONTENT = 16000

# HARD free-only request contract (DMR-X auto-free). Both body and headers
# are sent; alias alone is never proof. No paid fallback anywhere.
FREE_ONLY_BODY = {"costFilter": "free"}
FREE_ONLY_HEADERS = {
    "X-Cost-Filter": "free",
    "X-Free-Tier-Strategy": "free_only",
}
DECISIONS_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"


def free_only_extra() -> tuple[dict, dict]:
    """Return (extra_body, extra_headers) enforcing HARD free-only."""
    return dict(FREE_ONLY_BODY), dict(FREE_ONLY_HEADERS)


_BUDGET_LOCKS = {}


class CallBudget:
    """Atomic per-organism admission; free/failed attempts count too."""
    FILENAME = "call_budget.json"

    def __init__(self, root: str):
        import threading
        self.root = os.path.realpath(root)
        self.path = os.path.join(self.root, self.FILENAME)
        self._lock = _BUDGET_LOCKS.setdefault(self.root, threading.RLock())
        self.state = {}
        with self._lock:
            self._load()

    def _today(self):
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).date().isoformat()

    def _week(self):
        from datetime import datetime, timezone
        y, week, _ = datetime.now(timezone.utc).isocalendar()
        return f"{y}-W{week:02d}"

    def _load(self):
        self.state = {"day": self._today(), "week": self._week(),
            "daily_calls": 0, "weekly_calls": 0, "daily_tokens": 0,
            "weekly_tokens": 0, "failures": 0, "unreported_usage_calls": 0}
        if os.path.isfile(self.path):
            with open(self.path, encoding="utf-8") as f:
                stored = json.load(f)  # corruption must not reopen admission
            if not isinstance(stored, dict):
                raise RuntimeError("invalid call budget; refusing inference")
            self.state.update(stored)
        for key in ("daily_calls", "weekly_calls", "daily_tokens", "weekly_tokens", "failures", "unreported_usage_calls"):
            value = self.state[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RuntimeError("invalid call budget; refusing inference")
        if self.state["day"] != self._today():
            self.state.update(day=self._today(), daily_calls=0, daily_tokens=0)
        if self.state["week"] != self._week():
            self.state.update(week=self._week(), weekly_calls=0, weekly_tokens=0)

    def _save(self):
        import tempfile
        os.makedirs(self.root, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".budget-", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.state, f)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def _admitted(self):
        return (self.state["daily_calls"] < int(config.get("daily_max_model_calls", 40))
            and self.state["weekly_calls"] < int(config.get("weekly_max_model_calls", 200)))

    def can_call(self):
        with self._lock:
            self._load()
            return self._admitted()

    def reserve(self):
        with self._lock:
            self._load()
            if not self._admitted():
                raise RuntimeError("model-call cap reached (free/failed calls included)")
            self.state["daily_calls"] += 1
            self.state["weekly_calls"] += 1
            self._save()  # reserve before network; crashes cannot erase admission

    def record_call(self, ok, in_tokens=0, out_tokens=0, *, reserved=False, reported=True):
        with self._lock:
            self._load()
            if not reserved:
                self.state["daily_calls"] += 1
                self.state["weekly_calls"] += 1
            if ok:
                tokens = max(0, int(in_tokens)) + max(0, int(out_tokens))
                self.state["daily_tokens"] += tokens
                self.state["weekly_tokens"] += tokens
                self.state["unreported_usage_calls"] += int(not reported)
            else:
                self.state["failures"] += 1
            self._save()

    def status(self):
        with self._lock:
            self._load()
            return dict(self.state)


def _bounded_tokens(requested: int | None) -> int:
    """Bound token caps so a bad config cannot explode cost."""
    try:
        want = int(requested or 0)
    except (TypeError, ValueError):
        want = 0
    cap = int(config.get("max_output_tokens", 1000) or 1000)
    return max(1, min(want or cap, cap, 4000))


def _log_error_response(response: httpx.Response) -> None:
    """Event hook: log 4xx/5xx response body immediately (before retries consume it)."""
    if response.status_code >= 400:
        try:
            response.read()
            body = response.text[:1000] if response.text else "(empty)"
        except Exception:
            body = "(could not read)"
        logger.error(
            "Ollama/API HTTP %s: %s | url=%s",
            response.status_code,
            body,
            str(response.url),
        )


TOOLS = [
    {
        "type": "function",
        "name": "shell",
        "description": (
            "Run a shell command inside your environment folder. "
            "You can use ls, cat, mkdir, mv, cp, touch, echo, tee, find, grep, head, tail, wc, etc. "
            "You can also run Python scripts: 'python script.py' or 'python -c \"code\"'. "
            "Use 'cat > file.txt << EOF' or 'echo ... > file.txt' to write files. "
            "Create folders with mkdir. Organize however you like. "
            "All paths are relative to your environment root."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to run"}
            },
            "required": ["command"],
        },
    },
    {
        "type": "function",
        "name": "respond",
        "description": (
            "Talk to your owner! Use this whenever you hear their voice and want to "
            "reply. After you speak, they might say something back — if they do, "
            "use respond AGAIN to keep the conversation going. You can go back and "
            "forth as many times as you like."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "What you say back to them",
                }
            },
            "required": ["message"],
        },
    },
    {
        "type": "function",
        "name": "fetch_url",
        "description": (
            "Fetch the content of a web page. Use this for research when you need to read "
            "an article, documentation, or any URL. Returns the page content (HTML or text). "
            "Only http and https URLs are allowed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch (must start with http:// or https://)",
                }
            },
            "required": ["url"],
        },
    },
    {
        "type": "function",
        "name": "move",
        "description": (
            "Move to a location in your room. Use this to go where feels natural "
            "for what you're doing — desk for writing, bookshelf for research, "
            "window for pondering, bed for resting."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "enum": [
                        "desk",
                        "bookshelf",
                        "window",
                        "plant",
                        "bed",
                        "rug",
                        "center",
                    ],
                }
            },
            "required": ["location"],
        },
    },
]

# Ollama cloud web search tools — for minimax-m2.5:cloud etc. when OLLAMA_API_KEY is set
OLLAMA_WEB_TOOLS = [
    {
        "type": "function",
        "name": "web_search",
        "description": (
            "Search the web for current information. Use for research, fact-checking, "
            "or finding recent news. Returns titles, URLs, and content snippets."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {
                    "type": "integer",
                    "description": "Max results to return (default 5, max 10)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "web_fetch",
        "description": (
            "Fetch the full content of a specific URL. Use after web_search to read "
            "a page in detail. Returns page title, content, and links."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch (e.g. https://...)",
                }
            },
            "required": ["url"],
        },
    },
]


def _translate_tools_for_completions(tools: list[dict]) -> list[dict]:
    """Convert Responses API tool defs to Chat Completions format.

    Drops web_search_preview (unsupported). Wraps function tools in the
    {"type": "function", "function": {...}} structure Chat Completions expects.
    """
    result = []
    for tool in tools:
        if tool.get("type") != "function":
            continue
        result.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {}),
                },
            }
        )
    return result


def _translate_input_to_messages(
    input_list: list, instructions: str | None
) -> list[dict]:
    """Convert a Responses API input_list to Chat Completions messages.

    Handles:
    - Role-based dicts ({"role": ..., "content": ...}) pass through
    - {"type": "function_call_output", ...} -> {"role": "tool", ...}
    - Multimodal content: input_image -> image_url, input_text -> text
    - Non-dict items (SDK objects from Responses API) are skipped
    - Instructions become a system message at index 0
    """
    messages = []
    if instructions:
        messages.append({"role": "system", "content": instructions})

    for item in input_list:
        if not isinstance(item, dict):
            continue

        if item.get("type") == "function_call_output":
            content = str(item.get("output", ""))
            if len(content) > MAX_TOOL_CONTENT:
                content = content[:MAX_TOOL_CONTENT] + "\n...(truncated)"
            tool_msg = {
                "role": "tool",
                "content": content,
            }
            # v1/chat/completions is OpenAI-compatible; use tool_call_id
            call_id = item.get("call_id")
            if call_id:
                tool_msg["tool_call_id"] = call_id
            # Only Ollama cloud models expect tool_name; Groq rejects it
            if config["provider"] == "custom" and "ollama" in config.get("base_url", ""):
                tool_msg["tool_name"] = item.get("name", "")
            messages.append(tool_msg)
        elif "role" in item:
            content = item.get("content")
            if isinstance(content, list):
                content = _translate_multimodal(content)
            messages.append({**item, "content": content})

    return messages


def _translate_multimodal(content_parts: list[dict]) -> list[dict]:
    """Convert Responses API multimodal content to Chat Completions format."""
    result = []
    for part in content_parts:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "input_image":
            result.append(
                {"type": "image_url", "image_url": {"url": part["image_url"]}}
            )
        elif part.get("type") == "input_text":
            result.append({"type": "text", "text": part["text"]})
        else:
            result.append(part)
    return result


def _normalize_completions_response(response) -> dict:
    """Normalize a Chat Completions response into the same format as _chat_responses.

    Returns {"text", "tool_calls", "output"} where output contains dicts
    that brain.py can safely append to input_list for follow-up calls.
    """
    message = response.choices[0].message
    text = message.content
    tool_calls = []
    output = []

    if message.tool_calls:
        for i, tc in enumerate(message.tool_calls):
            # Ollama may omit id; ensure we have one for tool_call_id in follow-up
            call_id = tc.id or f"call_{tc.function.name}_{i}"
            tool_calls.append(
                {
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                    "call_id": call_id,
                }
            )

        # Build a synthetic assistant message for brain.py's input_list
        output.append(
            {
                "role": "assistant",
                "content": text,
                "tool_calls": [
                    {
                        "id": tc.id or f"call_{tc.function.name}_{i}",
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for i, tc in enumerate(message.tool_calls)
                ],
            }
        )

    return {"text": text, "tool_calls": tool_calls, "output": output}


def _client() -> openai.OpenAI:
    return openai.OpenAI(api_key=config["api_key"], max_retries=0, timeout=max(1.0, min(60.0, float(config.get("model_timeout_seconds", 60)))))


def _uses_responses_api() -> bool:
    """Returns True if the configured provider uses the OpenAI Responses API."""
    return config["provider"] == "openai"


def _completions_client() -> openai.OpenAI:
    """Create an OpenAI client configured for Chat Completions (with base_url)."""
    api_key = config["api_key"]
    if not api_key and config.get("base_url"):
        # Ollama and similar local providers don't need a real key;
        # the SDK requires something, so use a placeholder
        api_key = "ollama"
    kwargs = {"api_key": api_key, "max_retries": 0, "timeout": max(1.0, min(60.0, float(config.get("model_timeout_seconds", 60))))}
    if config.get("base_url"):
        kwargs["base_url"] = config["base_url"]
        # Local/cloud models (Ollama, etc.) can return transient 500s — retry more
        kwargs["max_retries"] = 0
        # Log 500 response bodies immediately (before retries)
        http_client = httpx.Client(
            event_hooks={"response": [_log_error_response]},
        )
        kwargs["http_client"] = http_client
    return openai.OpenAI(**kwargs)


def _chat_responses(
    input_list: list,
    tools: bool = True,
    instructions: str = None,
    max_tokens: int = 300,
) -> dict:
    """
    Make one Responses API call. Returns:
    {
        "text": str or None,
        "tool_calls": [{"name": str, "arguments": dict, "call_id": str}],
        "output": list,   # raw output items (for appending back to input)
    }
    """
    kwargs = {
        "model": config["model"],
        "input": input_list,
        "max_output_tokens": max_tokens,
    }
    if instructions:
        kwargs["instructions"] = instructions
    if tools:
        kwargs["tools"] = TOOLS
    if config.get("free_only", True):
        body, headers = free_only_extra()
        kwargs["extra_body"] = body
        kwargs["extra_headers"] = headers

    with _client() as client:
        response = client.responses.create(**kwargs)

    # Parse output items
    text_parts = []
    tool_calls = []
    for item in response.output:
        if item.type == "message":
            for content in item.content:
                if hasattr(content, "text"):
                    text_parts.append(content.text)
        elif item.type == "function_call":
            tool_calls.append(
                {
                    "name": item.name,
                    "arguments": json.loads(item.arguments),
                    "call_id": item.call_id,
                }
            )

    return {
        "text": "\n".join(text_parts) if text_parts else None,
        "tool_calls": tool_calls,
        "output": response.output,
        "usage": response.usage.model_dump() if response.usage else {},
        "model": response.model,
    }


def _summarize_messages_for_log(messages: list) -> list:
    """Return a safe summary of messages for logging (truncate long content)."""
    out = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content", "")
        if isinstance(content, str) and len(content) > 80:
            content = content[:80] + "..."
        elif isinstance(content, list):
            content = f"[{len(content)} parts]"
        d = {"role": role, "content": str(content)[:100]}
        if m.get("role") == "tool":
            d["tool_name"] = m.get("tool_name", "?")
            d["tool_call_id"] = (
                m.get("tool_call_id", "?")[:20] if m.get("tool_call_id") else None
            )
        if m.get("role") == "assistant" and m.get("tool_calls"):
            d["tool_calls"] = [
                {"name": tc.get("function", {}).get("name")} for tc in m["tool_calls"]
            ]
        out.append(d)
    return out


def _chat_completions(
    input_list: list,
    tools: bool = True,
    instructions: str = None,
    max_tokens: int = 300,
) -> dict:
    """Make a Chat Completions API call. Same return format as _chat_responses."""
    messages = _translate_input_to_messages(input_list, instructions)

    kwargs = {
        "model": config["model"],
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if tools:
        completions_tools = _translate_tools_for_completions(TOOLS)
        if config.get("ollama_api_key") and config["provider"] == "custom":
            ollama_tools = _translate_tools_for_completions(OLLAMA_WEB_TOOLS)
            completions_tools = completions_tools + ollama_tools
        if completions_tools:
            kwargs["tools"] = completions_tools
    if config.get("free_only", True):
        body, headers = free_only_extra()
        kwargs["extra_body"] = body
        kwargs["extra_headers"] = headers

    summary = _summarize_messages_for_log(messages)
    logger.info(
        "chat_completions request: model=%s provider=%s msg_count=%d summary=%s",
        config["model"],
        config["provider"],
        len(messages),
        json.dumps(summary, default=str),
    )
    try:
        with _completions_client() as client:
            response = client.chat.completions.create(**kwargs)
        result = _normalize_completions_response(response)
        result["usage"] = response.usage.model_dump() if response.usage else {}
        result["model"] = response.model
        return result
    except Exception as e:
        body = ""
        for attr in ("response", "http_response", "body"):
            val = getattr(e, attr, None)
            if val is not None:
                if hasattr(val, "text"):
                    body = (val.text or "")[:500]
                    break
                if isinstance(val, str):
                    body = val[:500]
                    break
        logger.exception(
            "chat_completions failed: %s | response_body=%s",
            e,
            body or "(none)",
        )
        raise


def chat(input_list: list, tools: bool = True, instructions: str = None,
         max_tokens: int = 300, *, budget_root: str | None = None) -> dict:
    """One bounded admitted invocation; no SDK retries or paid fallback."""
    _require_free_route()
    budget = CallBudget(budget_root or config.get("environment_path", "."))
    budget.reserve()
    try:
        invoke = _chat_responses if _uses_responses_api() else _chat_completions
        result = invoke(input_list, tools, instructions, _bounded_tokens(max_tokens))
    except Exception:
        budget.record_call(False, reserved=True)
        raise
    usage = result.get("usage") or {}
    in_tokens = usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0
    out_tokens = usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0
    budget.record_call(True, in_tokens, out_tokens, reserved=True, reported=bool(usage))
    return result


def _require_free_route():
    if not config.get("free_only", True):
        return
    from urllib.parse import urlparse
    base = urlparse(config.get("base_url") or "")
    if not (config.get("provider") in ("dmrx", "custom")
            and base.hostname in ("127.0.0.1", "localhost", "::1")
            and base.port == 47113):
        raise RuntimeError("free-only requires the local DMR-X gateway; other providers are not admitted")


def embed(text: str) -> list[float]:
    """Get an embedding vector. Disabled by default (free-only, no paid fallback).

    Returns [] unless config embeddings_enabled is explicitly True.
    Never automatically calls OpenAI embeddings.
    """
    from drift.config import config as cfg

    if not cfg.get("embeddings_enabled", False) or cfg.get("free_only", True):
        return []
    model = cfg.get("embedding_model", "text-embedding-3-small")

    # Try configured provider only; never paid fallback.
    try:
        client = _completions_client() if not _uses_responses_api() else _client()
        response = client.embeddings.create(model=model, input=text)
        return response.data[0].embedding
    except Exception as e:
        logger.warning("embedding unavailable, lexical fallback: %s", str(e)[:120])
        return []


def chat_short(input_list: list, instructions: str = None) -> str:
    """Short LLM call (for importance scoring, reflections) — just returns text, no tools."""
    result = chat(input_list, tools=False, instructions=instructions)
    return result["text"] or ""
