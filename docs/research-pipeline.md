# Persistent research pipeline

The public `ResearchStore` retains source-linked queries, notes, tool and script lineage, file-change provenance, reports and bounded repair context. Scripts are recorded, never executed by the store. Relative paths are validated against the research root.

Checkpoints include phase, revision, next action and timestamp. Old records are interpreted through backward-compatible defaults; accepted new writes persist current checkpoints. Fetches actually performed by Brain are recorded as tool provenance. Sources and report attempts survive restart; prior failed reports are not substituted with invented evidence.

`POST /api/ui/research/sessions/{id}/resume` requests a bounded owner retry of the **same task and same sources**. A durable pending-repair marker allows recovery if task persistence fails, without spending another attempt. Completed work and exhausted repairs are rejected.

Citation integrity is a structural check, not factual verification. Candidate coverage/conflict scores are lexical heuristics, not semantic probabilities. The dashboard labels the limitations and shows provenance, repair history and explicit resume controls.

See `research.py`, `brain.py`, `ui_api.py` and [implementation status](PR235-IMPLEMENTATION.md).
