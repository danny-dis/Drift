"""The bounded-task cognitive loop — the heart of Drift's production kernel.

The model is a temporary cognitive worker. Durable state lives in the ledger,
task store, memory stream and receipt store. Every model invocation receives a
bounded context packet assembled from durable state — never an unbounded
transcript. Tasks are resumable and idempotent; a restart never loses progress.
"""

import asyncio
import base64
import json
import logging
import os
import random
from datetime import datetime, date

from drift.config import config
from drift.context import (
    ContextPacket,
    MemoryBlock,
    build_packet,
    decay_recency,
    keyword_relevance,
)
from drift.compaction import Compactor
from drift.memory import MemoryStream
from drift.organism import DriftLedger, read_drift_md
from drift.prompts import (
    main_system_prompt,
    REFLECTION_PROMPT,
    PLANNING_PROMPT,
    FOCUS_NUDGE,
)
from drift.providers import chat, chat_short
from drift.receipt import ContextReceipt, ReceiptStore, to_dict
from drift.task import Task, TaskStore
from drift.tools import execute_tool, ensure_venv
from drift.watcher import GitWatcher
from drift.attention import AttentionEconomy, generate_candidates, select_best_candidate, BudgetTracker

logger = logging.getLogger("drift.brain")

LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "drift.log.jsonl")


def _serialize_input(input_list: list) -> list:
    """Convert input_list to JSON-safe dicts for broadcasting."""
    result = []
    for item in input_list:
        if isinstance(item, dict):
            result.append(item)
        elif hasattr(item, "type"):
            if item.type == "function_call":
                result.append(
                    {
                        "type": "function_call",
                        "name": item.name,
                        "arguments": item.arguments,
                        "call_id": item.call_id,
                    }
                )
            elif item.type == "message":
                parts = []
                for c in item.content:
                    if hasattr(c, "text"):
                        parts.append(c.text)
                result.append(
                    {
                        "type": "message",
                        "role": getattr(item, "role", "assistant"),
                        "content": " ".join(parts),
                    }
                )
            elif item.type == "web_search_call":
                result.append({"type": "web_search_call"})
            else:
                result.append({"type": item.type})
        else:
            result.append({"type": "unknown", "repr": str(item)[:200]})
    return result


def _serialize_output(output) -> list:
    """Convert API response output items to JSON-safe dicts."""
    items = []
    for item in output:
        if hasattr(item, "type"):
            if item.type == "message":
                content_parts = []
                for c in item.content:
                    if hasattr(c, "text"):
                        content_parts.append({"type": "text", "text": c.text})
                    else:
                        content_parts.append({"type": getattr(c, "type", "unknown")})
                items.append({"type": "message", "content": content_parts})
            elif item.type == "function_call":
                items.append(
                    {
                        "type": "function_call",
                        "name": item.name,
                        "arguments": item.arguments,
                        "call_id": item.call_id,
                    }
                )
            elif item.type == "web_search_call":
                items.append({"type": "web_search_call", "id": getattr(item, "id", "")})
            else:
                items.append({"type": item.type})
        elif isinstance(item, dict):
            items.append(item)
        else:
            items.append({"type": "unknown", "repr": str(item)[:200]})
    return items


class Brain:
    """Bounded-task cognitive loop.

    Each cycle:
      1. Inspect filesystem and ledger deterministically
      2. Select the highest-value task
      3. Build a bounded context packet from durable state
      4. Invoke the model with the packet
      5. Emit a receipt recording what entered context
      6. Process tool results
      7. Persist findings, update task state
      8. Compact if the active-event threshold is crossed
      9. Clear transient output
    """

    # Room is 12x12 tiles (kept for animal visualization)
    ROOM_LOCATIONS = {
        "desk": {"x": 10, "y": 1},
        "bookshelf": {"x": 1, "y": 2},
        "window": {"x": 4, "y": 0},
        "plant": {"x": 0, "y": 8},
        "bed": {"x": 3, "y": 10},
        "rug": {"x": 5, "y": 5},
        "center": {"x": 5, "y": 5},
    }

    _BLOCKED: set[tuple[int, int]] = set()

    @staticmethod
    def _init_blocked():
        collision_rows = [
            "XXXX..XXXXXX", "..XX...XX...", ".......XXXX.", "..XX...XX...",
            "..XX...XX...", "........XX..", "............", "..XXXXXX..XX",
            "..XX...X..X.", "....XXX...X.", "XX...X.....X", "X....X......",
        ]
        b = set()
        for y, row in enumerate(collision_rows):
            for x, ch in enumerate(row):
                if ch == "X":
                    b.add((x, y))
        return b

    _TEXT_EXTS = {
        ".txt", ".md", ".py", ".json", ".csv", ".yaml", ".yml", ".toml",
        ".js", ".ts", ".html", ".css", ".sh", ".log",
    }
    _PDF_EXTS = {".pdf"}
    _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    _IGNORE_FILES = {"memory_stream.jsonl", "identity.json"}
    _INTERNAL_ROOT_FILES = {"projects.md"}

    PLAN_INTERVAL = 10

    # Mood-based tasks are no longer used — attention economy handles
    # task selection when no work is pending. Kept for reference.
    # MOOD_TASKS = [...]

    def __init__(self, identity: dict, env_path: str):
        self.identity = identity
        self.env_path = env_path
        self.api_calls: list[dict] = []
        self.thought_count: int = 0
        self.state: str = "idle"
        self.running: bool = False
        self._ws_clients: set = set()
        self.stream: MemoryStream | None = None
        self.position = {"x": 5, "y": 5}
        self.latest_snapshot = None
        if not Brain._BLOCKED:
            Brain._BLOCKED = Brain._init_blocked()

        self._seen_env_files: set[str] = set()
        self._inbox_pending: list[dict] = []
        self._cycles_since_plan: int = 0
        self._current_focus: str = ""
        self._focus_mode: bool = False
        self._consecutive_research_cycles: int = 0

        # Conversation state
        self._user_message: str | None = None
        self._conversation_event: asyncio.Event = asyncio.Event()
        self._conversation_reply: str | None = None
        self._waiting_for_reply: bool = False

    # ------------------------------------------------------------------
    # Durable stores (initialized in run())
    # ------------------------------------------------------------------

    def _init_stores(self) -> None:
        """Initialize durable stores. Called once from run()."""
        self.ledger = DriftLedger(self.env_path)
        self.tasks = TaskStore(self.env_path)
        self.receipts = ReceiptStore(self.env_path)
        self.compactor = Compactor(self.ledger, self.stream, config)
        self.attention = AttentionEconomy(self.receipts)
        self._init_watcher()

    def _init_watcher(self) -> None:
        """Create a GitWatcher and register all projects that have a local_path.

        Projects with a local filesystem path are watched for new commits so
        meaningful changes can trigger focused analysis tasks.
        """
        self.watcher = GitWatcher(self.ledger, self.tasks, config)
        for project in self.ledger.data.get("projects", []):
            if project.get("local_path"):
                self.watcher.register_project(project["id"], project["local_path"])
        logger.info(
            "GitWatcher initialized with %d project(s)",
            len(self.watcher.get_watched_projects()),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _read_file(self, rel_path: str) -> str | None:
        fpath = os.path.join(self.env_path, rel_path)
        try:
            with open(fpath, "r", errors="replace") as f:
                return f.read()
        except (FileNotFoundError, IsADirectoryError):
            return None

    def _load_current_focus(self) -> str:
        content = self._read_file("projects.md")
        if not content:
            return ""
        lines = content.split("\n")
        in_focus = False
        focus_lines = []
        for line in lines:
            if line.strip().lower().startswith("# current focus"):
                in_focus = True
                continue
            if in_focus:
                if line.startswith("# "):
                    break
                if line.strip():
                    focus_lines.append(line.strip())
        return " ".join(focus_lines)[:300] if focus_lines else ""

    def _list_env_files(self) -> list[str]:
        env_root = self.env_path
        files = []
        for dirpath, dirnames, filenames in os.walk(env_root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fname in filenames:
                if fname.startswith(".") or fname in Brain._IGNORE_FILES:
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fname), env_root)
                files.append(rel)
        return sorted(files)

    # ------------------------------------------------------------------
    # WebSocket / events
    # ------------------------------------------------------------------

    def add_ws_client(self, ws):
        self._ws_clients.add(ws)

    def remove_ws_client(self, ws):
        self._ws_clients.discard(ws)

    async def _broadcast(self, message: dict):
        dead = set()
        for ws in self._ws_clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        self._ws_clients -= dead

    async def _emit(self, event_type: str, **data):
        entry = {
            "type": event_type,
            "timestamp": datetime.now().isoformat(),
            "thought_number": self.thought_count,
            **data,
        }
        await self._broadcast({"event": "entry", "data": entry})
        text = data.get("text", data.get("command", data.get("content", "")))
        logger.info(f"[{event_type}] {str(text)[:120]}")

    async def _emit_api_call(
        self,
        instructions: str,
        input_list: list,
        response: dict,
        is_reflection: bool = False,
        is_planning: bool = False,
    ):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "instructions": instructions,
            "input": _serialize_input(input_list),
            "output": _serialize_output(response["output"]),
            "is_dream": is_reflection,
            "is_planning": is_planning,
        }
        self.api_calls.append(entry)
        await self._broadcast({"event": "api_call", "data": entry})
        try:
            with open(LOG_PATH, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------

    def _is_blocked(self, x: int, y: int) -> bool:
        return (x, y) in Brain._BLOCKED

    async def _handle_move(self, args: dict) -> str:
        location = args.get("location", "center")
        target = Brain.ROOM_LOCATIONS.get(location)
        if not target:
            return f"Unknown location: {location}"
        self.position = {"x": target["x"], "y": target["y"]}
        await self._broadcast({"event": "position", "data": self.position})
        return f"Moved to {location}."

    async def _idle_wander(self):
        dx = random.choice([-1, 0, 1])
        dy = random.choice([-1, 0, 1])
        nx = self.position["x"] + dx
        ny = self.position["y"] + dy
        if not self._is_blocked(nx, ny) and 0 <= nx <= 11 and 0 <= ny <= 11:
            self.position = {"x": nx, "y": ny}
            await self._broadcast({"event": "position", "data": self.position})

    # ------------------------------------------------------------------
    # Conversation
    # ------------------------------------------------------------------

    async def _handle_respond(self, args: dict) -> str:
        msg = args.get("message", "")
        self._waiting_for_reply = True
        self._conversation_event.clear()
        self._conversation_reply = None
        await self._broadcast(
            {"event": "conversation", "data": {"state": "waiting", "message": msg, "timeout": 15}}
        )
        try:
            await asyncio.wait_for(self._conversation_event.wait(), timeout=15)
            text = self._conversation_reply or ""
            reply = f'They say: "{text}"\n(Use respond again to reply, or go back to what you were doing.)'
        except asyncio.TimeoutError:
            reply = "(They didn’t say anything else. You can get back to what you were doing.)"
        self._waiting_for_reply = False
        self._conversation_event.clear()
        self._conversation_reply = None
        await self._broadcast({"event": "conversation", "data": {"state": "ended"}})
        return reply

    def receive_user_message(self, text: str):
        self._user_message = text

    def receive_conversation_reply(self, text: str):
        self._conversation_reply = text
        self._conversation_event.set()

    async def set_focus_mode(self, enabled: bool):
        self._focus_mode = enabled
        await self._broadcast({"event": "focus_mode", "data": {"enabled": enabled}})

    # ------------------------------------------------------------------
    # File detection
    # ------------------------------------------------------------------

    def _scan_env_files(self) -> set[str]:
        env_root = self.env_path
        files = set()
        for dirpath, dirnames, filenames in os.walk(env_root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fname in filenames:
                if fname.startswith(".") or fname in Brain._IGNORE_FILES:
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fname), env_root)
                files.add(rel)
        return files

    def _check_new_files(self) -> list[dict]:
        current = self._scan_env_files()
        new_paths = current - self._seen_env_files
        self._seen_env_files = current
        env_root = self.env_path
        results = []
        for rel_path in sorted(new_paths):
            fpath = os.path.join(env_root, rel_path)
            if not os.path.isfile(fpath):
                continue
            ext = os.path.splitext(rel_path)[1].lower()
            entry: dict = {"name": rel_path, "content": "", "image": None}
            if ext in Brain._PDF_EXTS:
                try:
                    import pymupdf
                    doc = pymupdf.open(fpath)
                    pages = [page.get_text() for page in doc]
                    doc.close()
                    text = "\n\n".join(pages)
                    entry["content"] = text[:4000] if text.strip() else "(PDF has no extractable text)"
                except ImportError:
                    entry["content"] = "(install pymupdf to read PDFs: pip install pymupdf)"
                except Exception:
                    entry["content"] = "(could not read PDF)"
            elif ext in Brain._TEXT_EXTS:
                try:
                    text = open(fpath, "r", errors="replace").read()
                    entry["content"] = text[:2000]
                except Exception:
                    entry["content"] = "(could not read file)"
            elif ext in Brain._IMAGE_EXTS:
                try:
                    data = open(fpath, "rb").read()
                    mime = (
                        "image/png" if ext == ".png"
                        else "image/jpeg" if ext in (".jpg", ".jpeg")
                        else "image/gif" if ext == ".gif" else "image/webp"
                    )
                    entry["image"] = f"data:{mime};base64,{base64.b64encode(data).decode()}"
                except Exception:
                    entry["content"] = "(could not read image)"
            else:
                entry["content"] = f"(binary file: {rel_path})"
            results.append(entry)
        return results

    # ------------------------------------------------------------------
    # Activity classification
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_activity(tool_name: str, tool_args: dict) -> dict:
        if tool_name == "move":
            loc = tool_args.get("location", "")
            return {"type": "moving", "detail": f"Going to {loc}"}
        if tool_name == "respond":
            return {"type": "conversing", "detail": "Talking to someone..."}
        if tool_name in ("fetch_url", "web_search", "web_fetch"):
            return {"type": "searching", "detail": f"{tool_name.replace('_', ' ')}..."}
        if tool_name == "shell":
            cmd = tool_args.get("command", "").strip()
            if cmd.startswith("python"):
                detail = cmd[:60] + ("..." if len(cmd) > 60 else "")
                return {"type": "python", "detail": detail}
            if ">" in cmd or cmd.startswith("cat >") or cmd.startswith("tee "):
                parts = cmd.split(">")
                fname = parts[-1].strip().split()[0] if len(parts) > 1 else "file"
                return {"type": "writing", "detail": f"Writing {fname}"}
            if cmd.startswith(("cat ", "head ", "tail ", "ls", "find ", "grep ")):
                return {"type": "reading", "detail": cmd[:50]}
            return {"type": "shell", "detail": cmd[:50]}
        return {"type": "working", "detail": tool_name}

    # ------------------------------------------------------------------
    # Bounded context assembly (the production core)
    # ------------------------------------------------------------------

    def _build_task_context(self, task) -> tuple[str, list[dict], dict]:
        """Build a bounded context packet from durable state.

        Returns (instructions, input_list, meta) where meta tracks what was
        selected for the receipt.
        """
        instructions = main_system_prompt(self.identity, self._current_focus)
        budget_chars = int(config.get("context_max_chars", 7000))

        input_list: list[dict] = []
        selected_memory_ids: list[str] = []
        selection_scores: dict[str, float] = {}
        evidence_ids: list[str] = []
        excluded_high_score: list[str] = []

        # 1. Retrieve recent memories (bounded)
        if self.stream:
            memories = self.stream.retrieve(
                task.objective or task.goal,
                top_k=int(config.get("memory_retrieval_count", 5)),
            )
            for m in memories:
                score = decay_recency(m.get("timestamp", "")) + m.get("importance", 5) / 10.0
                selected_memory_ids.append(m.get("id", ""))
                selection_scores[m.get("id", "")] = round(score, 3)

        # 2. Build a ContextPacket from durable state
        project_state = []
        relevant_ideas = []
        facts = [f"Current task: {task.goal}"]

        if task.project_id:
            project = next(
                (p for p in self.ledger.data.get("projects", []) if p["id"] == task.project_id),
                None,
            )
            if project:
                project_state.append(f"name={project['name']}")
                project_state.append(f"repo={project.get('repo', '')}")
                if project.get("local_path"):
                    drift_md = read_drift_md(project["local_path"])
                    if drift_md:
                        evidence_ids.append(f"drift-md:{task.project_id}")
                        project_state.append(f"drift_md_available=true")
                facts.append(f"project: {project['name']} ({project.get('repo', '')})")

        # Pull relevant ideas from the ledger
        for idea in self.ledger.data.get("ideas", [])[-20:]:
            if task.project_id and task.project_id in idea.get("related_projects", []):
                relevant_ideas.append(idea.get("text", ""))
                evidence_ids.append(idea.get("id", ""))

        # Recent events (bounded, last 8)
        recent_events = []
        for ev in self.ledger.data.get("events", [])[-8:]:
            if ev.get("summary"):
                recent_events.append(ev["summary"])
                if task.project_id and task.project_id in ev.get("related_projects", []):
                    evidence_ids.append(f"event:{ev.get('timestamp', '')}")

        # Convert memories to MemoryBlock list
        memory_blocks = []
        if self.stream:
            for m in self.stream.retrieve(task.objective or task.goal, top_k=10):
                mem_id = m.get("id", "")
                score = selection_scores.get(mem_id, 0.5)
                memory_blocks.append(
                    MemoryBlock(
                        id=mem_id,
                        text=m.get("content", ""),
                        kind=m.get("kind", "observation"),
                        importance=m.get("importance", 5) / 10.0,
                        confidence=m.get("confidence", 0.5),
                        relevance=keyword_relevance(task.objective or task.goal, m.get("content", "")),
                        recency=decay_recency(m.get("timestamp", "")),
                        created_at=m.get("timestamp", ""),
                    )
                )

        # Sort by score and track excluded items
        memory_blocks.sort(key=lambda mb: mb.score(), reverse=True)
        for mb in memory_blocks:
            if mb.score() < 0.3 and len(memory_blocks) > 3:
                excluded_high_score.append(mb.id)

        packet = build_packet(
            task=task.goal,
            objective=task.objective,
            facts=facts,
            recent_events=recent_events[-5:],
            relevant_ideas=relevant_ideas[-5:],
            project_state=project_state,
            constraints=[
                "Separate fact, observation, hypothesis and recommendation.",
                "Cite evidence for consequential claims.",
                "Do not treat missing context as proof that something does not exist.",
                f"Task phase: {task.phase}. Next action: {task.next_action or 'decide'}",
            ],
            evidence=evidence_ids[:10],
            memories=memory_blocks[:7],
            budget_chars=budget_chars,
        )

        rendered = packet.render(budget_chars)
        input_list.append({"role": "user", "content": rendered})

        meta = {
            "context_budget": budget_chars,
            "estimated_tokens": max(1, len(rendered) // 4),
            "selected_memory_ids": selected_memory_ids,
            "selection_scores": selection_scores,
            "evidence_ids": evidence_ids,
            "excluded_high_score": excluded_high_score,
        }
        return instructions, input_list, meta

    # ------------------------------------------------------------------
    # Model invocation with receipt
    # ------------------------------------------------------------------

    async def _invoke_model(
        self, task, input_list: list, instructions: str
    ) -> dict:
        """Invoke the model for a single bounded task attempt."""
        max_tokens = config.get("max_output_tokens", 1000)
        try:
            response = await asyncio.to_thread(
                chat, input_list, True, instructions, max_tokens
            )
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            await self._emit("error", text=str(e))
            raise
        return response

    def _save_receipt(
        self, task, meta: dict, response: dict, cost: float | None = None
    ) -> None:
        """Persist a context receipt for debugging context decisions."""
        receipt = ContextReceipt(
            task_id=task.id,
            context_budget=meta["context_budget"],
            estimated_tokens=meta["estimated_tokens"],
            selected_memory_ids=meta["selected_memory_ids"],
            selection_scores=meta["selection_scores"],
            evidence_ids=meta["evidence_ids"],
            excluded_high_score=meta["excluded_high_score"],
            model_provider=config.get("provider", "openai"),
            estimated_cost=cost,
            result_confidence=None,
        )
        self.receipts.save_receipt(receipt)
        logger.info(
            "Receipt: task=%s memories=%d evidence=%d tokens~=%d",
            task.id, len(meta["selected_memory_ids"]),
            len(meta["evidence_ids"]), meta["estimated_tokens"],
        )

    # ------------------------------------------------------------------
    # Think cycle (bounded, task-based)
    # ------------------------------------------------------------------

    async def _think_once(self):
        """One bounded cognitive cycle: select task → build context → invoke → persist."""
        self.state = "thinking"
        await self._broadcast(
            {"event": "status", "data": {"state": "thinking", "thought_count": self.thought_count}}
        )

        # 1. Select task
        task = self.tasks.get_next_task()
        if task is None:
            task = self._create_attention_task()
            if task:
                logger.info(f"No pending tasks, created attention task: {task.goal}")

        # If still no task (budget exhausted, no candidates), idle
        if task is None:
            logger.debug("No tasks available, idling")
            return

        # 2. Build bounded context
        instructions, input_list, meta = self._build_task_context(task)

        # Handle pending user messages (insert as context)
        if self._user_message:
            input_list.insert(0, {
                "role": "user",
                "content": f'A voice from outside says: "{self._user_message}"\n'
                           "You can respond with the respond tool, or keep working.",
            })
            self._user_message = None

        # Handle pending inbox files
        if self._inbox_pending:
            parts = ["Someone left something for you!"]
            for f in self._inbox_pending:
                parts.append(f"📎 {f['name']}")
                if f.get("content"):
                    parts.append(f["content"][:2000])
            input_list.insert(0, {"role": "user", "content": "\n\n".join(parts)})
            self._inbox_pending = []

        # 3. Invoke model
        try:
            response = await self._invoke_model(task, input_list, instructions)
        except Exception:
            return

        await self._emit_api_call(instructions, input_list, response)
        self._save_receipt(task, meta, response)

        # 4. Process tool loop
        pre_cycle_files = self._scan_env_files()
        did_research = False
        max_tool_rounds = config.get("max_tool_rounds", 12)
        tool_round = 0

        while response.get("tool_calls"):
            tool_round += 1
            if tool_round > max_tool_rounds:
                logger.warning("Hit max tool rounds (%d), stopping", max_tool_rounds)
                break

            if response.get("text"):
                await self._emit("thought", text=response["text"])

            input_list += response["output"]

            for tc in response["tool_calls"]:
                tool_name = tc["name"]
                tool_args = tc["arguments"]
                call_id = tc["call_id"]

                if tool_name in ("web_search", "web_fetch", "fetch_url"):
                    did_research = True

                await self._emit("tool_call", tool=tool_name, args=tool_args)
                activity = self._classify_activity(tool_name, tool_args)
                await self._broadcast({"event": "activity", "data": activity})

                pre_tool_files = self._scan_env_files()

                try:
                    if tool_name == "move":
                        result = await self._handle_move(tool_args)
                    elif tool_name == "respond":
                        result = await self._handle_respond(tool_args)
                    else:
                        result = await asyncio.to_thread(
                            execute_tool, tool_name, tool_args, self.env_path
                        )
                except Exception as e:
                    result = f"Error: {e}"

                await self._broadcast({"event": "activity", "data": {"type": "idle", "detail": ""}})
                await self._emit("tool_result", tool=tool_name, output=result)

                post_tool_files = self._scan_env_files()
                self._seen_env_files |= post_tool_files - pre_tool_files

                input_list.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "name": tool_name,
                        "output": result,
                    }
                )

            # Bounded context for follow-up calls — append only tool results
            try:
                response = await asyncio.to_thread(
                    chat, input_list, True, instructions, config.get("max_output_tokens", 1000)
                )
            except Exception as e:
                if "500" in str(e):
                    await asyncio.sleep(2)
                    try:
                        response = await asyncio.to_thread(
                            chat, input_list, True, instructions, config.get("max_output_tokens", 1000)
                        )
                    except Exception as e2:
                        logger.error(f"LLM follow-up failed after retry: {e2}")
                        break
                else:
                    logger.error(f"LLM follow-up failed: {e}")
                    break

            await self._emit_api_call(instructions, input_list, response)

        # 5. Track research/output ratio
        post_cycle_files = self._scan_env_files()
        created_files = post_cycle_files - pre_cycle_files
        if created_files:
            self._consecutive_research_cycles = 0
        elif did_research:
            self._consecutive_research_cycles += 1

        # 6. Persist thought
        if response.get("text"):
            self.thought_count += 1
            await self._emit("thought", text=response["text"])
            try:
                await asyncio.to_thread(self.stream.add, response["text"], "thought")
            except Exception as e:
                logger.error(f"Memory add failed: {e}")

        # 7. Advance task phase
        self._advance_task(task, created_files)

    # ------------------------------------------------------------------
    # Task management
    # ------------------------------------------------------------------

    def _create_attention_task(self) -> Task | None:
        """Create a task using the attention economy.

        Generates candidates from all signals, scores them, and selects
        the highest-value one within budget. Returns None if no candidates
        exist or budget is exhausted.
        """
        candidate = self.attention.generate_and_select(self)
        if candidate is None:
            return None
        return self.attention.create_task_from_candidate(self, candidate)

    def _advance_task(self, task, created_files: set) -> None:
        """Advance the task phase based on outcomes."""
        from drift.task import can_transition

        if created_files:
            # Task produced output — mark progress
            if task.phase in ("capture", "understand", "connect"):
                if can_transition(task, "research"):
                    self.tasks.update_task(task.id, phase="research", progress=0.3)
            elif task.phase == "research":
                if can_transition(task, "synthesize"):
                    self.tasks.update_task(task.id, phase="synthesize", progress=0.7)
            elif task.phase == "synthesize":
                if can_transition(task, "complete"):
                    self.tasks.update_task(task.id, phase="complete", status="complete", progress=1.0)

    # ------------------------------------------------------------------
    # Reflection (bounded, model call with receipt)
    # ------------------------------------------------------------------

    async def _reflect(self):
        """Reflection cycle — triggered by accumulated importance. Bounded."""
        self.state = "reflecting"
        await self._broadcast(
            {"event": "status", "data": {"state": "reflecting", "thought_count": self.thought_count}}
        )
        await self._emit("reflection_start")

        recent_memories = self.stream.get_recent(n=15)
        if not recent_memories:
            self.stream.reset_importance_sum()
            return

        memories_text = "\n\n".join(
            f"[{m['kind']}] (importance {m['importance']}): {m['content']}"
            for m in recent_memories
        )

        reflect_input = [
            {"role": "user", "content": f"Your recent memories:\n\n{memories_text}"}
        ]

        try:
            reflect_response = await asyncio.to_thread(
                chat, reflect_input, False, REFLECTION_PROMPT
            )
            await self._emit_api_call(
                REFLECTION_PROMPT, reflect_input, reflect_response, is_reflection=True
            )
            reflection_text = reflect_response["text"] or ""
        except Exception as e:
            logger.error(f"Reflection failed: {e}")
            await self._emit("error", text=f"Reflection failed: {e}")
            self.stream.reset_importance_sum()
            return

        source_ids = [m["id"] for m in recent_memories]
        insights = [line.strip() for line in reflection_text.split("\n") if line.strip()]

        for insight in insights:
            try:
                await asyncio.to_thread(
                    self.stream.add, insight, "reflection", 1, source_ids
                )
            except Exception as e:
                logger.error(f"Failed to store reflection: {e}")

        await self._emit("reflection", text=reflection_text)
        self.stream.reset_importance_sum()

    # ------------------------------------------------------------------
    # Planning (bounded, model call with receipt)
    # ------------------------------------------------------------------

    async def _plan(self):
        """Planning phase — review state, update projects.md. Bounded."""
        self.state = "planning"
        await self._broadcast(
            {"event": "status", "data": {"state": "planning", "thought_count": self.thought_count}}
        )

        projects = self._read_file("projects.md") or "(no projects.md yet)"
        files = self._list_env_files()
        recent_memories = self.stream.get_recent(n=10)
        memories_text = (
            "\n".join(f"- {m['content']}" for m in recent_memories)
            if recent_memories
            else "(none yet)"
        )

        plan_input = [
            {
                "role": "user",
                "content": f"""Time to plan. Here's your current state:

## Current projects.md:
{projects[:2000]}

## Files in your world:
{chr(10).join(files[:30]) if files else '(empty)'}

## Recent thoughts:
{memories_text}""",
            }
        ]

        try:
            plan_response = await asyncio.to_thread(
                chat, plan_input, False, PLANNING_PROMPT
            )
            await self._emit_api_call(
                PLANNING_PROMPT, plan_input, plan_response, is_planning=True
            )
            plan_text = plan_response["text"] or ""
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            await self._emit("error", text=f"Planning failed: {e}")
            return

        if not plan_text:
            return

        plan_body = plan_text
        log_entry = ""
        if "LOG:" in plan_text:
            idx = plan_text.index("LOG:")
            plan_body = plan_text[:idx].strip()
            log_entry = plan_text[idx + 4 :].strip()

        env_root = self.env_path
        try:
            with open(os.path.join(env_root, "projects.md"), "w") as f:
                f.write(plan_body)
        except Exception as e:
            logger.error(f"Failed to write projects.md: {e}")

        if log_entry:
            log_dir = os.path.join(env_root, "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, f"{date.today().isoformat()}.md")
            try:
                now_str = datetime.now().strftime("%I:%M %p")
                with open(log_path, "a") as f:
                    f.write(f"\n## {now_str}\n{log_entry}\n")
            except Exception as e:
                logger.error(f"Failed to write daily log: {e}")

        self._current_focus = self._load_current_focus()
        self._cycles_since_plan = 0
        self._seen_env_files = self._scan_env_files()

        await self._emit("planning", text=plan_text)

    # ------------------------------------------------------------------
    # Main loop (bounded, task-based, with compaction)
    # ------------------------------------------------------------------

    async def run(self):
        self.running = True
        logger.info(f"{self.identity['name']} is waking up...")

        await asyncio.to_thread(ensure_venv, self.env_path)
        self.stream = await asyncio.to_thread(MemoryStream, self.env_path)
        self._init_stores()

        all_files = self._scan_env_files()
        self._seen_env_files = {
            f for f in all_files if os.sep in f or f in Brain._INTERNAL_ROOT_FILES
        }
        self._current_focus = self._load_current_focus()
        logger.info(f"{self.identity['name']} is ready.")

        while self.running:
            # 1. Check for new files
            new_files = self._check_new_files()
            if new_files:
                self._inbox_pending = new_files
                await self._broadcast({"event": "alert"})

            # 2. Deterministic compaction check
            if self.compactor.should_compact():
                logger.info("Compaction threshold crossed, compacting events")
                findings = self.compactor.compact_events()
                await self._emit("compaction", count=len(findings))
                self.compactor.decay_stale_memories()

            # 3. Git watcher scan — detect meaningful changes, create analysis tasks
            if hasattr(self, 'watcher') and self.watcher.get_watched_projects():
                try:
                    changes = await asyncio.to_thread(self.watcher.scan_all)
                    for change in changes:
                        if self.watcher.should_analyze(change):
                            task = self.watcher.create_analysis_task(change)
                            if task:
                                logger.info(
                                    "GitWatcher created task %s for %s",
                                    task.id, change.project_id,
                                )
                                await self._emit(
                                    "git_analysis",
                                    project=change.project_id,
                                    commit=change.commit_hash[:8],
                                )
                except Exception as e:
                    logger.warning("GitWatcher scan failed: %s", e)

            # 4. Bounded cognitive cycle
            await self._think_once()

            # 5. Reflection (bounded)
            if self.stream.should_reflect():
                await self._reflect()

            # 6. Planning (bounded, periodic)
            self._cycles_since_plan += 1
            if self._cycles_since_plan >= Brain.PLAN_INTERVAL:
                await self._plan()

            # 7. Idle + broadcast state
            self.state = "idle"
            await self._broadcast(
                {"event": "status", "data": {"state": "idle", "thought_count": self.thought_count}}
            )
            await self._idle_wander()
            await asyncio.sleep(config["thinking_pace_seconds"])

    def stop(self):
        self.running = False
        self.state = "idle"
