"""Install a bounded context policy on the legacy Brain without making its loop stateful.

The old loop can remain running indefinitely because each model invocation gets a
fresh, bounded working set. Durable truth lives outside the prompt in the ledger,
files and memory store.
"""

from __future__ import annotations

from drift.config import config
from drift.context import build_packet
from drift.organism import DriftLedger


def install(brain_cls) -> None:
    if getattr(brain_cls, "_bounded_context_installed", False):
        return
    original = brain_cls._build_input

    def bounded(self):
        instructions, items = original(self)
        # Keep the conversation/tool transcript bounded. The latest user event and
        # latest tool results are more useful than an unbounded historical trace.
        max_items = int(config.get("context_max_items", 18))
        if len(items) > max_items:
            head = items[:1]
            tail = items[-(max_items - 1):]
            items = head + tail

        try:
            ledger = DriftLedger(self.env_path)
            facts = []
            if self._current_focus:
                facts.append(f"current focus: {self._current_focus}")
            project_text = ledger.data.get("projects", [])
            facts.extend(f"project: {p.get('name')} ({p.get('repo','')})" for p in project_text[-8:])
            recent = [e.get("summary", "") for e in ledger.data.get("events", [])[-8:] if e.get("summary")]
            packet = build_packet(
                task="continuous idea/project observation",
                objective="make one useful, evidence-backed next decision without losing durable state",
                facts=facts,
                recent_events=recent,
                constraints=[
                    "Do not treat the prompt as memory.",
                    "Separate fact, observation, hypothesis and recommendation.",
                    "Prefer writing durable findings to drift.md/research artifacts.",
                    "Do not invent project state when evidence is missing.",
                ],
                budget_chars=int(config.get("context_max_chars", 7000)),
            ).render()
            items.append({"role": "user", "content": "DURABLE CONTEXT PACKET:\n" + packet})
        except Exception:
            pass
        return instructions, items

    brain_cls._build_input = bounded
    brain_cls._bounded_context_installed = True
