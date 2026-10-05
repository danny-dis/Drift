# Decision Models as an Optional DRIFT Capability

## Status

**Proposed architecture / research**

Decision models such as JEV should be supported by DRIFT as an **optional acceleration and judgment capability**, never as a required runtime dependency.

DRIFT must remain fully functional when no decision model is configured, unavailable, rate-limited, degraded, or unsuitable for a decision.

## Why this matters

DRIFT runs continuously. Its memory pipeline currently asks a generative model to perform small bounded judgments, most notably importance scoring.

Examples of bounded memory decisions include:

- How important is this memory?
- Is this memory worth retaining?
- Is it probably a duplicate?
- What kind of memory is this?
- Which project or scope does it belong to?
- Should it be promoted to a higher-retention tier?
- Is reflection warranted?
- Which memories should be grouped for reflection?
- Should this event enter long-term memory?
- How confident are we in the classification?

These are different from generation, synthesis, research, or conversation.

A decision model is designed for this boundary: application state goes in, and typed choices, scores, or yes/no probabilities come back. JEV, for example, supports multiple typed questions against the same state in one request, making it well suited to batching memory judgments.

## Architectural rule

**Decision models are a capability, not a dependency.**

The DRIFT core must not import, require, or assume JEV.

Instead:

```
                    DRIFT
                      |
             Decision Service
                      |
       +--------------+--------------+
       |              |              |
   JEV adapter    future adapter   deterministic
       |              |              |
    optional       optional          fallback
```

The memory subsystem asks for a decision through an internal interface. It does not know which model produced it.

## Decision provider contract

Introduce a small internal abstraction conceptually equivalent to:

```python
class DecisionProvider(Protocol):
    def decide(
        self,
        state: dict | str,
        questions: list[DecisionQuestion],
    ) -> DecisionResult:
        ...
```

The contract should support:

- typed choices
- ordered scores
- yes/no probabilities
- confidence/probability
- model/provider identity
- latency and usage metadata
- failure status
- deterministic request/correlation ID

The contract must not expose JEV-specific request formats to the rest of DRIFT.

## Provider selection

The decision layer should support:

1. **Disabled**
   - Skip model decisions entirely.
   - Existing DRIFT behavior remains valid.

2. **JEV**
   - Use JEV when configured.
   - Batch independent questions against the same state.

3. **Other decision model**
   - Future System One / decision-model providers can be plugged in.

4. **LLM fallback**
   - Existing generative-model judgment can remain available where appropriate.

5. **Deterministic fallback**
   - Simple rules can answer some questions without any model.

The exact fallback chain should be configurable by decision type.

Example:

```
importance_score
    |
    +-- deterministic heuristic if obvious
    |
    +-- decision model if configured
    |
    +-- existing LLM scorer
    |
    +-- safe default
```

No path should make JEV mandatory.

## Memory pipeline

The current memory implementation calls an LLM directly for every importance score. That coupling should eventually become:

```
memory.add()
    |
    v
MemoryDecisionService
    |
    +--> importance
    +--> retention
    +--> classification
    +--> promotion
    +--> reflection trigger
    |
    v
Memory record
```

Embeddings remain independent. Storage remains independent. Reflection generation remains independent.

A decision model should therefore **complement** the existing memory architecture rather than replace it.

## High-value DRIFT uses

### 1. Importance scoring

Current:

```
memory -> LLM -> 1..10
```

Optional capability:

```
memory -> DecisionProvider -> score 1..10 + confidence
```

The probability/confidence should be stored as metadata where useful.

### 2. Retention decisions

Instead of treating every memory equally:

```
ephemeral
short_term
normal
important
long_term
permanent
```

A decision model can estimate which tier the memory deserves.

This should remain advisory: deterministic retention policies and user/system rules always have precedence.

### 3. Memory classification

A single request can classify a memory into several dimensions:

```
kind       = thought | fact | discovery | lesson | task | preference
scope      = personal | project | research | system
importance = 1..10
retain     = yes/no
promote    = yes/no
```

Batching these questions avoids repeatedly sending the same state.

### 4. Duplicate and novelty detection

Before creating another durable memory:

```
new memory
    |
    +-- semantic retrieval
    |
    +-- decision model
          |
          +-- duplicate
          +-- related
          +-- genuinely new
```

The decision model should not replace embeddings. Embeddings find candidates; the decision layer judges the relationship.

### 5. Reflection selection

Instead of reflecting whenever a simple accumulated score crosses a threshold, DRIFT can ask:

- Is there enough new information to reflect?
- Which memories belong together?
- Is the pattern novel?
- Should reflection happen now?
- What memories are most valuable to synthesize?

The expensive LLM then receives only the selected evidence.

### 6. Retrieval reranking

Embeddings provide candidate memories.

A decision model can optionally rerank a small candidate set using the current task state:

```
vector retrieval
       ↓
top 20 candidates
       ↓
decision model
       ↓
top 3-5 context memories
```

This should be optional because retrieval must remain functional without it.

### 7. Memory promotion

DRIFT can continuously review older memories and decide whether they deserve promotion based on:

- repeated relevance
- recurrence
- project importance
- user interaction
- later discoveries
- contradictions
- proven usefulness

This enables a more dynamic memory lifecycle without requiring an expensive generative call.

### 8. Contradiction detection

When a new memory conflicts with an existing important memory:

```
new fact
   ↓
retrieve related memories
   ↓
decision model
   ↓
no conflict / possible conflict / strong conflict
   ↓
LLM only when investigation is required
```

The decision model flags the case; the generative model investigates it.

## Decision models should not do everything

Do **not** use a decision model for:

- open-ended research
- writing reports
- generating reflections
- explaining discoveries
- conversations
- complex synthesis
- creating hypotheses
- writing code
- replacing the memory store
- replacing embeddings

The intended division is:

| Work | Best component |
|---|---|
| Store memory | DRIFT core |
| Embed memory | embedding model |
| Find candidates | vector/search system |
| Bounded judgment | decision model |
| Deterministic policy | rules |
| Deep synthesis | LLM |
| Research | research subsystem |
| Generate artifacts | LLM / coding agent |

## Cost strategy

Decision models are especially valuable because DRIFT is continuous.

The architecture should optimize for:

```
cheap deterministic work
        ↓
cheap decision work
        ↓
small retrieval set
        ↓
expensive generation only when justified
```

For JEV specifically, current documentation describes input-token billing with output not billed and supports up to 20 questions per request. This makes batching particularly attractive for memory bookkeeping.

However, DRIFT must never encode today's JEV price into its architecture.

The provider interface should work equally well if:

- JEV becomes expensive
- JEV changes API shape
- JEV disappears
- another decision model becomes better
- a local decision model becomes available

## Confidence-aware escalation

Decision-model output must be treated as a signal, not truth.

Use thresholds:

```
high confidence
    -> execute normal low-risk path

medium confidence
    -> conservative path / retrieve more evidence

low confidence
    -> LLM, deterministic policy, or defer

high-impact decision
    -> policy/human approval regardless of model confidence
```

Memory decisions are generally low-risk, but the same infrastructure may later be reused for higher-impact autonomous actions. The safety boundary therefore belongs in the decision service rather than inside a provider adapter.

## Observability

Every optional decision should be observable without exposing sensitive memory content unnecessarily.

Record:

- decision type
- provider
- model/version
- confidence
- selected answer
- latency
- input-token usage where available
- fallback taken
- decision ID
- schema/version

Do not make raw memory contents part of telemetry by default.

Pinned model versions should be supported for reproducibility. Rolling aliases should record the resolved model version.

## Failure behavior

Decision-provider failures must never stop the memory loop.

Examples:

```
timeout
rate limit
invalid response
provider unavailable
context too large
authentication failure
schema mismatch
```

All should degrade gracefully.

For example:

```
JEV unavailable
    ↓
existing LLM scorer
    ↓
deterministic/default score
    ↓
continue memory write
```

A transient decision-provider outage must not cause DRIFT to lose memories.

## Privacy

Decision models may receive memory state containing sensitive information.

The decision layer therefore needs:

- provider allow/deny configuration
- local-only mode
- redaction hooks
- field-level filtering
- maximum state size
- audit metadata
- explicit opt-in for remote providers

A user who does not want memory leaving the machine must be able to disable remote decision providers while keeping DRIFT operational.

## Configuration

Decision models should be configured as an optional capability, for example:

```yaml
decision_models:
  enabled: false

  provider: null

  fallback: "llm"

  memory:
    importance: true
    retention: true
    classification: true
    novelty: true
    reflection_selection: true

  confidence:
    low: 0.60
    high: 0.90
```

The exact configuration schema should be finalized during implementation.

When disabled, DRIFT must behave as closely as possible to its existing implementation.

## Recommended implementation phases

### Phase 1 — abstraction

Create the internal decision-provider interface and result schemas.

No JEV dependency.

### Phase 2 — memory integration

Move importance scoring behind the abstraction.

Preserve the current LLM implementation as the default fallback.

### Phase 3 — JEV adapter

Add JEV as an optional provider.

Keep it isolated behind the provider interface.

### Phase 4 — batch decisions

Batch importance, classification, retention, novelty and related decisions when they share the same state.

### Phase 5 — confidence-aware routing

Use confidence to decide whether to accept, retrieve more evidence, escalate to an LLM, or fall back.

### Phase 6 — evaluation

Build a memory-decision benchmark from DRIFT's own historical memory stream.

Compare:

- deterministic baseline
- current LLM scorer
- JEV
- other decision providers

Measure:

- agreement
- calibration
- false promotion
- false deletion
- retrieval quality
- reflection quality
- latency
- cost
- failure behavior

Do not adopt a provider merely because it is cheap.

## Architectural principle

The important change is not "add JEV."

The change is:

> **DRIFT gains a first-class decision capability that can be supplied by JEV, another decision model, a local model, an LLM, deterministic rules, or nothing at all.**

That makes the architecture future-proof while allowing DRIFT to exploit extremely cheap decision models when they provide measurable value.
