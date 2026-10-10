"""Lane runtime integration: real minimal behavior, no network/model/paid calls."""

import json
import os

from drift import tools
from drift.brain import input_value, repack_context
from drift.config import config
from drift.memory import MemoryStream
from drift.providers import CallBudget, embed, free_only_extra


def test_free_only_hard_body_and_headers():
    body, headers = free_only_extra()
    assert body == {"costFilter": "free"}
    assert headers["X-Cost-Filter"] == "free"
    assert headers["X-Free-Tier-Strategy"] == "free_only"
    assert config.get("free_only") is True


def test_call_budget_hard_cap_persists_and_failure_safe(tmp_path):
    b = CallBudget(str(tmp_path))
    assert b.can_call() is True
    b.record_call(True, in_tokens=10, out_tokens=5)
    b2 = CallBudget(str(tmp_path))  # persisted across restart
    assert b2.status()["daily_calls"] == 1
    assert b2.status()["daily_tokens"] == 15
    b2.record_call(False)  # failed call: counts call + failure, no tokens
    assert b2.status()["failures"] == 1
    assert b2.status()["daily_tokens"] == 15
    # Exhaust cap: free calls count too
    cap = int(config.get("daily_max_model_calls", 200))
    for _ in range(cap):
        b2.record_call(True)
    assert b2.can_call() is False


def test_embed_disabled_by_default_no_paid_fallback():
    assert config.get("embeddings_enabled") is False
    assert embed("hello world") == []


def test_memory_lexical_retrieval_no_model(tmp_path):
    ms = MemoryStream(str(tmp_path))
    ms.add("Fact: the crab eats kelp near the window")
    ms.add("unrelated gibberish zzz qqq")
    hits = ms.retrieve("crab kelp window", top_k=1)
    assert hits and "kelp" in hits[0]["content"]
    # deterministic importance, no LLM
    assert 1 <= hits[0]["importance"] <= 10


def test_shell_disabled_by_default():
    assert config.get("shell_enabled") is False
    ok, _ = tools.shell_available()
    assert ok is False
    assert tools.run_command("echo hi", ".").startswith("Blocked:")


def test_safe_join_blocks_traversal(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        tools.safe_join(str(tmp_path), "../../etc/passwd")
    p = tools.safe_join(str(tmp_path), "a/b.txt")
    assert p.startswith(str(tmp_path))


def test_fetch_url_ssrf_and_redirect_guards_no_network():
    # loopback + private denied without any network
    assert "not public" in tools.fetch_url("http://127.0.0.1/")
    assert "not public" in tools.fetch_url("http://10.0.0.5/x")
    assert "Only http" in tools.fetch_url("file:///etc/passwd")
    # byte limit + redirect validation via injectable fakes
    class FakeResp:
        status = 200
        headers = {}
        def __init__(self, data):
            self._d = data
        def read(self, n=-1):
            if not self._d:
                return b""
            out, self._d = self._d[:n], self._d[n:]
            return out
        def close(self):
            pass
    def pub_resolver(h):
        ip = "93.184.216.34" if h == "example.com" else h
        return [(None, None, None, None, (ip, 0))]
    big = FakeResp(b"<p>hi</p>" * 100000)
    out = tools.fetch_url("http://example.com/", max_chars=100,
                          opener=lambda r: big, resolver=pub_resolver)
    assert len(out) <= 200
    redir = FakeResp(b"")
    redir.status = 302
    redir.headers = {"Location": "http://127.0.0.1/evil"}
    out2 = tools.fetch_url("http://example.com/", opener=lambda r: redir,
                           resolver=pub_resolver)
    assert "not public" in out2


def test_brain_idle_gate_and_user_priority(tmp_path):
    from drift.brain import Brain
    br = Brain({"name": "t"}, str(tmp_path))
    br._user_message = None
    br._inbox_pending = []
    # recurring low-value input -> backoff after hysteresis
    hyst = int(config.get("idle_hysteresis_cycles", 3))
    res = None
    for _ in range(hyst + 1):
        br._user_message = None
        res, _ = br.should_think(False)
    assert res is False
    # user input / work wins
    br._user_message = "please research kelp forests"
    ok, reason = br.should_think(False)
    assert ok is True and "priority" in reason
    br._user_message = None
    ok2, _ = br.should_think(True)
    assert ok2 is True


def test_repack_context_keeps_pairs_trims():
    items = [
        {"role": "user", "content": "packet"},
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "fetch_url", "arguments": "{}"}}]},
        {"type": "function_call_output", "call_id": "c1", "name": "fetch_url",
         "output": "x" * 5000},
        {"type": "function_call_output", "call_id": "orphan", "name": "shell",
         "output": "drop me"},
    ]
    out = repack_context(items, 1000)
    ids = [i.get("call_id") for i in out if isinstance(i, dict) and i.get("type") == "function_call_output"]
    assert ids == ["c1"]
    assert len([i for i in out if str(i).find("drop me") >= 0]) == 0


def test_research_store_contract(tmp_path):
    from drift.decisions import ResearchStore
    rs = ResearchStore(str(tmp_path))
    s = rs.start("kelp?", task_id="t1", strategy="targeted_lookup")
    rs.add_source(s["id"], "http://example.com/a", "kelp facts here")
    done = rs.finish(s["id"], {"findings": ["kelp is green"], "citations": []})
    assert done["state"] == "needs_review"
    assert done["verified"] is False
    assert rs.get(s["id"])["id"] == s["id"]
    assert len(rs.list()) == 1


def test_attention_budget_persists(tmp_path, monkeypatch):
    monkeypatch.setitem(config, "environment_path", str(tmp_path))
    from drift.attention import BudgetTracker
    class Dummy:
        def get_total_estimated_cost(self):
            return 0.0
    b = BudgetTracker(Dummy())
    b.record_spend(0.5)
    b2 = BudgetTracker(Dummy())
    assert abs(b2.daily_spend() - 0.5) < 1e-9
