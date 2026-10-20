# Background work

Drift checks for saved input and pending tasks between pauses. Owner work comes before optional planning. Every model call still needs a place in the call allowance.

Input is inspected in bounded chunks. The older inbox can ignore recognized noise; the thought-capture path keeps the exact original. An optional decision provider may suggest an action, but it cannot override tool restrictions, approvals or budgets.

`loop_decisions.json` records observed actions, model calls, latency and output counts. Drift does not claim to know how much useful work it missed without labelled examples. It excludes its own memory, budget and decision files from new-input detection.

The code is in `drift/brain.py` and `drift/loop_decisions.py`. The dashboard reads recorded decisions from `/api/ui/decisions`.
