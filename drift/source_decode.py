"""Bounded decoding of HTTP source bodies before evidence extraction."""
from email.message import Message
import zlib


def _decompress(body: bytes, max_bytes: int, wbits: int) -> bytes:
    decoder = zlib.decompressobj(wbits)
    decoded = decoder.decompress(body, max_bytes + 1)
    if len(decoded) > max_bytes:
        raise ValueError("decompressed source exceeds byte limit")
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("malformed or truncated compressed source")
    return decoded


def decode_source(body: bytes, headers, max_bytes: int) -> str:
    if max_bytes < 0:
        raise ValueError("source byte limit must be nonnegative")
    if len(body) > max_bytes:
        raise ValueError("source exceeds byte limit")

    encoding = headers.get("Content-Encoding", "identity").strip().lower()
    try:
        if encoding == "gzip":
            body = _decompress(body, max_bytes, 16 + zlib.MAX_WBITS)
        elif encoding == "deflate":
            try:
                body = _decompress(body, max_bytes, zlib.MAX_WBITS)
            except zlib.error:
                body = _decompress(body, max_bytes, -zlib.MAX_WBITS)
        elif encoding != "identity":
            raise ValueError(f"unsupported source compression: {encoding}")
    except zlib.error as exc:
        raise ValueError("malformed compressed source") from exc

    content_type = Message()
    content_type["Content-Type"] = headers.get("Content-Type", "")
    charset = content_type.get_content_charset("utf-8")
    try:
        return body.decode(charset, errors="strict")
    except (LookupError, UnicodeError) as exc:
        raise ValueError(f"cannot decode source charset: {charset}") from exc
