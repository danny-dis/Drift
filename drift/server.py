"""FastAPI web server — Drift organism API + WebSocket + frontend."""

import asyncio
import hashlib
import json
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from drift.brain import Brain
from drift.config import config
from drift.identity import _derive_traits
from drift.organism_api import router as organism_router
from drift.ui_api import router as ui_router
from drift.capture_api import router as capture_router
from drift.project_intelligence_api import router as intelligence_router
from drift.capture_insights_api import router as insights_router

logger = logging.getLogger("drift.server")

@asynccontextmanager
async def _lifespan(application: FastAPI):
    try:
        await startup()
        yield
    finally:
        await _shutdown()


app = FastAPI(title="Drift", lifespan=_lifespan)
brains: dict[str, Brain] = {}
_tasks: set = set()  # tracked handles for graceful shutdown
_brain_tasks: dict[str, asyncio.Task] = {}
_task_failures: dict[str, dict] = {}
_shutting_down = False


def _origin_allowed(connection) -> bool:
    origin = connection.headers.get("origin")
    if not origin:
        return True  # native clients; browser requests supply Origin
    scheme = "https" if connection.url.scheme in ("https", "wss") else "http"
    same_origin = f"{scheme}://{connection.headers.get('host', '')}"
    allowed = os.environ.get("DRIFT_ALLOWED_ORIGINS", "").split(",")
    return origin == same_origin or origin in [o.strip() for o in allowed if o.strip()]


@app.middleware("http")
async def _bearer_guard(request: Request, call_next):
    from fastapi.responses import JSONResponse
    import hmac
    if not _origin_allowed(request):
        return JSONResponse({"detail": "foreign origin blocked"}, status_code=403)
    token = os.environ.get("DRIFT_API_TOKEN", "")
    if token and request.url.path.startswith("/api/"):
        got = request.headers.get("authorization", "")
        if not hmac.compare_digest(got, f"Bearer {token}"):
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)


async def _authorize_websocket(ws: WebSocket) -> bool:
    import hmac
    token = os.environ.get("DRIFT_API_TOKEN", "")
    if not _origin_allowed(ws):
        await ws.close(code=4403)
        return False
    if token and not hmac.compare_digest(ws.headers.get("authorization", ""), f"Bearer {token}"):
        await ws.close(code=4401)
        return False
    return True


def _track_task(coroutine, crab_id=None):
    task = asyncio.create_task(coroutine)
    _tasks.add(task)
    if crab_id is not None:
        _brain_tasks[crab_id] = task

    def finished(done):
        _tasks.discard(done)
        error = None if done.cancelled() else done.exception()
        if error is not None:
            failure = {"type": type(error).__name__, "at": time.time()}
            _task_failures[crab_id if crab_id is not None else "startup"] = failure
            logger.error("Runtime task ended (%s)", failure["type"])

    task.add_done_callback(finished)
    return task


async def _shutdown():
    global _shutting_down
    _shutting_down = True
    pending = list(_tasks)
    for t in pending:
        t.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    _tasks.clear()


def create_app(all_brains: dict[str, Brain]) -> FastAPI:
    """Initialize the app with the running Drift organisms."""
    global brains
    brains = all_brains
    app.state.drift_brains = brains
    for brain in brains.values():
        if not hasattr(brain, "ledger"):
            brain._init_stores()
    if getattr(app.state, "routes_installed", False):
        return app
    app.include_router(organism_router)
    app.include_router(ui_router)
    app.include_router(capture_router)
    app.include_router(intelligence_router)
    app.include_router(insights_router)
    app.state.routes_installed = True

    # Register frontend catch-all LAST so it doesn't shadow API routes
    from drift.runtime_resources import frontend_directory
    frontend_dist = str(frontend_directory())
    if os.path.isdir(frontend_dist):
        app.mount(
            "/assets",
            StaticFiles(directory=os.path.join(frontend_dist, "assets")),
            name="assets",
        )

        @app.get("/{full_path:path}")
        async def serve_frontend(full_path: str):
            from pathlib import Path
            if full_path.startswith("api/"):
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail="endpoint not found")
            base = Path(frontend_dist).resolve()
            target = (base / full_path).resolve()
            try:
                target.relative_to(base)  # traversal guard (not prefix)
            except ValueError:
                return FileResponse(os.path.join(frontend_dist, "index.html"))
            if target.is_file():
                return FileResponse(str(target))
            return FileResponse(os.path.join(frontend_dist, "index.html"))

    return app


def _get_brain(request: Request) -> Brain:
    """Look up brain by ?crab=ID for backwards compatibility."""
    from fastapi import HTTPException
    crab_id = request.query_params.get("crab")
    if not brains:
        raise HTTPException(status_code=503, detail="no organisms running")
    if crab_id:
        if crab_id not in brains:
            raise HTTPException(status_code=404, detail="organism not found")
        return brains[crab_id]
    return next(iter(brains.values()))


app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])
if os.environ.get("DRIFT_ALLOWED_ORIGINS"):
    app.add_middleware(CORSMiddleware,
        allow_origins=os.environ["DRIFT_ALLOWED_ORIGINS"].split(","),
        allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])


@app.websocket("/ws/{crab_id}")
async def websocket_endpoint(ws: WebSocket, crab_id: str):
    if not await _authorize_websocket(ws):
        return
    brain = brains.get(crab_id)
    if not brain:
        await ws.close(code=4004)
        return
    await ws.accept()
    brain.add_ws_client(ws)
    logger.info(f"WebSocket client connected to {crab_id}")
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        brain.remove_ws_client(ws)
        logger.info(f"WebSocket client disconnected from {crab_id}")


@app.websocket("/ws")
async def websocket_default(ws: WebSocket):
    if not await _authorize_websocket(ws):
        return
    if not brains:
        await ws.close(code=4004)
        return
    brain = next(iter(brains.values()))
    await ws.accept()
    brain.add_ws_client(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        brain.remove_ws_client(ws)


@app.get("/api/crabs")
async def get_crabs():
    return [
        {
            "id": crab_id,
            "name": brain.identity["name"],
            "animal": brain.identity.get("animal", "crab"),
            "state": brain.state,
            "thought_count": brain.thought_count,
        }
        for crab_id, brain in brains.items()
    ]


@app.get("/api/runtime")
async def get_runtime(request: Request):
    """Task liveness, not inference availability; never expose exception text."""
    import hmac
    from fastapi.responses import JSONResponse
    token = os.environ.get("DRIFT_API_TOKEN") or os.environ.get("DRIFT_RUNTIME_TOKEN")
    if not token:
        return JSONResponse({"healthy": False, "detail": "runtime authentication not configured"}, status_code=503)
    if not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {token}"):
        return JSONResponse({"detail": "unauthorized"}, status_code=401)
    status = {}
    for crab_id in brains:
        task = _brain_tasks.get(crab_id)
        state = "starting" if task is None else "running"
        if task is not None and task.done():
            state = "cancelled" if task.cancelled() else "failed" if task.exception() else "stopped"
        status[crab_id] = {"state": state, "alive": state == "running",
                           "error": _task_failures.get(crab_id)}
    healthy = bool(status) and all(s["alive"] for s in status.values()) and not _shutting_down
    return JSONResponse({"healthy": healthy, "shutting_down": _shutting_down,
                         "brains": status, "startup_error": _task_failures.get("startup")},
                        status_code=200 if healthy else 503)


@app.post("/api/crabs")
async def create_crab(request: Request):
    body = await request.json()
    name = body.get("name", "").strip()
    animal = body.get("animal", "crab").strip().lower()
    if not name:
        return {"ok": False, "error": "name is required"}
    import re as _re
    if not _re.fullmatch(r"[A-Za-z0-9_-]{1,40}", name):
        return {"ok": False, "error": "invalid name (letters/numbers/_/- only)"}

    crab_id = name.lower()
    if crab_id in brains:
        return {"ok": False, "error": f"crab '{crab_id}' already exists"}

    from drift.runtime_resources import workspace_root
    project_root = str(workspace_root())
    box_path = os.path.join(project_root, f"{crab_id}_box")
    os.makedirs(box_path, exist_ok=True)
    seed_bytes = hashlib.sha256(
        f"{name}{time.time_ns()}{os.urandom(32).hex()}".encode()
    ).digest()
    identity = {
        "name": name,
        "animal": animal,
        "genome": seed_bytes.hex(),
        "traits": _derive_traits(seed_bytes),
        "born": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(os.path.join(box_path, "identity.json"), "w") as f:
        json.dump(identity, f, indent=2)

    brain = Brain(identity, box_path)
    brains[crab_id] = brain
    app.state.drift_brains = brains
    _track_task(brain.run(), crab_id)
    return {"ok": True, "id": crab_id, "name": name, "animal": animal}


@app.get("/api/identity")
async def get_identity(request: Request):
    return _get_brain(request).identity


@app.get("/api/events")
async def get_events(request: Request, limit: int = 100):
    count = max(0, min(limit, 1000))
    return _get_brain(request).ledger.data.get("events", [])[-count:] if count else []


@app.get("/api/raw")
async def get_raw(request: Request, limit: int = 20):
    return _get_brain(request).api_calls[-limit:]


@app.get("/api/status")
async def get_status(request: Request):
    brain = _get_brain(request)
    from drift.work_activity import snapshot
    return {
        **snapshot(brain),
        "state": brain.state,
        "thought_count": brain.thought_count,
        "importance_sum": brain.stream.importance_sum if brain.stream else 0,
        "reflection_threshold": config["reflection_threshold"],
        "memory_count": len(brain.stream.memories) if brain.stream else 0,
        "model": config["model"],
        "name": brain.identity["name"],
        "animal": brain.identity.get("animal", "crab"),
        "position": brain.position,
        "focus_mode": brain._focus_mode,
    }


@app.post("/api/focus-mode")
async def post_focus_mode(request: Request):
    brain = _get_brain(request)
    body = await request.json()
    enabled = bool(body.get("enabled", False))
    await brain.set_focus_mode(enabled)
    return {"ok": True, "focus_mode": enabled}


@app.post("/api/message")
async def post_message(request: Request):
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
    brain = _get_brain(request)
    body = await request.json()
    brain.latest_snapshot = body.get("image")
    return {"ok": True}


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
    from pathlib import Path
    env_root = Path(os.path.realpath(brain.env_path))
    full = (env_root / path).resolve()
    try:
        full.relative_to(env_root)
    except ValueError:
        return {"path": path, "content": "Blocked: path outside environment."}
    try:
        with open(full, "r") as f:
            return {"path": path, "content": f.read()}
    except Exception as e:
        return {"path": path, "content": f"Error: {e}"}


async def startup():
    global _shutting_down
    _shutting_down = False
    _brain_tasks.clear()
    _task_failures.clear()
    async def _start_brains():
        await asyncio.sleep(0.5)
        for crab_id, brain in brains.items():
            _track_task(brain.run(), crab_id)
            logger.info(f"{brain.identity['name']} ({crab_id}) starting...")

    _track_task(_start_brains())
