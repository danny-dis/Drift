# Drift completion: persistent thought laboratory

## Intent and boundaries

Fix the live-reproduced research transport defect and close the idea/research/project loop. Make capture suitable for rapid, messy, interrupted thinking: preserve exact originals before AI, do not require categories, never discard repeated or low-salience thoughts, and permit capture/search while inference is unavailable. This is a workbench, not clinical treatment, mind-reading, unlimited compute, or a coding factory. No provider secret exposure, paid fallback, implicit external communications, autonomous source edits, or changes to another Hermes profile. No commit/push without authorization.

Baseline: clean main at 70ade49; 364 tests passed and frontend built. Existing service sources match checkout. Live gzip source corruption reproduced; existing model call allowance exhausted; original ideas remain captured despite answer-task completion. Prior audit evidence: C:/Users/pc/AppData/Local/Temp/drift-audit-0f59f9hk/evidence.json.

## Architecture

- Canonical raw captures: additive SQLite store per box. Transactional idempotency uses a client request ID, not content deduplication. Raw text is immutable; summaries, links and processing status are separate fields.
- Compatibility: existing ideas/tasks/ledger remain; a bounded intake bridge links captures to legacy ideas/tasks, with restart reconciliation and no LLM on capture.
- ThoughtInbox: one obvious capture input, retry-safe durable local draft, search/history, readable originals and honest background-processing states. Preserve text entered during an in-flight request.
- Completion: structured advisory idea qualification and findings persisted by controller-owned outcome adapter; external drift.md writes stay explicit. Maintain internal compact project-intelligence projection automatically and expose owner-authorized publish.
- Model budgets: show real persisted call allowance and wait reason, separately from monetary estimates. Intake continues even when model admission is closed.
- Research: source decompression/charset extraction is bounded and keeps IP/redirect protections; retained source integrity is not factual verification. Missing/invalid evidence stays needs_review. Bounded repair is explicit and records the same task lineage.
- No new orchestration framework/dependencies; Python/FastAPI, SQLite and React/Vite only.

## File ownership / first wave

1. Source lane: drift/tools.py, new drift/source_decode.py if useful, tests/test_compressed_sources.py.
2. Capture lane: new drift/capture_store.py, drift/capture_api.py and their tests. Public contract: capture(text,client_id), list(query,status,limit,offset), get(id), pending(limit), link(id,idea_id,task_id), finish(task_id,status,report_path,summary); API /api/ui/captures.
3. UI lane: new ThoughtInbox.tsx, useThoughtCapture.ts, optional thought-types.ts, thoughts.css and test_thought_ui_contract.py. Controller integrates existing DriftApp.
4. Controller owns brain.py, existing API/server wiring, task/pipeline/organism integration, model-budget UI, project-intelligence adapter and integration tests. No overlapping lane writes.

## Ordered acceptance slices

- [ ] Compressed gzip/deflate, charset and malformed/bomb responses tested; normal source text recovered without unsafe unbounded decompression.
- [ ] Exact text >4,000 characters, whitespace, Unicode, repeated thoughts and interrupted retries persist without truncation or duplication.
- [ ] Concurrent bursts and >1,000 stored thoughts are searchable/paginated after reopening; no model needed to capture.
- [ ] Pending captures become idempotently linked processing work; model outages/budget stops do not lose or reject captures.
- [ ] Completed idea work updates domain qualification/summary without replacing raw text or inventing evidence.
- [ ] Structured project findings maintain an internal compact intelligence view; explicit publish preserves unmanaged human content.
- [ ] Actual model-call limits and next allowed period visible; no phantom provider usage or misleading unlimited free calls.
- [ ] Default capture UI restores drafts, handles slow/failing requests, Ctrl/Cmd+Enter, pagination, search and keyboard/mobile layouts.
- [ ] Real public source + real free-only model produces retained report/citations, or explicit review with diagnostically correct reason; no fabricated success.
- [ ] Spec review, then independent quality review; important findings fixed and rechecked.
- [ ] Full Python suite, frontend build, browser acceptance in separate clean browser where available, burst/reopen/cap/provider-failure tests pass.

## Verification and limits

Use Python312 C:/Users/pc/AppData/Local/Programs/Python/Python312/python.exe. Focused TDD RED then GREEN before broad checks. Full suite previously takes about 7 minutes on this Windows host. Frontend deps can be copied from the verified disposable audit build, then the lockfile build rerun. All live journeys use a new temporary box and no owner production data. GitNexus impact before modifying indexed symbols; regenerate index only after integration for changed-symbol review. Month-long unattended usefulness, real clinical benefit, and third-party decision-model accuracy cannot be certified by this session; report those limits explicitly.
