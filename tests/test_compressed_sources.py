"""Compressed source bodies must become bounded, readable evidence."""
import gzip
import io
import zlib

import pytest

from drift import tools
from drift.source_decode import decode_source


SENTENCE = "Errors detected during execution are called exceptions."
PAGE = f"<html><body><p>{SENTENCE}</p></body></html>".encode()


class Response:
    status = 200

    def __init__(self, body, headers):
        self.body = io.BytesIO(body)
        self.headers = headers
        self.closed = False
        self.read_sizes = []

    def read(self, size):
        self.read_sizes.append(size)
        return self.body.read(size)

    def close(self):
        self.closed = True


def fetch(body, headers=None, **kwargs):
    response = Response(body, headers or {})
    result = tools.fetch_url(
        "https://public.example/docs", opener=lambda request: response,
        resolver=lambda host: [(2, 1, 6, "", ("93.184.216.34", 443))],
        **kwargs,
    )
    assert response.closed
    return result


def test_gzip_returns_exact_readable_sentence():
    assert fetch(gzip.compress(PAGE), {"Content-Encoding": "gzip"}) == SENTENCE


@pytest.mark.parametrize("wbits", [zlib.MAX_WBITS, -zlib.MAX_WBITS])
def test_deflate_returns_exact_readable_sentence(wbits):
    compressor = zlib.compressobj(wbits=wbits)
    body = compressor.compress(PAGE) + compressor.flush()
    assert fetch(body, {"Content-Encoding": "deflate"}) == SENTENCE


def compressed(body, encoding):
    if encoding == "gzip":
        return gzip.compress(body)
    wbits = -zlib.MAX_WBITS if encoding == "raw" else zlib.MAX_WBITS
    compressor = zlib.compressobj(wbits=wbits)
    return compressor.compress(body) + compressor.flush()


@pytest.mark.parametrize("encoding", ["gzip", "deflate", "raw"])
@pytest.mark.parametrize("damage", ["garbage", "truncated", "trailing"])
def test_invalid_compression_returns_visible_error(encoding, damage):
    body = compressed(PAGE, encoding)
    if damage == "garbage":
        body = b"not a compressed source"
    elif damage == "truncated":
        body = body[:-1]
    else:
        body += b"trailing garbage"
    header = "deflate" if encoding == "raw" else encoding
    assert fetch(body, {"Content-Encoding": header}).startswith("Error:")


@pytest.mark.parametrize("encoding", ["br", "compress", "gzip, deflate"])
def test_unsupported_compression_returns_visible_error(encoding):
    assert fetch(PAGE, {"Content-Encoding": encoding}).startswith("Error:")


@pytest.mark.parametrize("encoding", ["identity", "gzip", "deflate", "raw"])
def test_declared_charset_returns_readable_text(encoding):
    sentence = "Les erreurs sont appelées des exceptions."
    page = f"<html><body><p>{sentence}</p></body></html>".encode("latin-1")
    body = page if encoding == "identity" else compressed(page, encoding)
    headers = {
        "Content-Encoding": "deflate" if encoding == "raw" else encoding,
        "Content-Type": 'text/html; Charset="ISO-8859-1"',
    }
    assert fetch(body, headers) == sentence


@pytest.mark.parametrize("charset,body", [
    ("unknown-charset", PAGE),
    ("utf-8", b"<p>\xff invalid UTF-8</p>"),
    ("ascii", b"<p>\xe9 invalid ASCII</p>"),
    ("base64_codec", PAGE),
])
def test_invalid_charset_returns_visible_error(charset, body):
    assert fetch(body, {"Content-Type": f"text/html; charset={charset}"}).startswith("Error:")


@pytest.mark.parametrize("encoding", ["gzip", "deflate", "raw"])
def test_decompression_bomb_returns_visible_error(encoding):
    body = compressed(b"A" * 10_000_000, encoding)
    assert len(body) < 20_000
    header = "deflate" if encoding == "raw" else encoding
    assert fetch(body, {"Content-Encoding": header}).startswith("Error:")


@pytest.mark.parametrize("encoding", ["identity", "gzip", "deflate", "raw"])
def test_decoder_enforces_input_and_output_byte_limits(encoding):
    plain = b"hello " * 100
    body = plain if encoding == "identity" else compressed(plain, encoding)
    header = "deflate" if encoding == "raw" else encoding
    headers = {"Content-Encoding": header}
    assert decode_source(body, headers, len(plain)) == plain.decode()
    with pytest.raises(ValueError):
        decode_source(body, headers, len(body) - 1)
    with pytest.raises(ValueError):
        decode_source(body, headers, len(plain) - 1)


def test_identity_defaults_to_strict_utf8():
    assert decode_source("café".encode(), {}, 100) == "café"
    assert fetch(b"<p>\xff</p>").startswith("Error:")
