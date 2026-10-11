"""Deterministic, bounded inspection for recurring background loop inputs."""

import re

_ACTIONS = {"research", "reflect", "plan", "respond", "sleep", "ignore"}
_HIGH_VALUE = re.compile(
    r"\b(urgent|critical|incident|security|investigate|research|analy[sz]e|"
    r"please|request|important|broken|failure|outage|deadline|error)\b", re.I
)
_RESEARCH = re.compile(r"\b(research|investigate|analy[sz]e|compare|find out)\b", re.I)
_REFLECT = re.compile(r"\b(reflect|summari[sz]e|synthesi[sz]e|pattern)\b", re.I)
_PLAN = re.compile(r"\b(plan|roadmap|next steps|prioriti[sz]e)\b", re.I)
_RESPOND = re.compile(r"\b(answer|respond|reply|question)\b", re.I)


def inspect_batch(events: list[dict], *, max_items: int = 24, max_chars: int = 1200) -> dict:
    """Inspect a bounded batch without model calls; retain names and short evidence."""
    items = []
    texts = []
    for event in list(events or [])[:max(0, min(int(max_items), 64))]:
        name = str(event.get("name", ""))[:240]
        content = str(event.get("content", ""))[:max(0, min(int(max_chars), 4000))]
        items.append({"name": name, "content": content})
        texts.append(name + "\n" + content)
    combined = "\n".join(texts)[:max(100, min(len(items) * max_chars, 12000))]
    noise = re.compile(r"^(?:ok|okay|ping|tick|heartbeat|alive|status|nothing new|no changes)[.!\s]*$", re.I)
    high_value = any(_HIGH_VALUE.search(item["name"] + "\n" + item["content"])
                     or bool(item["content"].strip() and not noise.fullmatch(item["content"].strip()))
                     for item in items)
    if not items:
        action = "sleep"
    elif not high_value:
        action = "ignore"
    elif _RESEARCH.search(combined):
        action = "research"
    elif _REFLECT.search(combined):
        action = "reflect"
    elif _PLAN.search(combined):
        action = "plan"
    elif _RESPOND.search(combined):
        action = "respond"
    else:
        action = "research"
    return {"action": action if action in _ACTIONS else "ignore", "high_value": high_value,
            "items": items, "count": len(items)}
