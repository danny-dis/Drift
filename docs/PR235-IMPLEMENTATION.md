# Closed PR #2 / #3 / #5 implementation

Source proposals: [#2](https://github.com/danny-dis/Drift/pull/2), [#3](https://github.com/danny-dis/Drift/pull/3), [#5](https://github.com/danny-dis/Drift/pull/5). Those merged proposals did not themselves establish runtime completion.

Three isolated `openai-codex / gpt-6-luna` worker lanes delivered loop gating, provenance/checkpoints, and decision-provider/evaluation code. Controller integration closes the shared API/memory/loop seams. A fourth read-only Luna review found credential-redaction and multi-store repair-recovery defects; both have regression tests and source fixes.

## Delivered

- Provider-neutral typed `DecisionService`: bounded scores, choices and booleans; batching, typed validation, confidence fallback, persisted call admission, model/version/schema identifiers and privacy-controlled state.
- JEV remains one optional adapter, not a dependency. Existing lexical scoring and explicitly enabled LLM scoring remain available. Raw incoming memories always append; explicit kind, hierarchy depth and references are retained. Retention, novelty, contradiction, promotion and reflection are advisory metadata, never destructive actions.
- Optional memory-advisory batch, retrieval reranking and loop-provider decisions; deterministic operation works with all optional providers disabled.
- Conservative low-noise gating, owner/task preemption, bounded batch inspection, persistent operational counters and no grant of shell/web permissions by a model.
- Restart-safe research provenance/checkpoints, source retention, bounded repair history, same-task owner retries and recovery of interrupted retry persistence.
- Real dashboard/API summary, lineage display and explicit resume controls.
- Offline JSONL evaluator for predictions and explicit labels, including false-promotion/false-deletion rates when the necessary policy labels exist. No labels means unavailable quality metrics, not fabricated scores.

## Optional configuration

Defaults keep `free_only: true`, `jev_enabled: false`, `decision_models_enabled: false`, `decision_remote_opt_in: false`, disabled embeddings, disabled shell and deterministic memory scoring.

Use `decision_provider: jev`, `decision_models_enabled: true`, `decision_remote_opt_in: true` and an explicit departure from free-only mode only when remote JEV use is authorized. Credentials remain in the environment, never config. Programmatic local providers implement `decide(state, questions)` and may be injected into DecisionService/MemoryStream without a remote dependency.

Further opt-in switches: `decision_memory_advisory_enabled`, `decision_reranking_enabled`, `decision_loop_enabled`; `decision_min_confidence` defaults to 0.60. Privacy knobs: `decision_local_only`, `decision_allowed_state_fields`, `decision_max_state_chars`. Hard caps are the existing persisted `daily_max_model_calls` / `weekly_max_model_calls`, not separate unlimited decision budgets.

## Verification and limits

Run `python -m pytest` (test discovery is constrained to `tests`) and `npm ci && npm run build` under `frontend`. Evaluate labeled offline records with `python -m drift.decision_eval records.jsonl`.

Acceptance includes API/store/memory seams, large inbox tails, provider failures, privacy/budgets, synthetic credential-format redaction, interrupted same-task repair, and source/report restart continuity. Provider fixtures prove contracts, **not live JEV accuracy, calibration or cost savings**. Actual call counters are operational measurements; missed high-value rates remain unmeasured. Retained research is advisory until an owner verifies it.

The stash and old worker folders are preserved. Their regressive budgets/retry/safety implementations are not reapplied over safer main code. Unique unfinished UI-lane tests were recovered and exercised. Deployment paths and evidence live under Clara's profile, outside the repository; application data must never be replaced when updating code.
