"""Fail-closed, operation-local metadata snapshots for archive execution policy."""
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
from types import SimpleNamespace


class ArchivePolicy:
    """Read once per selection/sweep, but refresh at each execution boundary."""

    def __init__(self, root):
        self.ideas, self.projects, self.pages, self.captures = {}, {}, {}, {}
        self.capture_ideas = {}
        self.idea_captures = {}
        self.valid = False
        try:
            def link(idea_id, capture_id):
                if idea_id and capture_id:
                    self.capture_ideas.setdefault(capture_id, set()).add(idea_id)
                    self.idea_captures.setdefault(idea_id, set()).add(capture_id)
            root = Path(root)
            path = root / 'drift_ledger.json'
            data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            self.ideas = {i['id']: i for i in data.get('ideas', [])}
            for idea in self.ideas.values():
                link(idea['id'], idea.get('capture_id'))
            self.projects = {p['id']: p for p in data.get('projects', [])}
            self.pages = {p['id']: p for p in data.get('wiki_pages', [])}
            path = root / 'captures.sqlite3'
            if path.exists():
                # No schema initialization/DDL; never read large originals.
                with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=30)) as db:
                    self.captures = {row[0]: {'archived': bool(row[1]), 'processing_hold': bool(row[2]), 'revision': row[3], 'idea_id': row[4]}
                        for row in db.execute('SELECT id, archived, processing_hold, revision, idea_id FROM captures')}
            for capture_id, capture in self.captures.items():
                link(capture.get('idea_id'), capture_id)
                # Legacy interrupted staging can retain only the established
                # canonical projection ID, before either linkage checkpoint.
                canonical = 'thought-' + capture_id
                if canonical in self.ideas:
                    link(canonical, capture_id)
            self.valid = True
        except (OSError, ValueError, TypeError, KeyError, AttributeError, sqlite3.Error):
            # Corrupt/migrating checkpoints are not permission to execute work.
            self.valid = False

    def _source_records(self, task):
        # Only sources actually retained in this execution's bounded packet are
        # dependencies. Never expand a project into all of its sibling ideas.
        for key in getattr(task, 'context_sources', {}):
            kind, _, source_id = key.partition(':')
            source = SimpleNamespace(goal='', objective='',
                idea_id=source_id if kind == 'idea' else '',
                capture_id=source_id if kind == 'thought' else '',
                project_id=source_id if kind == 'project' else None)
            yield from self._source_records(source)
        if getattr(task, 'wiki_page_id', ''):
            page = self.pages.get(task.wiki_page_id)
            if page is None:
                yield 'missing-wiki-page', {'archived': True}
                return
            for source in page.get('_source_catalog', []):
                source_task = SimpleNamespace(goal='', objective='', wiki_page_id='',
                    idea_id=source['id'] if source['kind'] == 'idea' else '',
                    project_id=source['id'] if source['kind'] == 'project' else None,
                    capture_id=source['id'] if source['kind'] == 'thought' else '')
                yield from self._source_records(source_task)
        idea_id = getattr(task, 'idea_id', '')
        if not idea_id:
            marker = getattr(task, 'last_evidence', '')
            if marker.startswith('attention_dedup_key=idea:'):
                idea_id = marker.removeprefix('attention_dedup_key=idea:')
            else:
                match = re.search(r'\bidea-\d+\b', getattr(task, 'goal', '') + ' ' + getattr(task, 'objective', ''))
                idea_id = match.group(0) if match else ''
        # Resolve the complete capture/projection family in memory. A visible
        # alias must not reintroduce text belonging to an archived sibling.
        pending_ideas = [idea_id] if idea_id else []
        capture_id = getattr(task, 'capture_id', '')
        pending_captures = [capture_id] if capture_id else []
        project_ids = [getattr(task, 'project_id', None)]
        seen_ideas, seen_captures = set(), set()
        while pending_ideas or pending_captures:
            if pending_ideas:
                linked_id = pending_ideas.pop()
                if linked_id in seen_ideas:
                    continue
                seen_ideas.add(linked_id)
                idea = self.ideas.get(linked_id, {})
                yield 'idea:' + linked_id, idea
                project_ids.extend(idea.get('related_projects', []))
                pending_captures.extend(self.idea_captures.get(linked_id, ()))
            else:
                linked_id = pending_captures.pop()
                if linked_id in seen_captures:
                    continue
                seen_captures.add(linked_id)
                capture = self.captures.get(linked_id, {})
                yield 'thought:' + linked_id, capture
                pending_ideas.extend(self.capture_ideas.get(linked_id, ()))
        for pid in dict.fromkeys(filter(None, project_ids)):
            yield 'project:' + pid, self.projects.get(pid, {})

    def context_changed(self, revisions):
        """An assembled packet cannot adopt later permission/source revisions."""
        if not self.valid:
            return True
        catalogs = {'idea': self.ideas, 'project': self.projects, 'thought': self.captures}
        for key, revision in revisions.items():
            kind, _, source_id = key.partition(':')
            record = catalogs.get(kind, {}).get(source_id)
            if record is None or record.get('revision', 0) != revision:
                return True
        return False

    def approval_revisions(self, task):
        """Permission covers these source revisions, never a later archive."""
        return {key: record.get('revision', 0) for key, record in self._source_records(task) if record}

    def source_suppressed(self, task, *, include_holds=False, approvals=None):
        if not self.valid:
            return True
        approvals = approvals or {}
        return any(record.get('archived') or include_holds and record.get('processing_hold')
            and approvals.get(key, -1) != record.get('revision', 0)
            for key, record in self._source_records(task))

    def task_suppressed(self, task):
        approvals = getattr(task, 'processing_approval', {}) if getattr(task, 'processing_approved', False) else {}
        return bool(getattr(task, 'archive_hold', False) or self.source_suppressed(task,
            include_holds=True, approvals=approvals))


def source_archived(root, task):
    """Visibility only: explicit approval may bypass holds, never archives."""
    return ArchivePolicy(root).source_suppressed(task)


def task_suppressed(root, task):
    return ArchivePolicy(root).task_suppressed(task)


def hold_archived_tasks(brain):
    """Never delete task parts or reset attempts; restoration is not approval."""
    brain.tasks.hold_tasks(ArchivePolicy(brain.env_path))


def capture_suppressed(brain, capture):
    if capture.get('archived') or capture.get('processing_hold'):
        return True
    task = SimpleNamespace(idea_id=capture.get('idea_id') or 'thought-' + capture['id'],
        capture_id=capture['id'], project_id=None, goal='', objective='')
    return ArchivePolicy(brain.env_path).source_suppressed(task, include_holds=True) or any(
        t.archive_hold for t in brain.tasks.list_tasks(limit=1000000) if t.capture_id == capture['id'])


def record_archived(root, record, *, policy=None):
    """A generated projection cannot outlive its archived original in active views."""
    if record.get('archived'):
        return True
    if record.get('capture_id'):
        if policy is None:
            policy = ArchivePolicy(root)
        return not policy.valid or bool(policy.captures.get(record['capture_id'], {}).get('archived'))
    return False
