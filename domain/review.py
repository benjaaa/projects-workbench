"""Daily and catch-up task review commands."""
import hashlib
import json
import time
from datetime import datetime

from . import codex_session
from .errors import conflict, invalid_argument
from .handlers import _resolve_task
from .registry import command


DEFAULT_WINDOW_SECONDS = 24 * 60 * 60


def _epoch(value, default=None):
    return codex_session.parse_epoch(value, default=default)


def _window_label(start, end):
    tz = codex_session.LOCAL_TZ
    left = datetime.fromtimestamp(int(start), tz).strftime('%Y-%m-%d %H:%M')
    right = datetime.fromtimestamp(int(end), tz).strftime('%Y-%m-%d %H:%M')
    return f'{left} -> {right}'


def _review_run_id(task_id, window_start, window_end):
    value = f'{task_id}|{int(window_start)}|{int(window_end)}'.encode('utf-8')
    return 'review_' + hashlib.sha1(value).hexdigest()[:20]


def _task_window_start(context, task, window_end=None):
    cursor = context.repositories.latest_completed_review(context.store.db_path, task['id'])
    if cursor and cursor.get('window_end'):
        return int(cursor['window_end']), 'review_cursor'
    created = task.get('created_at') or task.get('created')
    if created:
        try:
            return int(created), 'task_created_at'
        except Exception:
            pass
    return int(window_end or time.time()) - DEFAULT_WINDOW_SECONDS, 'default_24h'


def _text_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    result = []
    for item in value:
        text = str(item or '').strip()
        if text:
            result.append(text)
    return result


def _decisions(value):
    result = []
    for item in value or []:
        if isinstance(item, str):
            if item.strip():
                result.append({'desc': item.strip(), 'by': ''})
        elif isinstance(item, dict):
            text = str(item.get('desc') or item.get('text') or '').strip()
            if text:
                result.append({'desc': text, 'by': str(item.get('by') or '').strip()})
    return result


def _canonical_session_items(value, session_digests):
    result = []
    for item in list(value or []) + list(session_digests or []):
        if isinstance(item, str):
            sid = item
        elif isinstance(item, dict):
            sid = item.get('session_id') or item.get('sid') or item.get('id') or ''
        else:
            continue
        sid = codex_session.canonical_session_id(sid)
        if sid and sid not in {entry['id'] for entry in result}:
            result.append({'id': sid, 'source': 'codex'})
    return result


def _coverage_status(coverage, session_digests):
    failed = int((coverage or {}).get('failed_sessions') or 0)
    for digest in session_digests or []:
        if str(digest.get('status') or '').lower() in ('unreadable', 'partial', 'failed', 'error'):
            failed += 1
    expected = int((coverage or {}).get('included_sessions') or 0)
    provided = len({
        str(item.get('session_id') or item.get('sid') or item.get('id') or '').strip()
        for item in (session_digests or [])
        if isinstance(item, dict)
    } - {''})
    if expected > provided:
        failed += expected - provided
    return 'partial' if failed else 'completed'


@command('review.due', version=1)
def review_due(envelope, context):
    """List tasks whose linked Codex sessions changed since their cursor."""
    data = envelope.input or {}
    window_end = _epoch(data.get('window_end'), default=int(time.time()))
    limit = max(1, min(int(data.get('limit') or 200), 1000))
    due = []
    for task in context.db_read.load_tasks().get('tasks', []):
        links = context.repositories.list_task_session_links(context.store.db_path, task['id'])
        if not links:
            continue
        window_start, cursor_source = _task_window_start(context, task, window_end=window_end)
        if window_start >= window_end:
            continue
        candidates, skipped = codex_session.filter_updated_sessions(
            links,
            window_start,
            window_end,
            state_db=context.repositories.CODEX_DB,
        )
        if not candidates:
            continue
        due.append({
            'task_id': task['id'],
            'title': task.get('title') or '',
            'project': task.get('dir') or task.get('project') or '',
            'window_start': window_start,
            'window_end': window_end,
            'cursor_source': cursor_source,
            'sessions': [
                {
                    'session_id': item['session_id'],
                    'title': item.get('title') or '',
                    'archived': bool(item.get('archived')),
                    'updated_at': item.get('updated_at') or 0,
                }
                for item in candidates
            ],
            'skipped_sessions': skipped,
        })
        if len(due) >= limit:
            break
    due.sort(key=lambda item: max([s.get('updated_at') or 0 for s in item['sessions']] or [0]), reverse=True)
    return {'window_end': window_end, 'tasks': due, 'total': len(due)}


@command('review.prepare', version=1)
def review_prepare(envelope, context):
    """Prepare normalized Codex session packets for one task and window."""
    task = _resolve_task(context, envelope.target)
    data = envelope.input or {}
    window_end = _epoch(data.get('window_end'), default=int(time.time()))
    if data.get('window_start') not in (None, ''):
        window_start = _epoch(data.get('window_start'))
        cursor_source = 'explicit'
    else:
        window_start, cursor_source = _task_window_start(context, task, window_end=window_end)
    if window_start is None:
        raise invalid_argument('window_start is invalid')
    if int(window_start) >= int(window_end):
        raise invalid_argument('window_start must be earlier than window_end')
    max_text_chars = max(1000, min(int(data.get('max_text_chars') or 40000), 200000))
    links = context.repositories.list_task_session_links(context.store.db_path, task['id'])
    sessions, skipped, coverage = codex_session.collect_codex_sessions(
        links,
        window_start,
        window_end,
        state_db=context.repositories.CODEX_DB,
        max_text_chars=max_text_chars,
    )
    run_id = _review_run_id(task['id'], window_start, window_end)
    return {
        'run_id': run_id,
        'task_id': task['id'],
        'task_title': task.get('title') or '',
        'project': task.get('dir') or task.get('project') or '',
        'window_start': int(window_start),
        'window_end': int(window_end),
        'window': _window_label(window_start, window_end),
        'cursor_source': cursor_source,
        'sessions': sessions,
        'skipped_sessions': skipped,
        'coverage': coverage,
    }


@command(
    'review.commit',
    version=1,
    write=True,
    allowed_actors=('agent', 'user', 'system'),
    required_fields=('run_id', 'window_start', 'window_end', 'summary'),
    reason_required=True,
)
def review_commit(envelope, context):
    """Commit one task-level review after all session digest merging."""
    task = _resolve_task(context, envelope.target)
    data = envelope.input or {}
    window_start = _epoch(data.get('window_start'))
    window_end = _epoch(data.get('window_end'))
    if window_start is None or window_end is None or window_start >= window_end:
        raise invalid_argument('window_start and window_end must define a valid range')
    run_id = str(data.get('run_id') or '').strip()
    expected_run_id = _review_run_id(task['id'], window_start, window_end)
    if run_id != expected_run_id:
        raise invalid_argument('run_id does not match task and window')

    session_digests = list(data.get('session_digests') or [])
    sessions = _canonical_session_items(data.get('sessions'), session_digests)
    valid_links = {
        codex_session.canonical_session_id(link.get('sid'))
        for link in context.repositories.list_task_session_links(context.store.db_path, task['id'])
    }
    unlinked = [item['id'] for item in sessions if item['id'] not in valid_links]
    if unlinked:
        raise invalid_argument('sessions are not linked to task', {'session_ids': unlinked})

    coverage = dict(data.get('coverage') or {})
    status = _coverage_status(coverage, session_digests)
    existing = context.repositories.get_review_run(context.store.db_path, run_id)
    if existing and existing.get('status') == 'completed':
        return {
            'task': task,
            'run_id': run_id,
            'entry_id': existing.get('entry_id') or '',
            'status': 'completed',
            'unchanged': True,
        }

    entry = {
        'id': run_id,
        'date': datetime.fromtimestamp(int(window_end), codex_session.LOCAL_TZ).strftime('%m-%d %H:%M:%S'),
        'type': 'review',
        'summary': str(data.get('summary') or '').strip(),
        'window': _window_label(window_start, window_end),
        'sessions': sessions,
        'outputs': _text_list(data.get('outputs')),
        'risks': _text_list(data.get('risks')),
        'pending': _text_list(data.get('pending')),
        'method': _text_list(data.get('method')),
        'decisions': _decisions(data.get('decisions')),
    }
    if existing and existing.get('entry_id'):
        result = context.repositories.update_task_log(task['id'], existing['entry_id'], entry)
    else:
        result = context.repositories.create_task_log(task['id'], entry)
    if not result.get('ok'):
        raise conflict(result.get('error') or 'review.commit failed')

    run_result = context.repositories.upsert_review_run(
        run_id,
        task['id'],
        window_start,
        window_end,
        status,
        result['entry_id'],
        envelope.command_id,
        coverage,
    )
    if not run_result.get('ok'):
        raise conflict(run_result.get('error') or 'review run failed')
    context.repositories.replace_review_session_results(run_id, session_digests)
    context.db_core._log_change(
        'task',
        task['id'],
        'log_entries',
        existing.get('entry_id') if existing else None,
        result['entry_id'],
        f'{envelope.actor.type}:{envelope.actor.id or "unknown"}',
    )
    render_result = context.db_core._trigger_render('task', task['id'])
    return {
        'task': context.db_read.get_task(task['id']),
        'run_id': run_id,
        'entry_id': result['entry_id'],
        'status': status,
        'coverage': coverage,
        'write': {**result, **render_result},
    }
