# Four Reference Systems — Drift Integration Mining

Status: architecture input for Drift
Date: 2026-10-05

## Boundary
Drift stays the small autonomous research creature. These ideas should make its continuous loop more reliable without turning it into Ghost Factory, NOESIS or a full agent platform.

## ATLAS·OS → research state discipline
Give each research cycle a simple deterministic state: inbox, selecting, researching, synthesizing, writing, verifying, publishing, sleeping.

Use observable state from pending files, active project, recent failures and current research output to choose the next activity.

Keep the existing personality/mood system as a source of behavior, not as the source of safety or permission.

## Pacifio Atlas → research provenance
Every research session should retain query history, fetched sources, extracted notes, generated report, scripts, file changes and verification status.

Create lightweight checkpoints so a long research task can resume after restart.

Source and derived report must remain distinguishable. Never let a later summary erase the source trail.

## Inferstep ATLAS → research candidate loop
For significant research, generate multiple hypotheses, source-selection strategies or report outlines, then compare them against evidence.

Use deterministic checks where possible: citation presence, source deduplication, broken-link detection, consistency checks and requested-format validation.

Repair weak reports instead of blindly starting over.

This should be optional so ordinary Drift remains lightweight.

## iamvikshan Atlas → bounded intent and tools
When the user drops a file or asks for a focused task, classify the intent and scope before invoking shell/web/file tools.

Read source material before mutating project files. Keep tool permissions tied to the crab box.

Add a review step before publishing substantial research results.

## Ghost Research alignment
Drift can become a small experimental satellite for Ghost Research: formulate hypothesis -> run experiment -> measure -> keep/discard -> write report.

Results should be exportable as evidence, not silently promoted into ecosystem policy.

## Tests
Research session checkpointing, source lineage, tool-scope enforcement, citation validation, bounded repair and restart recovery.

## Non-goals
No large workflow engine, agent federation, model router, global memory service or security claim beyond the actual container/VM boundary.

## Result
Drift becomes a better autonomous research loop: observable state, resumable provenance, candidate-based research and bounded tool discipline while keeping its charm and small footprint.