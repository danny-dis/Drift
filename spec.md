# Drift — Production Implementation Specification

**Status:** Implementation specification  
**Target:** Drift v2 → production-ready autonomous idea/project intelligence organism  
**Primary principle:** Drift is not a perpetual LLM conversation. The model is a temporary cognitive worker; durable state, memory, evidence, scheduling, budgets, and project intelligence live outside the model.

---

## 1. Product Definition

Drift is a local-first personal idea laboratory and project-intelligence organism.

The owner dumps random ideas, concepts, observations, questions, documents, and thoughts into Drift. Drift turns them into structured knowledge, connects them to existing projects, researches them, challenges assumptions, monitors projects, and maintains a compact intelligence layer that coding agents can consume.

The owner chooses Drift's animal/personality presentation. The animal is a visualization and interaction layer, not the source of intelligence. Its visible state should reflect real internal state such as attention, curiosity, confidence, energy, sleep/consolidation, and current activity.

Drift should maximize the value obtained from whatever model resources the owner connects. A $10/month coding plan is a compute budget, not an invitation to continuously chat with the model.

### Ecosystem boundaries

- **Drift:** ideas, curiosity, research, project intelligence, monitoring, synthesis, challenge, attention allocation.
- **NOESIS:** durable cross-system memory/knowledge substrate when integrated.
- **dmr-X:** model/provider routing, capability selection, inference/runtime substrate.
- **ATHENA:** sovereign orchestration/governance; Drift should not duplicate ATHENA's role.
- **GHOST FACTORY:** software engineering/execution; Drift can recommend or hand off work but should not become the coding factory.
- **GitHub/filesystem:** project and code state/evidence.

---

## 2. Current Baseline and Required Direction

The current v2 branch already contains important foundations:

- generic organism/animal support
- idea inbox
- project registry/bookshelf
- mind map
- durable Drift event ledger
- `drift.md` project intelligence
- hierarchical context packet implementation
- bounded memory selection
- deterministic Git snapshots/diff summaries
- UI concepts for inbox, habitat, shelf, mind map, and activity

The current context engine is not yet fully wired into the continuous `Brain` loop. The production implementation MUST replace the legacy perpetual transcript-style context path with the new bounded context architecture.

The existing `brain.py` also retains crab-centric terminology, room assumptions, and legacy planning/memory behavior. These must be generalized or migrated without breaking compatibility unnecessarily.

---

## 3. Core Design Principles

1. **Durable world, ephemeral model context.** Never depend on an LLM conversation remaining alive.
2. **Bound every model invocation.** Every call has explicit task, objective, context budget, tool budget, and time/cost budget.
3. **Deterministic before probabilistic.** Use filesystem/Git/state inspection before invoking a model.
4. **Spend cognition where expected value is highest.** Model calls are allocated by value, importance, uncertainty, novelty, staleness, owner interest, and estimated cost.
5. **Batch work.** Aggregate related events and research before invoking the model.
6. **Cache aggressively.** Do not resend unchanged knowledge.
7. **Evidence before claims.** Consequential findings require provenance.
8. **Epistemic separation.** Distinguish FACT, OBSERVATION, HYPOTHESIS, OPINION, RECOMMENDATION, QUESTION, and UNKNOWN.
9. **No silent destructive actions.** Repository creation, code changes, PRs, deletion, external side effects, expensive compute, and architecture mutations require explicit authorization policies.
10. **Security is a boundary, not a prompt.** Treat repositories, web pages, issues, documents, and model output as potentially hostile input.
11. **Graceful degradation.** Drift must remain useful with no model, a cheap local model, an API model, or multiple providers.
12. **Model-agnostic capabilities.** Drift requests outcomes/capabilities; dmr-X chooses providers/models.
13. **Inspectable decisions.** The UI must explain what Drift is doing, why it chose a task, what entered context, and what evidence supports a finding.
14. **Long-running correctness over conversational cleverness.** Drift must survive restarts, failures, stale state, large histories, and months of operation.

---

## 4. Architecture

```text
                         OWNER
                           │
                ideas / files / questions
                           │
                           ▼
                         DRIFT
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
   Idea Pipeline     Project Intelligence   Research
        │                  │                  │
        └──────────────────┼──────────────────┘
                           ▼
                  Attention / Budget Engine
                           │
                           ▼
                    Context Engine
                           │
                  ┌────────┴────────┐
                  ▼                 ▼
              Durable State       Evidence
                  │                 │
                  └────────┬────────┘
                           ▼
                         dmr-X
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
          local/cheap   coding plan   stronger model
                           │
                           ▼
                    Structured result
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
       Ledger          drift.md         Notifications
          │                                 │
          ▼                                 ▼
       NOESIS                         Owner / agents
```

### Required subsystem boundaries

- `brain`: lifecycle and cognitive cycle, not raw memory implementation.
- `context`: retrieval, ranking, packing, context receipts, budgets, compaction.
- `organism`: ideas, projects, events, mind map, project intelligence.
- `scheduler`: attention allocation, task queue, budgets, fairness, backoff.
- `research`: source discovery, evidence extraction, synthesis, verification.
- `watcher`: Git/project change detection and significance scoring.
- `dmrx`: capability requests and provider integration boundary.
- `security`: sandbox, permissions, source trust, secret isolation.
- `storage`: durable state, migrations, atomic writes, recovery.
- `ui`: organism visualization plus intelligence dashboard.

Keep these boundaries testable and provider-independent.

---

# 5. Continuous Cognitive Loop

Drift MUST NOT implement an infinite LLM transcript.

Each cycle follows:

```text
WAKE
  ↓
deterministic inspection
  ↓
collect pending events/tasks
  ↓
score candidate work
  ↓
select highest-value task
  ↓
retrieve durable context
  ↓
construct bounded context packet
  ↓
invoke model/capability
  ↓
validate structured result
  ↓
persist useful findings
  ↓
update project intelligence / task state
  ↓
emit event + optional notification
  ↓
clear transient tool/model output
  ↓
SLEEP / next task
```

The model MUST receive only the current task's working set plus minimal continuity.

A restart MUST NOT lose task progress or require replaying the previous transcript.

---

# 6. Context Engineering and Memory

## 6.1 Memory hierarchy

Implement five levels:

1. **Working context** — current model invocation only.
2. **Recent runtime state** — tiny recent continuity for the current session/task.
3. **Durable episodic ledger** — events, findings, decisions, research outcomes.
4. **Project intelligence** — compact current-state `drift.md`.
5. **Raw evidence** — source documents, Git diffs, URLs, files, reports, tool artifacts.

The model must never be treated as the durable memory layer.

## 6.2 Context packet

Every invocation should contain, as applicable:

- task
- objective
- stable facts
- project state
- constraints
- relevant durable memories
- recent event summaries
- relevant ideas
- evidence references/excerpts
- current task state
- tiny recent continuity

The packet must have a configurable token/character budget.

The existing `drift/context.py` implementation should become the foundation. Extend it rather than replacing it with a heavyweight framework unless a measured need appears.

## 6.3 Retrieval

Current lexical relevance is acceptable as a fallback. Production retrieval should support hybrid ranking:

```text
relevance
+ semantic similarity
+ graph relationship
+ importance
+ confidence
+ recency
+ project relevance
+ owner interest
```

Embedding/reranking is optional when no suitable local model is available and should be routed through dmr-X.

## 6.4 Context receipts

Persist/debug a compact receipt for every model call:

- task ID
- context budget
- estimated tokens
- selected memory IDs
- selection scores
- evidence IDs
- excluded high-score items when useful
- model/provider
- estimated/actual cost if available
- result confidence

This makes context failures diagnosable instead of mysterious.

## 6.5 Compaction

Long-running work MUST periodically compact:

```text
raw events → findings → stable state
```

Old raw events remain available in durable storage, but they do not remain in active context.

Idle/sleep-time processing should synthesize recent events into stable knowledge and update project intelligence without requiring the owner to ask.

---

# 7. Task State

Add durable task/session state.

Minimum fields:

```text
id
goal
objective
project_id
phase
status
progress
blockers
open_questions
last_evidence
next_action
priority
estimated_cost
budget_remaining
attempt_count
created_at
updated_at
```

Supported phases should include at least:

- capture
- understand
- connect
- research
- verify
- synthesize
- qualify
- monitor
- complete
- blocked

Tasks must be resumable and idempotent.

---

# 8. Idea Pipeline

The owner can dump an unstructured thought such as:

> "Could we use X for Y? Maybe combine it with Z."

Drift turns this into a structured idea without prematurely forcing it into a project.

Lifecycle:

```text
CAPTURED
  ↓
UNDERSTANDING
  ↓
CONNECTED
  ↓
RESEARCHING
  ↓
QUALIFYING
  ├── PROJECT
  ├── RESEARCH
  └── PARKED
```

For each idea extract where possible:

- concise statement
- concepts
- entities
- implied problem
- possible solution
- uncertainty
- related projects
- evidence
- open questions
- confidence

### Matching existing projects

Matching should consider:

- semantic similarity
- project README/docs
- `drift.md`
- code concepts
- dependencies
- Git history
- project metadata
- prior idea relationships
- mind-map graph

Return a score plus a human-readable explanation. Never silently attach an idea to a project solely because of weak similarity.

---

# 9. Project Intelligence and `drift.md`

Every tracked project can have a compact living `drift.md`.

It is a **current-state projection**, not a diary.

Required managed sections:

```markdown
# Drift Intelligence

## Current State

## New Findings

## Challenges / Risks

## Alternatives

## Open Questions

## Evidence / Provenance
```

Optional sections:

- Opportunities
- Recommended Experiments
- Recently Changed
- Dependencies of Interest

Raw historical evidence belongs in the ledger/research artifacts.

Human-authored content outside the managed section must be preserved.

`drift.md` MUST be compact enough for coding agents to consume quickly.

---

# 10. Git / Project Watcher

Implement continuous project observation.

Monitor, where permissions allow:

- new commits
- meaningful diffs
- branches
- pull requests
- releases
- dependency changes
- documentation changes
- issues/events where available

Most monitoring MUST be deterministic and cheap.

Example:

```text
1000 Git events
      ↓
deterministic filtering
      ↓
37 meaningful changes
      ↓
12 potentially important
      ↓
5 model analyses
```

Never invoke the model for every Git event.

### Change analysis

For meaningful changes:

1. inspect commit/diff metadata
2. identify affected components
3. retrieve relevant project state
4. construct bounded context
5. ask a focused analysis capability
6. extract structured findings
7. update ledger
8. update `drift.md` when warranted
9. notify downstream coding agents when appropriate

A Git diff must be analyzed for significance, not merely reported as `git status`.

---

# 11. Research Engine

Drift should research ideas and project questions autonomously.

Research modes:

- Explore
- Investigate
- Verify
- Compare
- Challenge
- Monitor
- Synthesize

Pipeline:

```text
question
 ↓
search/discovery
 ↓
source filtering
 ↓
deduplication
 ↓
relevant extraction
 ↓
evidence classification
 ↓
cross-source comparison
 ↓
synthesis
 ↓
confidence + provenance
 ↓
ledger / research artifact
```

Research should batch related sources and avoid repeatedly fetching unchanged information.

### Epistemic rules

Every consequential result should classify claims as:

- FACT
- OBSERVATION
- HYPOTHESIS
- OPINION
- RECOMMENDATION
- QUESTION
- UNKNOWN

Claims should retain provenance and confidence.

Conflicting sources should be preserved as conflict, not silently averaged into certainty.

---

# 12. Attention and Compute-Budget Engine

This is a core subsystem.

Drift must treat model access as a scarce cognitive resource.

Every candidate task receives an attention score based on factors such as:

```text
importance
uncertainty
novelty
owner interest
staleness
expected value
risk
estimated cost
```

Conceptually:

```text
priority ≈ expected value / estimated cognitive cost
```

The exact formula must be configurable and tested rather than hard-coded as a magical constant.

### Required behavior

- prioritize high-value work
- batch related work
- avoid duplicate calls
- cache stable results
- defer low-value work
- enforce per-provider/per-period budgets
- reserve emergency budget for high-priority discoveries
- learn from owner feedback over time
- maintain fairness so low-priority projects do not starve forever

### Budget accounting

Track:

- provider
- model
- task
- estimated input tokens
- estimated output tokens
- actual usage if provider exposes it
- estimated cost
- configured budget
- remaining budget
- outcome/value

A connected $10 coding plan should be exploited as a finite resource. Drift should maximize useful artifacts/findings per unit of budget, not maximize number of conversations.

---

# 13. dmr-X Integration

Drift must request capabilities rather than hard-code a particular model.

Example capability requests:

```text
classify_idea
extract_concepts
embed
match_project
analyze_diff
research
verify_claims
compare_alternatives
challenge_assumption
synthesize
summarize
```

Example routing:

```text
Drift → dmr-X → cheapest capable model
                 ↓
             escalate only when needed
```

Escalation conditions include:

- low confidence
- conflicting evidence
- high-impact architecture decision
- security-sensitive analysis
- unusually complex reasoning
- repeated failure from cheaper capability
- owner explicitly requesting deeper analysis

The system must support a cheap local model, a connected coding subscription, and stronger external/local models without changing Drift's cognitive code.

---

# 14. Model Call Policy

Every model call must have:

- task ID
- capability
- objective
- context budget
- tool budget
- time budget
- provider/model selected by dmr-X
- authorization scope
- output schema
- retry policy

Prefer structured outputs over free-form prose for internal state transitions.

The model must not decide its own unrestricted budget.

The model must not receive secrets unless explicitly authorized and required.

---

# 15. Tool Use and Security

The current repository warning correctly notes that command blocklists and Python monkey-patches are not a security boundary. Production Drift MUST provide actual isolation for autonomous execution.

Required security architecture:

### Execution isolation

- sandbox shell/code execution in Docker, microVM, or equivalent real isolation
- per-project workspace boundaries
- read/write capability scopes
- no implicit host filesystem access
- network egress policy
- process/resource limits
- execution timeouts
- memory/CPU limits
- package installation isolation

### Secret isolation

- never expose host environment secrets by default
- explicit scoped credentials
- secret redaction in logs/context
- separate GitHub credentials with least privilege
- no secrets inside model-visible diagnostics

### Prompt-injection defense

Treat the following as untrusted content:

- README files
- source code comments
- GitHub issues/PR text
- web pages
- uploaded documents
- generated artifacts

Untrusted content MUST NOT be allowed to redefine Drift's system policy, permissions, or task authorization.

### Destructive action policy

Require explicit approval for:

- repository creation unless pre-authorized
- code writes outside a dedicated workspace
- pushes
- PR creation if not pre-authorized
- destructive file operations
- dependency upgrades with meaningful risk
- external side effects
- expensive compute
- architecture mutations

---

# 16. Failure Recovery

Drift is intended to run continuously, so failure recovery is mandatory.

Implement:

- durable task queue
- atomic state writes
- crash-safe checkpoints
- retry with exponential backoff
- provider failure fallback
- stuck-task detection
- idempotent task execution
- corruption recovery
- startup reconciliation
- orphaned task cleanup
- rate-limit handling
- network failure handling
- graceful shutdown

A crash must not duplicate a destructive action or lose a completed finding.

---

# 17. Observability

Provide structured telemetry for:

- cycle duration
- task selection
- task outcomes
- model calls
- estimated/actual usage
- budget consumption
- context size
- retrieval scores
- selected memories
- tool execution
- research sources
- failures/retries
- confidence
- escalation events

The UI should expose useful human-level summaries rather than raw logs by default.

---

# 18. Organism State and Animal UI

The owner chooses an animal.

No subsystem should assume crab, crab anatomy, or crab-specific behavior.

Animal configuration should include:

- species/visual identity
- name
- personality traits
- curiosity domains
- preferred thinking styles
- temperament
- animation mapping

### State mapping

The visible organism should reflect real state:

```text
curiosity  ← interesting unresolved questions
attention  ← selected task
confidence ← evidence quality
energy     ← workload/resource state
mood       ← recent activity/outcomes
sleep      ← consolidation/idle state
growth     ← accumulated knowledge
```

Habitat semantics:

- **desk:** current investigation/coding/reasoning
- **bookshelf:** projects
- **window:** external research/exploration
- **bed:** sleep/consolidation
- **floor:** unprocessed ideas
- **notice board:** unresolved questions

The UI should make the organism useful, not merely decorative.

---

# 19. Production UI

The UI should combine Tamagotchi, project intelligence dashboard, and knowledge graph.

Required areas:

1. **Idea Inbox** — raw and structured ideas.
2. **Habitat** — live organism state.
3. **Project Shelf** — all tracked projects and health/intelligence status.
4. **Mind Map** — ideas ↔ concepts ↔ projects ↔ findings.
5. **Activity Timeline** — what Drift has done and why.
6. **Research Panel** — evidence, sources, confidence, conflicts.
7. **Project Intelligence** — `drift.md` rendered as structured state.
8. **Task/Attention view** — what Drift is prioritizing and why.
9. **Budget view** — model/provider resource usage and remaining budget.
10. **Context receipt/debug view** — why memories/evidence entered a model call.
11. **Approvals** — pending actions requiring owner authorization.

The interface must answer:

> What is Drift doing?

> Why is it doing that?

> What did it learn?

> What evidence supports it?

> What did it spend?

> What needs my attention?

---

# 20. Notifications

Do not notify the user for every event.

Notify when:

- a high-value finding appears
- an important project risk is discovered
- an assumption is challenged with meaningful evidence
- an idea strongly matches an existing project
- a project becomes stale or newly important
- research reveals a significant opportunity
- Drift needs authorization
- a task is blocked
- a model/provider budget is near a configured limit

Notifications should include a concise reason and link to evidence/artifacts.

---

# 21. Daily Project Rounds

Drift should periodically review the project bookshelf.

It must NOT spend equal time on every project.

Attention should depend on:

- importance
- recent activity
- uncertainty
- novelty
- owner interest
- staleness
- risk
- expected value

Each round should produce a small bounded task, not an open-ended conversation.

Projects with nothing interesting should consume little or no model budget.

---

# 22. Sleep / Consolidation

When idle, Drift can perform low-priority consolidation.

Examples:

- summarize recent events
- merge duplicate findings
- update stable project state
- decay stale relevance
- identify unresolved questions
- refresh mind-map edges
- prepare future tasks

Sleep work must obey the same resource budget and must yield to higher-value tasks.

---

# 23. Research Artifacts

Ideas that do not qualify as projects should not disappear.

Create durable research artifacts containing:

- question
- motivation
- current understanding
- findings
- evidence
- alternatives
- uncertainties
- open questions
- conclusion/status
- timestamps

Possible statuses:

```text
researching
promising
validated
rejected
parked
superseded
```

A future idea should be able to reactivate old research and connect it to a new project.

---

# 24. Repository Creation and Handoff

When an idea qualifies as a project:

1. present qualification evidence
2. check authorization policy
3. create repository only if permitted
4. initialize project metadata
5. create initial `drift.md`
6. register the project
7. link the originating idea
8. create initial research/task state
9. hand implementation work to the appropriate engineering system when requested/authorized

Drift should not silently create projects because a model thinks an idea sounds interesting.

---

# 25. Owner Feedback Loop

Drift must learn from the owner's reactions.

Capture signals such as:

- useful/not useful
- dismiss
- investigate
- promote priority
- park
- accept challenge
- reject challenge
- mark finding correct/incorrect

Use these signals to tune:

- attention priorities
- project importance
- owner-interest model
- research depth
- notification thresholds
- challenge frequency

Do not allow implicit feedback to override explicit owner policy.

---

# 26. Context-Rot and Long-Running Evaluation

Add tests specifically for continuous operation.

Required scenarios:

### Long history

Create thousands of events and ensure a critical old fact is retrieved when relevant.

### Noise injection

Create large volumes of irrelevant recent events and ensure important relevant memory remains retrievable.

### Context budget

Verify every rendered packet stays below configured limits.

### Stale knowledge

Verify old facts lose recency weight without being permanently deleted.

### Provenance

Verify every consequential finding can trace back to evidence.

### Restart

Kill and restart Drift during a task. It must resume safely.

### Provider failure

Make the active model unavailable. Drift must retry/fallback without losing task state.

### Budget exhaustion

Exhaust a provider budget. Drift must stop nonessential calls and continue deterministic work/local capabilities.

### Prompt injection

Place malicious instructions in a README/web page. Drift must treat them as untrusted evidence.

### Duplicate event

Deliver the same Git event multiple times. Drift must not perform duplicate expensive work.

### Crash during write

Simulate interruption during persistence. State must remain recoverable.

---

# 27. Acceptance Criteria

Drift is considered production-ready only when all of the following are true.

## Cognitive architecture

- [ ] Brain no longer relies on an ever-growing model transcript.
- [ ] Every model call uses a bounded context packet.
- [ ] Context packets are inspectable and reproducible.
- [ ] Durable memory survives restart.
- [ ] Long histories do not cause context growth.
- [ ] Tool outputs are compacted/cleared after use.
- [ ] Long tasks have durable task state.

## Value / economics

- [ ] Model calls are selected by deterministic attention/budget logic.
- [ ] Low-value work does not consume significant model budget.
- [ ] Related work is batched.
- [ ] Stable results are cached.
- [ ] Provider usage is tracked.
- [ ] Budget limits are enforced.
- [ ] Escalation is selective.
- [ ] A cheap coding plan can be used continuously without runaway spend or pointless chatter.

## Project intelligence

- [ ] Git changes are monitored deterministically.
- [ ] Meaningful diffs trigger focused analysis.
- [ ] `drift.md` is maintained as compact current state.
- [ ] Historical evidence remains in the ledger.
- [ ] Ideas can match existing projects with explanations.
- [ ] Non-project ideas become durable research artifacts.
- [ ] Daily rounds prioritize intelligently.

## Research quality

- [ ] Findings preserve provenance.
- [ ] Confidence is explicit.
- [ ] Fact/hypothesis/recommendation are separated.
- [ ] Conflicting evidence is represented honestly.
- [ ] Research can resume after restart.

## Security

- [ ] Autonomous execution runs inside a real isolation boundary.
- [ ] Host secrets are not implicitly exposed.
- [ ] Untrusted repository/web content cannot change system policy.
- [ ] Permissions are explicit and least-privilege.
- [ ] Destructive/external actions require authorization.

## Reliability

- [ ] Tasks are resumable and idempotent.
- [ ] State writes are atomic/crash-safe.
- [ ] Provider failures are recoverable.
- [ ] Stuck tasks are detected.
- [ ] Rate limits/backoff are handled.
- [ ] Health/telemetry exists.

## UX

- [ ] Animal is owner-selectable.
- [ ] Organism state reflects actual system state.
- [ ] User can see what Drift is doing and why.
- [ ] User can inspect findings and evidence.
- [ ] User can inspect budget usage.
- [ ] User can approve/reject sensitive actions.
- [ ] UI remains useful without requiring the user to understand the internals.

---

# 28. Implementation Order

Do not implement this as one uncontrolled rewrite.

### Phase 1 — Cognitive kernel

1. Wire `drift/context.py` into `Brain`.
2. Remove dependence on legacy transcript replay for continuous cognition.
3. Add durable task state.
4. Add context receipts.
5. Add compaction and transient-output clearing.
6. Add long-running/context-rot tests.

### Phase 2 — Project intelligence

1. Build Git watcher.
2. Add deterministic significance detection.
3. Build focused diff-analysis tasks.
4. Connect findings to ledger.
5. Maintain `drift.md`.
6. Build research artifact lifecycle.
7. Complete idea → project/research qualification pipeline.

### Phase 3 — Attention economy

1. Add candidate task queue.
2. Add attention scoring.
3. Add budget accounting.
4. Add batching/deduplication.
5. Add caching.
6. Add fairness/starvation prevention.
7. Add owner-interest feedback.

### Phase 4 — dmr-X

1. Define capability interface.
2. Route cheap tasks to cheapest capable provider.
3. Add MiniMax/connected coding-plan integration through provider abstraction.
4. Add selective escalation.
5. Add usage/cost telemetry.

### Phase 5 — Research + challenge

1. Implement research modes.
2. Evidence extraction.
3. Source comparison.
4. Verification.
5. Alternatives.
6. Challenge engine.
7. Confidence/provenance UI.

### Phase 6 — Security/reliability

1. Real execution sandbox.
2. Credential isolation.
3. Prompt-injection defenses.
4. Durable job queue.
5. Crash recovery.
6. Rate-limit handling.
7. Health/telemetry.
8. Backup/migration tooling.

### Phase 7 — Production UI

1. Redesign organism/habitat.
2. Project shelf.
3. Idea inbox.
4. Research/evidence view.
5. Attention/budget dashboard.
6. Context receipts.
7. Approval center.
8. Notification system.

### Phase 8 — Production validation

Run the complete test matrix, long-running soak tests, security tests, provider failure tests, and budget exhaustion tests before declaring production-ready.

---

# 29. Coding-Agent Rules

The coding agent implementing this specification MUST:

1. Inspect the existing architecture before changing it.
2. Preserve working functionality unless explicitly replacing it.
3. Prefer small composable modules over one giant `brain.py`.
4. Add tests with each subsystem.
5. Keep model/provider integrations behind interfaces.
6. Never make a network/API dependency mandatory for basic local operation.
7. Never use an LLM where deterministic logic is sufficient.
8. Never feed entire repositories, ledgers, or transcripts into a model by default.
9. Never silently expand permissions.
10. Never silently spend beyond configured model budgets.
11. Preserve provenance for generated findings.
12. Make state transitions deterministic where possible.
13. Add migrations when changing durable schemas.
14. Document configuration and recovery behavior.
15. Run the full test suite after meaningful changes.
16. Do not declare production-ready because the feature exists; validate the acceptance criteria.

---

# 30. Definition of Done

The implementation is done when Drift behaves like a persistent personal research/project organism rather than a chatbot loop:

> The owner can dump an idea, walk away, and later return to a system that has intelligently connected it to their projects, investigated useful questions, monitored meaningful changes, challenged assumptions, preserved evidence, updated project intelligence, and spent scarce model resources only where they were likely to produce real value.

The strongest test is not how impressive one model response looks.

The strongest test is whether **one month of unattended operation produces useful, trustworthy, inspectable work without runaway context, runaway cost, unsafe execution, or loss of state.**
