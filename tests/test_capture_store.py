"""Durable, lossless capture contract; no model or runtime required."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from drift.capture_store import CaptureStore


@pytest.fixture
def store(tmp_path):
    return CaptureStore(tmp_path)


def test_original_text_survives_restart_and_canonical_database(tmp_path):
    text = " \tstuf typo?? café e\u0301 🦀\r\n重复 重复\u2003\x00 trailing \n"
    original = CaptureStore(tmp_path).capture(text)["capture"]
    assert original == {
        "id": original["id"], "text": text,
        "created_at": original["created_at"], "status": "captured",
        "idea_id": None, "task_id": None, "report_path": None,
    }
    assert original["id"] and original["created_at"]
    assert CaptureStore(tmp_path).get(original["id"]) == original
    assert (tmp_path / "captures.sqlite3").is_file()
    with sqlite3.connect(tmp_path / "captures.sqlite3") as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


@pytest.mark.parametrize("size", [5000, 50_000, 1_000_000])
def test_large_dump_never_truncated(store, size):
    text = ("a 🦀\n " * size)[:size]
    capture = store.capture(text)["capture"]
    assert store.get(capture["id"])["text"] == text
    assert store.list()["captures"][0]["text"] == text


@pytest.mark.parametrize("text", [None, 42, False, [], {}, "", " \t\r\n\u2003", "x" * 1_000_001],
                         ids=['none', 'number', 'boolean', 'list', 'dict', 'empty', 'whitespace', 'oversized'])
def test_invalid_text_rejected_explicitly_without_writes(store, text):
    with pytest.raises(ValueError):
        store.capture(text)
    assert store.list()["total"] == 0


def test_retries_are_by_client_id_not_content_and_persist(tmp_path):
    store = CaptureStore(tmp_path)
    first = store.capture("same \n", "intent-1")
    retry = CaptureStore(tmp_path).capture("same \n", "intent-1")
    assert first["deduplicated"] is False
    assert retry == {"capture": first["capture"], "deduplicated": True}
    with pytest.raises(ValueError):
        store.capture("same", "intent-1")
    rows = [store.capture("same \n", key)["capture"] for key in (None, None, "intent-2")]
    assert len({row["id"] for row in rows} | {first["capture"]["id"]}) == 4
    assert store.list()["total"] == 4


@pytest.mark.parametrize("client_id", ["", " \t", 123, False, [], {}])
def test_invalid_client_ids(store, client_id):
    with pytest.raises(ValueError):
        store.capture("thought", client_id)


def test_parallel_writes_separate_store_objects_and_initialization(tmp_path):
    def write(index):
        return CaptureStore(tmp_path).capture(f"thought {index}", f"key-{index}")["capture"]
    with ThreadPoolExecutor(max_workers=12) as pool:
        captures = list(pool.map(write, range(100)))
    assert len({capture["id"] for capture in captures}) == 100
    assert CaptureStore(tmp_path).list()["total"] == 100
    assert {row["text"] for row in CaptureStore(tmp_path).list(limit=100)["captures"]} == {
        f"thought {index}" for index in range(100)
    }


def test_parallel_same_key_creates_exactly_one_capture(tmp_path):
    def write(_):
        return CaptureStore(tmp_path).capture("retry", "same-key")
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(write, range(30)))
    assert len({result["capture"]["id"] for result in results}) == 1
    assert sum(not result["deduplicated"] for result in results) == 1
    assert CaptureStore(tmp_path).list()["total"] == 1


def test_more_than_1000_captures_retained_searchable_and_paginated(store, tmp_path):
    ids = [store.capture(f"thought {index:04d}")["capture"]["id"] for index in range(1005)]
    restarted = CaptureStore(tmp_path)
    all_rows = []
    for offset in range(0, 1005, 100):
        page = restarted.list(limit=100, offset=offset)
        assert page["total"] == 1005
        assert page["has_more"] is (offset + len(page["captures"]) < 1005)
        all_rows.extend(page["captures"])
    assert [row["id"] for row in all_rows] == ids[::-1]
    assert restarted.list(query="0000")["captures"][0]["id"] == ids[0]
    assert restarted.list(offset=1005) == {"captures": [], "total": 1005, "has_more": False}


def test_order_has_id_tiebreak_even_for_equal_timestamps(store, tmp_path):
    captures = [store.capture("same moment")["capture"] for _ in range(4)]
    with sqlite3.connect(tmp_path / "captures.sqlite3") as db:
        db.execute("UPDATE captures SET created_at = ?", ("2026-01-01T00:00:00+00:00",))
    assert [row["id"] for row in store.list()["captures"]] == sorted(
        (row["id"] for row in captures), reverse=True
    )
    assert [row["id"] for row in store.pending()] == sorted(row["id"] for row in captures)


@pytest.mark.parametrize("needle", ["%", "_", "\\", "🦀", "\x00"])
def test_literal_substring_search_not_wildcards(store, needle):
    expected = store.capture(f"before {needle} after")["capture"]
    store.capture("ordinary unmatched thought")
    result = store.list(query=needle)
    assert result == {"captures": [expected], "total": 1, "has_more": False}


@pytest.mark.parametrize("kwargs", [
    {"limit": 0}, {"limit": -1}, {"limit": 1001}, {"limit": True},
    {"limit": 1.5}, {"limit": "2"}, {"offset": -1}, {"offset": True},
    {"offset": 1.5}, {"status": "deleted"}, {"status": []}, {"query": None},
])
def test_list_boundary_validation(store, kwargs):
    with pytest.raises(ValueError):
        store.list(**kwargs)


@pytest.mark.parametrize("limit", [0, -1, 1001, True, 1.5, "2"])
def test_pending_limit_validation(store, limit):
    with pytest.raises(ValueError):
        store.pending(limit)


def test_link_finish_and_pending_preserve_raw_and_associations(store, tmp_path):
    first = store.capture(" \nraw raw raw\t")["capture"]
    second = store.capture("next")["capture"]
    third = store.capture("last")["capture"]
    assert store.pending(limit=2) == [first, second]
    linked = store.link(first["id"], "idea-1", "task-1")
    assert linked["status"] == "queued"
    assert linked["idea_id"] == "idea-1" and linked["task_id"] == "task-1"
    assert store.link(first["id"], "idea-1", "task-1") == linked
    with pytest.raises(ValueError):
        store.link(first["id"], "idea-2", "task-2")
    with pytest.raises(ValueError):
        store.link(first["id"], "idea-2", "task-1")
    store.link(second["id"], "idea-1", "task-1")
    store.finish("task-1", "processed", "reports/out.md", "done")
    restarted = CaptureStore(tmp_path)
    assert restarted.pending() == [third]
    for capture in (first, second):
        result = restarted.get(capture["id"])
        assert result["text"] == capture["text"]
        assert result["status"] == "processed"
        assert result["report_path"] == "reports/out.md"
        assert restarted.link(capture["id"], "idea-1", "task-1") == result
    assert restarted.list(status="processed")["total"] == 2
    store.finish("task-1", "needs_review", summary="retry later")
    assert store.list(status="needs_review")["total"] == 2
    assert store.list()["total"] == 3


def test_missing_capture_and_invalid_link_finish(store):
    assert store.get("missing") is None
    with pytest.raises(KeyError):
        store.link("missing", "idea", "task")
    capture = store.capture("raw")["capture"]
    for idea, task in (("", "task"), ("idea", ""), (None, "task"), ("idea", 3)):
        with pytest.raises(ValueError):
            store.link(capture["id"], idea, task)
    for status in ("queued", "captured", "deleted", None, []):
        with pytest.raises(ValueError):
            store.finish("task", status)
    assert store.get(capture["id"]) == capture
