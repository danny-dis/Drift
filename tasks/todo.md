# Drift 0.2.0 completion checklist

- [x] T1 Source transport: bounded gzip/deflate/charset decode; live public page readable; safety regressions pass.
- [x] T2 Canonical capture: exact originals, retry IDs, long dumps, concurrency, restart, search and pagination.
- [x] T3 Intake bridge: background staging, idempotent associations, checkpoint recovery, capture independent of models.
- [x] T4 Outcomes: advisory findings linked to originals; project intelligence requires explicit publication.
- [x] T5 Runtime: actual call limits, wait reason, bounded transient retries and no idle planning storm.
- [x] T6 ThoughtInbox: recovered drafts, safe in-flight editing, keyboard capture, searchable originals, responsive layout.
- [x] T7 Research: retained readable sources, bounded JSON evidence, validated quotes, no fabricated verified status.
- [x] Checkpoint: fault injection and independent checkpoint/privacy rechecks passed.
- [x] T8 Earlier capture/checkpoint/privacy spec and quality findings repaired and independently approved.
- [x] Office: current dashboard mounted, high-DPI procedural graphics, opt-in motion, reduced-motion and cleanup exercised in browsers.
- [x] Live v0.2.0: real source-backed research completed; thought processed; originals exact after reopen and service restart.
- [ ] Release gate: final inference/packaging reviews, complete hosted matrix, clean wheel install and published artifacts.
- [ ] Final release report: exact hosted CI and release evidence; no monthly unattended-soak claim.

Evidence artifacts are in the controller's private QA workspace, not user-state folders or release packages. The earlier full run passed 514 tests; the expanded run passed 538 with one CI-text-contract failure. That workflow compatibility failure was fixed and the focused release tests rerun successfully. The exact release commit must still pass hosted CI before publishing the version tag.
