"""FastAPI web server — API + WebSocket + serves frontend."""

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from drift.brain import Brain
from drift.config import config
from drift.identity import _derive_traits

logger = logging.getLogger("drift.server")

app = FastAPI(title="Drift")
brains: dict[str, Brain] = {}  # cat_id -> Brain


def create_app(all_brains: dict[str, Brain]) -> FastAPI:
    """Initialize the app with brains dict. Called from main.py."""
    global brains
    brains = all_brains
    return app


def _get_brain(request: Request) -> Brain:
    """Look up brain by ?cat=ID query param, or default to first."""
    cat_id = request.query_params.get("cat")
    if cat_id and cat_id in brains:
        return brains[cat_id]
    return next(iter(brains.values()))


# CORS for development (Vite dev server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- WebSocket ---


@app.websocket("/ws/{cat_id}")
async def websocket_endpoint(ws: WebSocket, cat_id: str):
    brain = brains.get(cat_id)
    if not brain:
        await ws.close(code=4004)
        return
    await ws.accept()
    brain.add_ws_client(ws)
    logger.info(f"WebSocket client connected to {cat_id}")
    try:
        while True:
            await ws.receive_text()  # keep connection alive
    except WebSocketDisconnect:
        brain.remove_ws_client(ws)
        logger.info(f"WebSocket client disconnected from {cat_id}")


@app.websocket("/ws")
async def websocket_default(ws: WebSocket):
    """Backwards-compatible /ws — connects to the first brain."""
    if not brains:
        await ws.close(code=4004)
        return
    brain = next(iter(brains.values()))
    await ws.accept()
    brain.add_ws_client(ws)
    logger.info("WebSocket client connected (default)")
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        brain.remove_ws_client(ws)
        logger.info("WebSocket client disconnected (default)")


# --- REST API ---


@app.get("/api/cats")
async def get_cats():
    """List all running cats."""
    return [
        {
            "id": cat_id,
            "name": brain.identity["name"],
            "pet_type": brain.identity.get("pet_type", "cat"),
            "state": brain.state,
            "thought_count": brain.thought_count,
        }
        for cat_id, brain in brains.items()
    ]


@app.post("/api/cats")
async def create_cat(request: Request):
    """Create a new cat at runtime."""
    body = await request.json()
    name = body.get("name", "").strip()
    pet_type = body.get("pet_type", "cat").strip().lower()
    if not name:
        return {"ok": False, "error": "name is required"}

    cat_id = name.lower()
    if cat_id in brains:
        return {"ok": False, "error": f"cat '{cat_id}' already exists"}

    # Create box directory
    project_root = os.path.dirname(os.path.dirname(__file__))
    box_path = os.path.join(project_root, f"{cat_id}_box")
    os.makedirs(box_path, exist_ok=True)

    # Generate identity with random entropy (no interactive keyboard mashing)
    seed_bytes = hashlib.sha256(
        f"{name}{time.time_ns()}{os.urandom(32).hex()}".encode()
    ).digest()
    genome_hex = seed_bytes.hex()
    traits = _derive_traits(seed_bytes)

    identity = {
        "name": name,
        "pet_type": pet_type,
        "genome": genome_hex,
        "traits": traits,
        "born": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    with open(os.path.join(box_path, "identity.json"), "w") as f:
        json.dump(identity, f, indent=2)

    # Start the brain
    brain = Brain(identity, box_path)
    brains[cat_id] = brain
    asyncio.create_task(brain.run())
    logger.info(f"Created and started new {pet_type}: {name} ({cat_id})")

    return {"ok": True, "id": cat_id, "name": name, "pet_type": pet_type}


@app.get("/api/identity")
async def get_identity(request: Request):
    """Get the cat's identity."""
    brain = _get_brain(request)
    return brain.identity


@app.get("/api/events")
async def get_events(request: Request, limit: int = 100):
    brain = _get_brain(request)
    return brain.events[-limit:]


@app.get("/api/raw")
async def get_raw(request: Request, limit: int = 20):
    """Get raw API call history."""
    brain = _get_brain(request)
    return brain.api_calls[-limit:]


@app.get("/api/status")
async def get_status(request: Request):
    brain = _get_brain(request)
    return {
        "state": brain.state,
        "thought_count": brain.thought_count,
        "importance_sum": brain.stream.importance_sum if brain.stream else 0,
        "reflection_threshold": config["reflection_threshold"],
        "memory_count": len(brain.stream.memories) if brain.stream else 0,
        "model": config["model"],
        "name": brain.identity["name"],
        "position": brain.position,
        "focus_mode": brain._focus_mode,
        "focus_topic": brain._focus_topic,
        "focus_remaining": max(0, brain._focus_until - asyncio.get_event_loop().time()) if brain._focus_until > 0 else 0,
        "paused": brain._paused,
        "pace": brain.current_pace,
        "open_loops": brain._open_loops,
    }


@app.post("/api/focus-mode")
async def post_focus_mode(request: Request):
    """Toggle focus mode. Optional: topic (str), duration_minutes (int)."""
    brain = _get_brain(request)
    body = await request.json()
    enabled = bool(body.get("enabled", False))
    topic = str(body.get("topic", ""))
    duration = int(body.get("duration_minutes", 0))
    await brain.set_focus_mode(enabled, topic=topic, duration_minutes=duration)
    return {"ok": True, "focus_mode": enabled, "topic": topic, "duration_minutes": duration}


@app.post("/api/pause")
async def post_pause(request: Request):
    """Pause or resume the thinking loop."""
    brain = _get_brain(request)
    body = await request.json()
    paused = bool(body.get("paused", False))
    await brain.set_paused(paused)
    return {"ok": True, "paused": paused}


@app.post("/api/pace")
async def post_pace(request: Request):
    """Set thinking pace in seconds. Pass null to reset to default."""
    brain = _get_brain(request)
    body = await request.json()
    pace = body.get("pace")
    brain.set_pace(pace)
    return {"ok": True, "pace": brain.current_pace}


@app.post("/api/message")
async def post_message(request: Request):
    """Receive a message from the user (voice from outside the room)."""
    brain = _get_brain(request)
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return {"ok": False, "error": "empty message"}
    if brain._waiting_for_reply:
        brain.receive_conversation_reply(text)
    else:
        brain.receive_user_message(text)
    return {"ok": True}


@app.post("/api/snapshot")
async def post_snapshot(request: Request):
    """Receive a canvas snapshot from the frontend."""
    brain = _get_brain(request)
    body = await request.json()
    brain.latest_snapshot = body.get("image")
    return {"ok": True}


@app.get("/api/activity-since")
async def get_activity_since(request: Request, since: str = ""):
    """Return activity summary since a timestamp (ISO format). Used for 'while you were away' digests."""
    brain = _get_brain(request)
    if not since:
        return {"events": [], "summary": ""}

    try:
        since_dt = datetime.fromisoformat(since)
    except Exception:
        return {"events": [], "summary": ""}

    # Read the log file for recent API calls
    log_path = os.path.join(os.path.dirname(__file__), "..", "drift.log.jsonl")
    events = []
    if os.path.isfile(log_path):
        try:
            with open(log_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    ts = entry.get("timestamp", "")
                    if not ts:
                        continue
                    try:
                        entry_dt = datetime.fromisoformat(ts.replace("Z", "+00:00").replace("+00:00", ""))
                        if entry_dt > since_dt:
                            # Extract key info
                            output = entry.get("output", [])
                            thoughts = []
                            tools = []
                            for item in output:
                                if isinstance(item, dict):
                                    if item.get("type") == "message":
                                        txt = ""
                                        for c in item.get("content", []):
                                            if isinstance(c, dict) and c.get("type") == "output_text":
                                                txt += c.get("text", "")
                                        if txt.strip():
                                            thoughts.append(txt.strip()[:200])
                                    elif item.get("type") == "function_call":
                                        tools.append(item.get("name", "unknown"))
                            if thoughts or tools:
                                events.append({
                                    "timestamp": ts,
                                    "thoughts": thoughts[:3],
                                    "tools": tools[:5],
                                    "is_dream": entry.get("is_dream", False),
                                    "is_planning": entry.get("is_planning", False),
                                })
                    except Exception:
                        continue
        except Exception:
            pass

    # Build a text summary with topic hints
    n_thoughts = sum(len(e["thoughts"]) for e in events)
    n_tools = sum(len(e["tools"]) for e in events)
    n_dreams = sum(1 for e in events if e["is_dream"])
    n_plans = sum(1 for e in events if e["is_planning"])
    summary_parts = []
    if n_thoughts:
        summary_parts.append(f"{n_thoughts} thoughts")
    if n_tools:
        summary_parts.append(f"{n_tools} tool uses")
    if n_dreams:
        summary_parts.append(f"{n_dreams} dream cycles")
    if n_plans:
        summary_parts.append(f"{n_plans} planning sessions")

    # Extract recent topic hints
    recent_topics = []
    for e in events[-10:]:
        for t in e.get("thoughts", [])[:1]:
            first_line = t.split(".")[0][:60].strip()
            if first_line and first_line not in recent_topics:
                recent_topics.append(first_line)
    topic_hint = ""
    if recent_topics:
        topic_hint = " Topics: " + "; ".join(recent_topics[-3:]) + "."

    summary = "While you were away: " + ", ".join(summary_parts) + "." + topic_hint if summary_parts else ""

    return {"events": events[-10:], "summary": summary}


@app.get("/api/memories")
async def get_memories(
    request: Request,
    query: str = "",
    kind: str = "",
    min_importance: int = 0,
    limit: int = 20,
):
    """Search and browse the creature's memories."""
    brain = _get_brain(request)
    if not brain.stream:
        return {"memories": []}

    memories = brain.stream.memories

    # Filter by kind
    if kind:
        memories = [m for m in memories if m["kind"] == kind]

    # Filter by importance
    if min_importance > 0:
        memories = [m for m in memories if m["importance"] >= min_importance]

    # If query provided, use semantic search
    if query:
        results = brain.stream.retrieve(query, top_k=limit)
        # Apply kind/importance filters to semantic results
        if kind:
            results = [m for m in results if m["kind"] == kind]
        if min_importance > 0:
            results = [m for m in results if m["importance"] >= min_importance]
        memories = results
    else:
        # No query — return most recent, sorted by time descending
        memories = memories[-limit:][::-1]

    # Strip embeddings from response (too large)
    return {
        "memories": [
            {
                "id": m["id"],
                "timestamp": m["timestamp"],
                "kind": m["kind"],
                "content": m["content"],
                "importance": m["importance"],
                "depth": m.get("depth", 0),
                "cluster": m.get("cluster", ""),
                "cluster_label": brain.stream.get_cluster_label(m.get("cluster", "")) if m.get("cluster") else "",
            }
            for m in memories
        ]
    }


@app.get("/api/clusters")
async def get_clusters(request: Request):
    """List all memory clusters/themes."""
    brain = _get_brain(request)
    if not brain.stream:
        return {"clusters": []}
    return {"clusters": brain.stream.get_all_clusters()}


@app.get("/api/files")
async def get_files(request: Request):
    brain = _get_brain(request)
    env_root = os.path.realpath(brain.env_path)
    files = []
    for dirpath, _, filenames in os.walk(env_root):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, env_root)
            if not rel.startswith("."):
                files.append(rel)
    files.sort()
    return {"files": files}


@app.get("/api/files/{path:path}")
async def get_file(request: Request, path: str):
    brain = _get_brain(request)
    env_root = os.path.realpath(brain.env_path)
    full = os.path.realpath(os.path.join(env_root, path))
    if not full.startswith(env_root):
        return {"path": path, "content": "Blocked: path outside environment."}
    try:
        with open(full, "r") as f:
            return {"path": path, "content": f.read()}
    except Exception as e:
        return {"path": path, "content": f"Error: {e}"}


# --- Static frontend ---

frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(frontend_dist, "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))


# --- Startup ---


@app.on_event("startup")
async def startup():
    async def _start_brains():
        # Small delay so the server finishes binding the port first
        await asyncio.sleep(0.5)
        for cat_id, brain in brains.items():
            asyncio.create_task(brain.run())
            logger.info(f"{brain.identity['name']} ({cat_id}) starting...")

    asyncio.create_task(_start_brains())
