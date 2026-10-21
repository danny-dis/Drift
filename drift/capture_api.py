"""Capture-first UI endpoints, independent of models and task creation.

The host owns authentication and router registration. Organisms may supply a
``captures`` store; otherwise their ``env_path`` holds the canonical database.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from drift.capture_store import CaptureStore, IdempotencyConflict


router = APIRouter(prefix="/api/ui/captures", tags=["captures"])


def _get_store(request: Request) -> CaptureStore:
    brains = getattr(request.app.state, "drift_brains", {}) or {}
    if not brains:
        raise HTTPException(status_code=503, detail="No Drift organisms running")
    crab_id = request.query_params.get("crab")
    if crab_id:
        if crab_id not in brains:
            raise HTTPException(status_code=404, detail="organism not found")
        brain = brains[crab_id]
    else:
        brain = next(iter(brains.values()))
    store = getattr(brain, "captures", None)
    if store is not None:
        return store
    root = getattr(brain, "env_path", None)
    if root is None:
        raise HTTPException(status_code=503, detail="Capture storage not available")
    return CaptureStore(root)


@router.post("")
async def create_capture(request: Request):
    store = await run_in_threadpool(_get_store, request)
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="body must be valid JSON") from None
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be an object")
    try:
        result = await run_in_threadpool(store.capture, body.get("text"), body.get("client_id"))
        result['capture'] = await run_in_threadpool(store.view, result['capture']['id'])
        return result
    except IdempotencyConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None


@router.get("")
def list_captures(request: Request):
    store = _get_store(request)
    params = request.query_params
    try:
        limit = int(params.get("limit", "50"))
        offset = int(params.get("offset", "0"))
    except ValueError:
        raise HTTPException(status_code=400, detail="limit and offset must be integers") from None
    try:
        return store.list(query=params.get("q", ""), status=params.get("status"),
                          limit=limit, offset=offset,
                          include_archived=params.get("include_archived", "").lower() == "true")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None


@router.get("/{capture_id}")
def get_capture(capture_id: str, request: Request):
    store = _get_store(request)
    try:
        capture = store.view(capture_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    if capture is None:
        raise HTTPException(status_code=404, detail="capture not found")
    return {"capture": capture}


async def _revise_capture(capture_id, request, *, archived=None):
    from drift.ux import mutation_body
    body = await mutation_body(request, {"text"} if archived is None else set(),
                               confirm=archived is not None, revision=archived is not False)
    try:
        capture = _get_store(request).revise(capture_id, text=body.get('text'),
            archived=archived, expected_revision=body.get('expected_revision'))
    except KeyError:
        raise HTTPException(404, 'capture not found') from None
    except IdempotencyConflict:
        raise HTTPException(409, 'revision conflict') from None
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    if archived is True:
        from drift.ui_api import _get_brain
        from drift.archive_policy import hold_archived_tasks
        hold_archived_tasks(_get_brain(request))
    return {'capture': capture}


@router.patch('/{capture_id}')
async def edit_capture(capture_id: str, request: Request):
    return await _revise_capture(capture_id, request)


@router.delete('/{capture_id}')
async def archive_capture(capture_id: str, request: Request):
    return await _revise_capture(capture_id, request, archived=True)


@router.post('/{capture_id}/restore')
async def restore_capture(capture_id: str, request: Request):
    return await _revise_capture(capture_id, request, archived=False)
