from drift.context import MemoryBlock, build_packet, keyword_relevance


def test_context_prefers_relevant_important_memory():
    packet = build_packet(
        task="investigate lattice",
        objective="identify risks",
        memories=[
            MemoryBlock("weak", "unrelated old note", importance=.2, confidence=.3, relevance=.1, recency=.1),
            MemoryBlock("strong", "deterministic lattice dependency graph", importance=.9, confidence=.9, relevance=.95, recency=.5),
        ],
        budget_chars=2500,
    )
    rendered = packet.render(2500)
    assert "deterministic lattice dependency graph" in rendered


def test_context_is_bounded_without_splitting_items():
    packet = build_packet(
        task="test",
        objective="stay small",
        evidence=["x" * 1000 for _ in range(20)],
        budget_chars=2200,
    )
    assert len(packet.render(2200)) <= 2200


def test_keyword_relevance_is_cheap_and_deterministic():
    assert keyword_relevance("dependency graph", "use a dependency graph for routing") > 0.5
    assert keyword_relevance("dependency graph", "weather forecast") == 0.0
