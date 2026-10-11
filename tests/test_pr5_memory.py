import json

from drift import memory
from drift.memory import MemoryStream


def test_memory_keeps_explicit_kind_and_adds_advisory_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "embed", lambda _text: [])
    item = MemoryStream(str(tmp_path)).add("A lesson learned", kind="episode", depth=2, references=["m_0001"])
    assert item["kind"] == "episode"
    assert item["depth"] == 2 and item["references"] == ["m_0001"]
    assert item["decision"]["provider"]
    persisted = json.loads((tmp_path / "memory_stream.jsonl").read_text().splitlines()[0])
    assert persisted["content"] == "A lesson learned"
    assert persisted["decision"] == item["decision"]


def test_novelty_and_contradiction_are_candidates_not_truth(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "embed", lambda _text: [])
    stream = MemoryStream(str(tmp_path))
    first = stream.add("The setting is enabled", kind="fact")
    second = stream.add("The setting is disabled", kind="fact")
    assert first["decision"]["novelty"] == "unassessed"
    assert second["decision"]["novelty"] == "unassessed"
    assert len(stream.memories) == 2
    assert second["decision"].get("contradiction_candidates") == []
