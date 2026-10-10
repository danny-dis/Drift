"""Tests for ResearchStore (PR3/4) in drift/research.py.

Compact deterministic durable session store. Disk-backed, stdlib only.
"""
import os

import pytest

from drift.research import ResearchStore


def sample_report(sources, n_findings=1):
    return {
        "findings": [f"finding {i} about testing" for i in range(n_findings)],
        "citations": [{"source_id": s["id"], "note": "supports"} for s in sources],
        "proposals": [],
    }


class TestLifecycle:
    def test_start_get_list(self, tmp_path):
        from drift.research import ResearchStore as RS
        s = RS(str(tmp_path / "box"))
        sess = s.start("why do crabs molt?")
        assert sess["state"] in ("selecting", "researching")
        assert sess["id"]
        got = s.get(sess["id"])
        assert got["query"] == "why do crabs molt?"
        assert isinstance(s.list(), list) and len(s.list()) == 1

    def test_disk_restart_resumes_lineage(self, tmp_path):
        from drift.research import ResearchStore as RS
        root = str(tmp_path / "box")
        s1 = RS(root)
        sess = s1.start("crab molting cycle")
        s1.add_source(sess["id"], "https://example.com/molting", "Studies show that crabs molt to grow larger shells over time.")
        s2 = RS(root)  # new instance = restart
        got = s2.get(sess["id"])
        assert len(got["sources"]) == 1
        assert got["sources"][0]["url"]
        # lineage continues after restart
        s2.add_source(sess["id"], "https://example.com/shell", "Studies show that new shells harden after molting completes fully.")
        assert len(s2.get(sess["id"])["sources"]) == 2

    def test_path_bounds_reject_traversal(self, tmp_path):
        from drift.research import ResearchStore as RS
        s = RS(str(tmp_path / "box"))
        with pytest.raises(ValueError):
            s.get("../evil")
        with pytest.raises(ValueError):
            s.get("a/b")
        assert s.get("does-not-exist-0000") is None


class TestSources:
    def test_add_source_record_shape(self, tmp_path):
        from drift.research import ResearchStore as RS
        s = RS(str(tmp_path / "box"))
        sess = s.start("crab diet")
        src = s.add_source(sess["id"], "https://example.com/diet?a=1#frag", "Studies show that crabs eat a varied diet daily for growth.")
        assert src["url"] and src["excerpt"] and src["content_hash"] and src["retrieved_at"]
        assert src["duplicate"] is False

    def test_duplicate_url_dedupes_without_discarding(self, tmp_path):
        from drift.research import ResearchStore as RS
        s = RS(str(tmp_path / "box"))
        sess = s.start("crab diet")
        text = "Studies show that crabs eat a varied diet daily for growth and health."
        s.add_source(sess["id"], "https://example.com/diet", text)
        dup = s.add_source(sess["id"], "https://EXAMPLE.com/diet/", text)
        assert dup["duplicate"] is True
        got = s.get(sess["id"])
        assert len(got["sources"]) == 1  # no new entry
        assert "https://EXAMPLE.com/diet/" in got["sources"][0]["aliases"]

    def test_duplicate_hash_dedupes(self, tmp_path):
        from drift.research import ResearchStore as RS
        s = RS(str(tmp_path / "box"))
        sess = s.start("crab diet")
        text = "Studies show that crabs eat a varied diet daily for growth and health."
        s.add_source(sess["id"], "https://example.com/a", text)
        dup = s.add_source(sess["id"], "https://example.com/b", text)
        assert dup["duplicate"] is True
        assert len(s.get(sess["id"])["sources"]) == 1

    def test_source_cap(self, tmp_path):
        from drift.research import ResearchStore as RS
        s = RS(str(tmp_path / "box"))
        sess = s.start("cap query")
        for i in range(10):
            s.add_source(sess["id"], f"https://example.com/p{i}", f"Studies show that crab fact number {i} holds true in the wild today.")
        with pytest.raises(ValueError):
            s.add_source(sess["id"], "https://example.com/overflow", "Studies show that one more crab fact holds true in the wild today.")

    def test_conflicting_evidence_tracked_as_candidates(self, tmp_path):
        from drift.research import ResearchStore as RS
        s = RS(str(tmp_path / "box"))
        sess = s.start("do crabs sleep?")
        s.add_source(sess["id"], "https://example.com/a", "Studies show that crabs sleep regularly every night in burrows.")
        s.add_source(sess["id"], "https://example.com/b", "Studies show that crabs do not sleep regularly and never rest in burrows.")
        got = s.get(sess["id"])
        assert len(got["conflicts"]) >= 1
        c = got["conflicts"][0]
        assert c["kind"] == "candidate"
        assert len(c["source_ids"]) == 2


class TestFinish:
    def test_finish_happy_path_complete(self, tmp_path):
        from drift.research import ResearchStore as RS
        s = RS(str(tmp_path / "box"))
        sess = s.start("crab molting")
        src = s.add_source(sess["id"], "https://example.com/m", "Studies show that crabs molt to grow larger shells over time.")
        done = s.finish(sess["id"], sample_report([src]))
        assert done["state"] == "complete"
        assert done["report"] is not None
        # report persisted in box
        assert os.path.isdir(os.path.join(str(tmp_path / "box"), "research"))

    def test_no_source_report_never_verified(self, tmp_path):
        from drift.research import ResearchStore as RS
        s = RS(str(tmp_path / "box"))
        sess = s.start("unsourced query")
        done = s.finish(sess["id"], {"findings": ["a guess"], "citations": [], "proposals": []})
        assert done["state"] == "needs_review"
        assert done["verified"] is False

    def test_invalid_citations_need_repair(self, tmp_path):
        from drift.research import ResearchStore as RS
        s = RS(str(tmp_path / "box"))
        sess = s.start("cited query")
        src = s.add_source(sess["id"], "https://example.com/m", "Studies show that crabs molt to grow larger shells over time.")
        bad = {"findings": ["claim"], "citations": [{"source_id": "missing-id"}], "proposals": []}
        done = s.finish(sess["id"], bad)
        assert done["state"] == "needs_review"
        assert done["repairs"] == 1
        # valid retry succeeds
        done2 = s.finish(sess["id"], sample_report([src]))
        assert done2["state"] == "complete"

    def test_repair_limit_enforced(self, tmp_path):
        from drift.research import ResearchStore as RS
        s = RS(str(tmp_path / "box"))
        sess = s.start("repair query")
        s.add_source(sess["id"], "https://example.com/m", "Studies show that crabs molt to grow larger shells over time.")
        bad = {"findings": ["claim"], "citations": [{"source_id": "nope"}], "proposals": []}
        s.finish(sess["id"], bad)
        s.finish(sess["id"], bad)
        with pytest.raises(ValueError):
            s.finish(sess["id"], bad)

    def test_report_cap(self, tmp_path):
        from drift.research import ResearchStore as RS
        s = RS(str(tmp_path / "box"))
        sess = s.start("big report query")
        src = s.add_source(sess["id"], "https://example.com/m", "Studies show that crabs molt to grow larger shells over time.")
        big = {"findings": ["x" * 9000], "citations": [{"source_id": src["id"]}], "proposals": []}
        out = s.finish(sess["id"], big)
        assert out["state"] == "needs_review"

    def test_proposal_transitions_validated(self, tmp_path):
        from drift.research import ResearchStore as RS
        s = RS(str(tmp_path / "box"))
        sess = s.start("proposal query")
        src = s.add_source(sess["id"], "https://example.com/m", "Studies show that crabs molt to grow larger shells over time.")
        r1 = {"findings": ["f"], "citations": [{"source_id": src["id"]}], "proposals": [{"id": "p1", "title": "build trap", "state": "proposed"}]}
        d1 = s.finish(sess["id"], r1)
        assert d1["state"] == "complete"
        # illegal jump proposed -> implemented rejected (must go via accepted)
        r2 = {"findings": ["f"], "citations": [{"source_id": src["id"]}], "proposals": [{"id": "p1", "title": "build trap", "state": "implemented"}]}
        with pytest.raises(ValueError):
            s.finish(sess["id"], r2)
        # legal: proposed -> accepted
        r3 = {"findings": ["f"], "citations": [{"source_id": src["id"]}], "proposals": [{"id": "p1", "title": "build trap", "state": "accepted"}]}
        d3 = s.finish(sess["id"], r3)
        assert d3["report"]["proposals"][0]["state"] == "accepted"
        assert d3["report"]["proposals"][0]["provenance"]

    def test_significant_query_gets_hypotheses(self, tmp_path):
        from drift.research import ResearchStore as RS
        s = RS(str(tmp_path / "box"))
        sess = s.start("compare crab molting vs fish growth and evaluate which strategy helps survival and why?")
        assert len(sess["candidates"]) >= 2
        assert sess["outline"]
        plain = s.start("crabs")
        assert plain["candidates"] == []
