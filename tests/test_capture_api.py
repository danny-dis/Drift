"""Capture-only router integration; no Brain, LLM or TaskStore imports."""
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from drift.capture_api import router
from drift.capture_store import CaptureStore


PREFIX = "/api/ui/captures"


class ForbiddenRuntime:
    def __getattr__(self, name):
        raise AssertionError(f"Capture route touched forbidden runtime: {name}")


@pytest.fixture
def api(tmp_path):
    brains = {}
    for name in ("first", "second"):
        root = tmp_path / name
        brains[name] = SimpleNamespace(
            env_path=root, captures=CaptureStore(root),
            tasks=ForbiddenRuntime(), llm=ForbiddenRuntime(), ledger=ForbiddenRuntime(),
        )
    app = FastAPI()
    app.state.drift_brains = brains
    app.include_router(router)
    with TestClient(app) as client:
        yield client, brains


def test_post_get_and_retry_are_lossless_and_capture_only(api):
    client, brains = api
    text = " \t typoss café 🦀\r\nrepeated repeated \n" + "messy \t\n" * 7000
    first = client.post(PREFIX, json={"text": text, "client_id": "one-intent"})
    assert first.status_code == 200
    capture = first.json()["capture"]
    assert capture["text"] == text and len(text) > 50_000
    assert capture["status"] == "captured" and capture["task_id"] is None
    assert first.json()["deduplicated"] is False
    retry = client.post(PREFIX, json={"text": text, "client_id": "one-intent"})
    assert retry.json() == {"capture": capture, "deduplicated": True}
    assert client.get(f"{PREFIX}/{capture['id']}").json() == {"capture": capture}
    assert brains["first"].captures.get(capture["id"]) == capture
    conflict = client.post(PREFIX, json={"text": text + "changed", "client_id": "one-intent"})
    assert conflict.status_code == 409
    assert brains["first"].captures.list()["total"] == 1


def test_same_text_without_client_id_remains_distinct(api):
    client, _ = api
    ids = [client.post(PREFIX, json={"text": "again"}).json()["capture"]["id"] for _ in range(3)]
    assert len(set(ids)) == 3
    assert client.get(PREFIX).json()["total"] == 3


@pytest.mark.parametrize("body", [
    None, [], "text", {}, {"text": None}, {"text": 12}, {"text": False},
    {"text": " \t\u2003"}, {"text": "x" * 1_000_001},
    {"text": "valid", "client_id": 2}, {"text": "valid", "client_id": ""},
], ids=['null', 'list', 'string', 'missing', 'none', 'number', 'boolean', 'whitespace', 'oversized', 'key-number', 'key-empty'])
def test_invalid_body_is_explicit_400_and_does_not_write(api, body):
    client, brains = api
    result = client.post(PREFIX, json=body)
    assert result.status_code == 400
    assert brains["first"].captures.list()["total"] == 0


def test_invalid_json_is_400(api):
    client, _ = api
    response = client.post(PREFIX, content="{bad", headers={"content-type": "application/json"})
    assert response.status_code == 400


def test_organism_selection_is_isolated_and_invalid_is_not_fallback(api):
    client, brains = api
    capture = client.post(PREFIX + "?crab=second", json={"text": "second only"}).json()["capture"]
    assert brains["first"].captures.list()["total"] == 0
    assert client.get(PREFIX + "?crab=second").json()["captures"] == [capture]
    assert client.get(f"{PREFIX}/{capture['id']}?crab=second").status_code == 200
    assert client.get(f"{PREFIX}/{capture['id']}").status_code == 404
    for method, url in (("get", PREFIX), ("post", PREFIX), ("get", f"{PREFIX}/{capture['id']}")):
        response = getattr(client, method)(url + "?crab=missing", **({"json": {"text": "wrong"}} if method == "post" else {}))
        assert response.status_code == 404
    assert brains["second"].captures.list()["total"] == 1


def test_no_organisms_returns_503(api):
    client, _ = api
    client.app.state.drift_brains = {}
    assert client.get(PREFIX).status_code == 503
    assert client.post(PREFIX, json={"text": "raw"}).status_code == 503


def test_missing_id_returns_404(api):
    client, _ = api
    assert client.get(PREFIX + "/missing").status_code == 404


def test_filtered_literal_search_pagination_and_status(api):
    client, brains = api
    captures = [brains["first"].captures.capture(text)["capture"] for text in ("one%", "two%", "ordinary")]
    store = brains["first"].captures
    store.link(captures[0]["id"], "idea", "task")
    store.finish("task", "needs_review")
    page = client.get(PREFIX, params={"q": "%", "limit": 1}).json()
    assert page == {"captures": [captures[1]], "total": 2, "has_more": True}
    page2 = client.get(PREFIX, params={"q": "%", "limit": 1, "offset": 1}).json()
    assert page2["captures"][0]["id"] == captures[0]["id"]
    assert page2["has_more"] is False
    assert client.get(PREFIX, params={"status": "needs_review"}).json()["total"] == 1


@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": -1}, {"limit": 1001}, {"limit": "1.5"},
    {"limit": "wat"}, {"offset": -1}, {"offset": "wat"}, {"status": "deleted"},
])
def test_invalid_pagination_and_status_are_400(api, params):
    client, _ = api
    assert client.get(PREFIX, params=params).status_code == 400


def test_router_leaves_auth_to_host_middleware(api):
    _, brains = api
    app = FastAPI()
    app.state.drift_brains = brains
    app.include_router(router)
    @app.middleware("http")
    async def auth(request, call_next):
        from starlette.responses import JSONResponse
        if request.headers.get("x-test-auth") != "allowed":
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)
    with TestClient(app) as client:
        assert client.post(PREFIX, json={"text": "blocked"}).status_code == 401
        assert client.post(PREFIX, json={"text": "allowed"}, headers={"x-test-auth": "allowed"}).status_code == 200
