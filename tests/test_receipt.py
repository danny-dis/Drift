"""Tests for drift/receipt.py — context receipt logging."""
import pytest

from drift.receipt import ContextReceipt, ReceiptStore, from_dict, to_dict


def test_context_receipt_defaults(tmp_path):
    r = ContextReceipt(task_id="t1", context_budget=7000, estimated_tokens=1750)
    assert r.timestamp != ""
    assert r.selected_memory_ids == []
    assert r.evidence_ids == []


def test_to_dict_from_dict_roundtrip(tmp_path):
    r = ContextReceipt(
        task_id="t1", context_budget=7000, estimated_tokens=1750,
        selected_memory_ids=["m1", "m2"], selection_scores={"m1": 0.9, "m2": 0.5},
        evidence_ids=["e1"], excluded_high_score=["m3"],
        model_provider="openai", estimated_cost=0.02, result_confidence=0.8,
    )
    d = to_dict(r)
    r2 = from_dict(d)
    assert r2.task_id == "t1"
    assert r2.selected_memory_ids == ["m1", "m2"]
    assert r2.selection_scores == {"m1": 0.9, "m2": 0.5}


def test_save_and_load_receipts(tmp_path):
    store = ReceiptStore(str(tmp_path))
    store.save_receipt(ContextReceipt("t1", 7000, 1750))
    store.save_receipt(ContextReceipt("t2", 6000, 1500))
    store.save_receipt(ContextReceipt("t3", 5000, 1250))
    store2 = ReceiptStore(str(tmp_path))
    assert len(store2.list_receipts()) == 3


def test_get_receipts_for_task(tmp_path):
    store = ReceiptStore(str(tmp_path))
    store.save_receipt(ContextReceipt("t1", 7000, 1750))
    store.save_receipt(ContextReceipt("t2", 6000, 1500))
    store.save_receipt(ContextReceipt("t1", 5000, 1250))
    t1_receipts = store.get_receipts_for_task("t1")
    assert len(t1_receipts) == 2


def test_list_receipts_limit(tmp_path):
    store = ReceiptStore(str(tmp_path))
    for i in range(5):
        store.save_receipt(ContextReceipt(f"t{i}", 7000, 1750))
    assert len(store.list_receipts(limit=3)) == 3


def test_get_total_estimated_cost(tmp_path):
    store = ReceiptStore(str(tmp_path))
    store.save_receipt(ContextReceipt("t1", 7000, 1750, estimated_cost=0.01))
    store.save_receipt(ContextReceipt("t2", 6000, 1500, estimated_cost=0.02))
    store.save_receipt(ContextReceipt("t3", 5000, 1250, estimated_cost=None))
    assert store.get_total_estimated_cost() == 0.03


def test_receipt_store_no_file(tmp_path):
    store = ReceiptStore(str(tmp_path / "nonexistent"))
    assert store.list_receipts() == []
    assert store.get_total_estimated_cost() == 0.0
