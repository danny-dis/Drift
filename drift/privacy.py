"""Credential redaction for inference-only views; originals remain untouched."""
import json
import re


_ASSIGNMENT = re.compile(
    r'''(?:api[_ -]?key|token|password|secret)["']?\s*[:=]\s*(?P<value>"(?:\\.|[^"\\])*(?:"|$)|'(?:\\.|[^'\\])*(?:'|$)|[^\s,;"'}]+)''',
    re.IGNORECASE,
)
_PATTERNS = tuple(re.compile(pattern) for pattern in (
    r'(?i)\bBearer\s+\S+|\bsk-[a-zA-Z0-9_-]{12,}',
    r'\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b',
    r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    r'-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----',
    r'(?<![A-Za-z0-9+/])(?=[A-Za-z0-9+/]{40}(?![A-Za-z0-9+/]))(?=[A-Za-z0-9+/]*[A-Za-z])(?=[A-Za-z0-9+/]*[0-9+/])[A-Za-z0-9+/]{40}',
))
_SENSITIVE_KEY = re.compile(r'^(?:api[_ -]?key|token|password|secret|authorization)$', re.IGNORECASE)


def credential_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    for match in _ASSIGNMENT.finditer(text):
        start, end = match.span('value')
        if text[start] in ('"', "'"):
            quote = text[start]
            start += 1
            if end > start and text[end - 1] == quote:
                end -= 1
        spans.append((start, end))
    for pattern in _PATTERNS:
        spans.extend(match.span() for match in pattern.finditer(text))
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def redact_slice(text: str, start: int = 0, end: int | None = None) -> str:
    end = len(text) if end is None else min(len(text), end)
    cursor, pieces = start, []
    for left, right in credential_spans(text):
        if right <= start or left >= end:
            continue
        left, right = max(left, start), min(right, end)
        pieces.extend((text[cursor:left], '[REDACTED]'))
        cursor = right
    pieces.append(text[cursor:end])
    return ''.join(pieces)


def redact_text(text: str) -> str:
    return redact_slice(text)


def redact_value(value):
    if isinstance(value, str):
        try:
            structured = json.loads(value)
        except (ValueError, RecursionError):
            structured = None
        if isinstance(structured, (dict, list)):
            return json.dumps(redact_value(structured), ensure_ascii=False)
        return redact_text(value)
    if isinstance(value, dict):
        return {key: '[REDACTED]' if isinstance(item, str) and _SENSITIVE_KEY.fullmatch(str(key))
                else redact_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    return value
