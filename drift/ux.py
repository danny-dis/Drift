"""Owner-facing revision validation and archive policy, independent of inference."""
from fastapi import HTTPException
from fastapi import APIRouter, Request
import math

router = APIRouter()


async def mutation_body(request, fields, *, confirm=False, revision=True):
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(422, 'body must be valid JSON') from None
    allowed = set(fields) | {'expected_revision'} | ({'confirm'} if confirm else set())
    if not isinstance(body, dict) or set(body) - allowed:
        raise HTTPException(422, 'unknown fields or invalid body')
    if confirm and body.get('confirm') is not True:
        raise HTTPException(422, 'confirm must be true')
    if revision or 'expected_revision' in body:
        value = body.get('expected_revision')
        if type(value) is not int or value < 0:
            raise HTTPException(422, 'expected_revision must be a nonnegative integer')
    if fields == {'text'} and (not isinstance(body.get('text'), str) or not body['text'].strip()):
        raise HTTPException(422, 'text must be a nonempty string')
    return body


def record_view(record, root=None, *, policy=None):
    from drift.archive_policy import record_archived
    archived = record_archived(root, record, policy=policy) if root is not None else bool(record.get('archived', False))
    return {**record, 'revision': record.get('revision', 0), 'archived': archived}


def _brain(request):
    from drift.ui_api import _get_brain
    return _get_brain(request)


def _record(brain, kind, record_id):
    brain.ledger.reload()
    record = next((r for r in brain.ledger.data[kind] if r['id'] == record_id), None)
    if record is None:
        raise HTTPException(404, kind[:-1] + ' not found')
    return record_view(record, brain.env_path)


async def _change_record(kind, record_id, request, *, archived=None):
    brain = _brain(request)
    fields = {'text'} if kind == 'ideas' else {'name', 'repo', 'local_path', 'importance'}
    body = await mutation_body(request, fields if archived is None else set(),
                               confirm=archived is not None, revision=archived is not False)
    changes = {k: v for k, v in body.items() if k in fields}
    if archived is None and not changes:
        raise HTTPException(422, 'at least one editable field is required')
    for key, value in changes.items():
        if key == 'importance':
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise HTTPException(422, 'importance must be a number between 0 and 1')
        elif key == 'local_path' and value is None:
            continue
        elif not isinstance(value, str) or (key in ('text', 'name') and not value.strip()):
            raise HTTPException(422, key + ' must be a valid string')
        elif len(value) > {'text': 4000, 'name': 200, 'repo': 500, 'local_path': 1024}[key]:
            raise HTTPException(422, key + ' is too long')
    if 'local_path' in changes and changes['local_path']:
        root = getattr(request.app.state, 'projects_root', None)
        if root is not None:
            from drift.local_runtime import check_projects
            try:
                check_projects([changes], root)
            except (ValueError, OSError):
                raise HTTPException(403, 'Project path outside allowed root') from None
    def apply(data):
        record = next((r for r in data[kind] if r['id'] == record_id), None)
        if record is None:
            raise HTTPException(404, kind[:-1] + ' not found')
        current = record.get('revision', 0)
        if 'expected_revision' in body and current != body['expected_revision']:
            raise HTTPException(409, 'revision conflict')
        if kind == 'ideas' and 'text' in changes:
            record.setdefault('original_text', record['text'])
        record.update(changes)
        if archived is not None:
            record['archived'] = archived
        if archived is True:
            record['processing_hold'] = True
        record['revision'] = current + 1
        return record_view(record)
    result = brain.ledger.mutate(apply)
    if archived is True:
        from drift.archive_policy import hold_archived_tasks
        hold_archived_tasks(brain)
    if kind == 'projects':
        watcher = getattr(brain, 'watcher', None)
        if watcher is not None:
            watcher._watched.pop(record_id, None)
            if not result['archived'] and not result.get('processing_hold') and result.get('local_path'):
                watcher.register_project(record_id, result['local_path'])
    return {kind[:-1]: result}


@router.get('/ideas/{record_id}')
async def read_idea(record_id: str, request: Request):
    return {'idea': _record(_brain(request), 'ideas', record_id)}


@router.patch('/ideas/{record_id}')
async def edit_idea(record_id: str, request: Request):
    return await _change_record('ideas', record_id, request)


@router.patch('/projects/{record_id}')
async def edit_project(record_id: str, request: Request):
    return await _change_record('projects', record_id, request)


@router.delete('/ideas/{record_id}')
async def archive_idea(record_id: str, request: Request):
    return await _change_record('ideas', record_id, request, archived=True)


@router.delete('/projects/{record_id}')
async def archive_project(record_id: str, request: Request):
    return await _change_record('projects', record_id, request, archived=True)


@router.post('/ideas/{record_id}/restore')
async def restore_idea(record_id: str, request: Request):
    return await _change_record('ideas', record_id, request, archived=False)


@router.post('/projects/{record_id}/restore')
async def restore_project(record_id: str, request: Request):
    return await _change_record('projects', record_id, request, archived=False)


def active_captures(brain):
    from drift.capture_store import CaptureStore
    store = CaptureStore(brain.env_path)
    offset = 0
    while True:
        page = store.list(limit=1000, offset=offset)
        yield from page['captures']
        offset += len(page['captures'])
        if not page['has_more']:
            break


def canonical_graph(brain):
    brain.ledger.reload()
    from drift.archive_policy import ArchivePolicy, record_archived
    policy = ArchivePolicy(brain.env_path)
    nodes, edges, aliases = {}, set(), {}
    for kind, prefix, section, key in (('idea', 'i:', 'ideas', 'text'), ('project', 'p:', 'projects', 'name')):
        for item in brain.ledger.data[section]:
            if record_archived(brain.env_path, item, policy=policy):
                continue
            node_id = prefix + item['id']
            aliases[item['id']] = node_id
            nodes[node_id] = {'id': node_id, 'kind': kind, 'label': item.get(key, '')[:160],
                              'target': {'section': section, 'id': item['id']}}
    for idea in brain.ledger.data['ideas']:
        if 'i:' + idea['id'] not in nodes:
            continue
        for pid in idea.get('related_projects', []):
            if 'p:' + pid in nodes:
                edges.add(('i:' + idea['id'], 'p:' + pid, 'related_project'))
    for capture in active_captures(brain):
        node_id = 'c:' + capture['id']
        nodes[node_id] = {'id': node_id, 'kind': 'thought', 'label': capture['current_text'][:160],
                          'target': {'section': 'inbox', 'id': capture['id']}}
        target = 'i:' + (capture.get('idea_id') or '')
        if target in nodes:
            edges.add((node_id, target, 'derived_idea'))
    for edge in brain.ledger.data['mind_map']['edges']:
        source, target = aliases.get(edge['source']), aliases.get(edge['target'])
        if source in nodes and target in nodes:
            edges.add((source, target, edge['relation']))
    return {'nodes': list(nodes.values()),
            'edges': [dict(source=s, target=t, relation=r) for s, t, r in sorted(edges)]}


@router.get('/mind-map')
async def mind_map(request: Request):
    return canonical_graph(_brain(request))
