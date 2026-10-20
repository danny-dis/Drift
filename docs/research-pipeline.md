# Saved research

A research session keeps its question, sources, notes and report attempts on disk. It also records the phase, revision and next action so a restart does not discard the work. Failed reports stay available for review.

`ResearchStore` records tool, script and file-change history. Recording a script does not execute it. Relative paths must stay inside the research folder, and an OS-backed writer lock prevents separate processes from overwriting each other's updates. The lock releases when its owner exits.

A citation check verifies the link to a retained source and quote. It does not prove the finding is true. Coverage and conflict scores use word matching, not semantic certainty. Read the sources yourself before relying on a report.

To retry a stopped session, use the explicit resume control. `POST /api/ui/research/sessions/{id}/resume` keeps the same task and sources, with a limited number of repairs. An interrupted repair can recover without spending another attempt. Completed sessions and exhausted repairs cannot be resumed through that endpoint.

The implementation is in `drift/research.py`, `drift/brain.py` and `drift/ui_api.py`.
