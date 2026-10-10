# Drift Context Engineering

Drift is a continuous organism, but it must **not** be a perpetual LLM conversation.
The model context is working memory; durable state is outside the model.

## Memory hierarchy

1. **Working context** — one bounded task packet sent to the model.
2. **Recent runtime state** — a small window of current events/tool outcomes.
3. **Durable episodic ledger** — ideas, observations, findings, questions and provenance.
4. **Project intelligence** — compact `drift.md` files representing the current project state.
5. **Raw source/evidence** — repositories, Git diffs, research documents and URLs that can be fetched again.

This follows the practical direction of modern context engineering: curate context rather than blindly increasing it, clear re-fetchable tool results, compact long-running state, and use persistent structured memory across tasks.

## Per-cycle algorithm

```text
wake/event
  -> deterministic state inspection
  -> identify task + project
  -> retrieve candidate memories
  -> score by relevance + importance + confidence + recency
  -> pack whole items into a hard budget
  -> call model
  -> validate/classify result
  -> persist useful result with provenance
  -> update project intelligence when warranted
  -> discard transient transcript/tool output
```

The next cycle reconstructs context from durable state. It does not inherit an ever-growing transcript.

## Why this works with cheap/local models

A small model is not asked to remember the world. It receives a narrow question, stable facts, relevant project state, and a few high-value memories. Expensive reasoning is therefore reserved for ambiguity, high-impact architectural questions, conflicting evidence, or low-confidence conclusions.

The context builder is intentionally provider-independent. dmr-X can later replace lexical relevance with embeddings/reranking and choose the appropriate model without changing Drift's memory contract.

## Compaction rule

`drift.md` is a **current-state projection**, not an append-only diary. Raw history remains in the ledger/evidence store. Re-synthesizing `drift.md` therefore reduces context size without deleting provenance.

## Epistemic rule

Every important result should be represented as one of observation, finding, hypothesis, question, challenge, recommendation or decision, with confidence and evidence where available. Missing context must never be treated as evidence that something does not exist.

## Escalation

A future dmr-X policy layer should escalate when:

- confidence is low;
- project importance is high;
- evidence conflicts;
- the proposed change affects architecture/security/data integrity;
- the cheap model repeatedly fails to converge.

Otherwise, Drift should continue with the inexpensive/local path.
