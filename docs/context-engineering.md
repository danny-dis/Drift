# How Drift builds model context

Drift builds a bounded packet for each model call. Saved thoughts, task checkpoints and evidence live outside that packet, so a long-running worker does not need an ever-growing conversation to remember its work.

## Memory hierarchy

The current packet holds the task, selected project facts, a bounded set of memories and any tool results needed for that call. The ledger keeps ideas, events and their provenance. Task checkpoints keep progress and processing permission. Original captures stay in SQLite; reports and fetched evidence stay in the box.

Project intelligence and `drift.md` are summaries of saved work, not replacements for the original evidence. Publishing a project's `drift.md` section still requires an explicit owner action.

## Per-cycle algorithm

```text
wake/event
  -> deterministic state inspection
  -> identify task + project
  -> retrieve candidate memories
  -> exclude archived or held sources
  -> score by relevance + importance + confidence + recency
  -> pack whole items into a hard budget
  -> record selected source revisions and recheck before the physical request
  -> call model
  -> validate/classify result
  -> persist useful result with provenance
  -> update project intelligence when warranted
  -> discard transient transcript/tool output
```

The next cycle reconstructs context from durable state. It does not inherit an ever-growing transcript.

## Provider and context limits

The packet has a character budget, and provider requests also have output, retry and call limits. Captured-thought processing uses only the current original part rather than unrelated workbench history. Wiki uses its explicitly saved source snapshots.

The configured provider receives that bounded input. Drift does not automatically escalate difficult work to a paid model, and free-only mode refuses routes outside its allowed gateway. A smaller packet does not guarantee that a model will reason correctly.

## Compaction rule

`drift.md` is a **current-state projection**, not an append-only diary. Raw history remains in the ledger/evidence store. Re-synthesizing `drift.md` therefore reduces context size without deleting provenance.

## Epistemic rule

Every important result should be represented as one of observation, finding, hypothesis, question, challenge, recommendation or decision, with confidence and evidence where available. Missing context must never be treated as evidence that something does not exist.

## Archive and provenance

A project task can use related ideas without naming one as its primary source. Drift therefore tracks the sources actually retained by the packet, including source-bearing events and memory-reference chains. Saved task provenance lets later outcomes and memories keep those relationships after restart.

Archive checks follow originals, their idea projections and related projects. They run again before model attempts, retries, tools and result publication. Processing approval covers reviewed source revisions; it is separate from the revision vector of an already assembled packet. Approving fresh work cannot make a stale in-flight response current.

Background planning and reflection apply source checks too. Generated `projects.md` text stays readable but is not promoted into owner instructions. A reflection rechecks its sources inside the storage worker before saving an insight. See [safety and limits](safety.md).
