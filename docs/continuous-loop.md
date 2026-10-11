# Continuous bounded loop

Implemented from PR #2's proposal, not merely the merged specification.

- Explicit owner messages always preempt idle hysteresis; pending tasks still require deterministic budget admission.
- Every incoming batch is inspected in bounded chunks. Only recognized small noise is discarded; nontrivial unknown input and high-value tails are retained.
- Loop actions: research, reflect, plan, respond, sleep, ignore. An optional typed decision provider is advisory and cannot suppress high-value work or grant capabilities.
- `loop_decisions.json` persists observed actions, model calls, latency and output counts. `missed_high_value` is **unmeasured** without labeled counterfactuals, not an asserted zero.
- Memory, decision and budget files are excluded from new-input detection.
- Shell, URL and sandbox permission checks stay deterministic. Decisions never constitute security approval.

See `brain.py`, `loop_decisions.py`, `/api/ui/decisions` and [implementation status](PR235-IMPLEMENTATION.md).
