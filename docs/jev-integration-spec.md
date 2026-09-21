# Jev Integration Specification

## Summary
Adds an optional bounded-decision layer to Drift's always-running loop.

## Implementation
- Replace repeated LLM-only importance classification with a Decision Provider.
- Decide whether to research, reflect, plan, respond, sleep, or ignore.
- Preserve append-only memory and reflection hierarchy.
- Batch new-file/event classification.
- Keep shell/web safety deterministic and sandbox-based; Jev is not a security boundary.
- Add hysteresis and measure model calls, latency, output, and missed high-value events.

## Acceptance criteria
- Drift runs unchanged without Jev.
- Full LLM cycles decrease for low-value events.
- Decision output cannot grant capabilities or escape the sandbox.
