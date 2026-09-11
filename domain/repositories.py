import os
import re
import sqlite3
import time

TASK_PATH_RE = re.compile(r'^2\. Project/2\.1 Project/([^/]+)/tasks/任务-(.+)\.md$')
VAULT = os.environ.get('WORKBENCH_VAULT', '/Users/ben/Documents/Second Brain/Second Brain')
PROJECT_ROOT = '2. Project/2.1 Project'
STATE_DB = os.path.expanduser('~/.hermes/profiles/business_analysis/state.db')
CODEX_DB = os.path.expanduser('~/.codex/state_5.sqlite')


def _connect(db_path):
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def unlink_session(db_path, path='', sid='', project_path=''):
    if not sid:
        return {'ok': False, 'error': 'sid required'}
    conn = _connect(db_path)
    deleted = 0
    try:
        if path:
            match = TASK_PATH_RE.match(path)
            if match:
                project = conn.execute('SELECT id FROM projects WHERE name=?', (match.group(1),)).fetchone()
                if project:
                    task = conn.execute(
                        'SELECT id FROM tasks WHERE title=? AND project_id=?',
                        (match.group(2), project['id']),
                    ).fetchone()
                    if task:
                        cursor = conn.execute(
                            'DELETE FROM task_sessions WHERE task_id=? AND sid=?',
                            (task['id'], sid),
                        )
                        deleted += cursor.rowcount
        if project_path:
            project_name = project_path.rstrip('/').rsplit('/', 1)[-1]
            project = conn.execute('SELECT id FROM projects WHERE name=?', (project_name,)).fetchone()
            if project:
                cursor = conn.execute(
                    'DELETE FROM project_sessions WHERE project_id=? AND sid=?',
                    (project['id'], sid),
                )
                deleted += cursor.rowcount
        cursor = conn.execute('DELETE FROM project_sessions WHERE sid=?', (sid,))
        deleted += cursor.rowcount
        conn.commit()
        return {'ok': True, 'deleted': deleted}
    finally:
        conn.close()


def resolve_project_path(db_path, vault, project_root, project_id='', name=''):
    conn = _connect(db_path)
    try:
        resolved_id = project_id
        if not resolved_id and name:
            row = conn.execute('SELECT id FROM projects WHERE name=?', (name,)).fetchone()
            resolved_id = row['id'] if row else ''
        if not resolved_id:
            return {'ok': False, 'error': 'project not found: ' + (project_id or name)}
        project = conn.execute('SELECT name FROM projects WHERE id=?', (resolved_id,)).fetchone()
        project_name = project['name'] if project else (name or resolved_id)
        row = conn.execute(
            "SELECT path FROM documents WHERE entity_type='project' AND entity_id=? ORDER BY updated_at DESC LIMIT 1",
            (resolved_id,),
        ).fetchone()
        mapped_root = ''
        if row and row['path']:
            normalized = row['path'].replace('\\', '/')
            dir_part = normalized.rsplit('/', 1)[0] if '/' in normalized else project_root
            mapped_root = os.path.join(vault, dir_part)
        root = mapped_root if mapped_root and os.path.isdir(mapped_root) else os.path.join(vault, project_root, project_name)
        if not os.path.isdir(root):
            return {'ok': False, 'error': 'project root not found: ' + root}
        fixed = ''
        if root != mapped_root:
            for filename in os.listdir(root):
                if filename.startswith('项目说明-') and filename.endswith('.md'):
                    fixed = project_root + '/' + project_name + '/' + filename
                    break
            if fixed:
                conn.execute(
                    "UPDATE documents SET path=?, doc_type=?, updated_at=? WHERE entity_type='project' AND entity_id=?",
                    (fixed, fixed, int(time.time()), resolved_id),
                )
                conn.commit()
        return {'ok': True, 'root': root, 'path': fixed or (row['path'] if row else '')}
    finally:
        conn.close()


def list_sessions(ids):
    values = [str(value).strip() for value in ids if str(value).strip()]
    if not values:
        return {'ok': True, 'sessions': []}
    state_db = os.path.join(os.path.expanduser('~'), '.hermes/profiles/business_analysis/state.db')
    conn = sqlite3.connect(state_db)
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ','.join('?' for _ in values)
        rows = conn.execute(
            f'SELECT id, title, cwd, last_activity_at, message_count, source FROM sessions WHERE id IN ({placeholders})',
            values,
        ).fetchall()
        return {'ok': True, 'sessions': [dict(row) for row in rows]}
    finally:
        conn.close()

def _session_dict(row):
    return {
        'id': row['id'],
        'title': row['title'] or '(无标题)',
        'message_count': row['message_count'] or 0,
        'last_activity_at': row['last_activity_at'] or 0,
        'input_tokens': row['input_tokens'] or 0,
        'output_tokens': row['output_tokens'] or 0,
        'source': row['source'] or '',
        'started_at': row['started_at'] or 0,
        'first_user': '',
        'last_assistant': '',
    }


def list_project_sessions(db_path, project_id='', project_name=''):
    wb = _connect(db_path)
    try:
        if not project_id and project_name:
            row = wb.execute('SELECT id, name FROM projects WHERE name=?', (project_name,)).fetchone()
        elif project_id:
            row = wb.execute('SELECT id, name FROM projects WHERE id=?', (project_id,)).fetchone()
        else:
            return {'ok': False, 'error': 'project_id or project_name is required'}
        if not row:
            return {'ok': False, 'error': 'project not found'}
        real_id = row['id']
        project_name = row['name']
        links = wb.execute(
            'SELECT sid, linked_at FROM project_sessions WHERE project_id=? ORDER BY linked_at',
            (real_id,),
        ).fetchall()
    finally:
        wb.close()

    explicit = {row['sid']: row['linked_at'] or 0 for row in links}
    seen = set()
    sessions = []

    if os.path.exists(STATE_DB):
        conn = sqlite3.connect(STATE_DB)
        conn.row_factory = sqlite3.Row
        try:
            for sid in explicit:
                if sid.startswith('codex:') or sid in seen:
                    continue
                row = conn.execute(
                    'SELECT id, title, cwd, last_activity_at, message_count, input_tokens, output_tokens, source, started_at FROM sessions WHERE id=?',
                    (sid,),
                ).fetchone()
                if row:
                    seen.add(sid)
                    sessions.append(_session_dict(row))
            full_cwd = os.path.join(VAULT, PROJECT_ROOT, project_name)
            rows = conn.execute(
                'SELECT id, title, cwd, last_activity_at, message_count, input_tokens, output_tokens, source, started_at FROM sessions WHERE cwd=? OR cwd LIKE ? ORDER BY last_activity_at DESC LIMIT 50',
                (full_cwd, full_cwd + '/%'),
            ).fetchall()
            for row in rows:
                sid = row['id']
                if sid not in seen:
                    seen.add(sid)
                    sessions.append(_session_dict(row))
        finally:
            conn.close()

    codex_ids = [sid for sid in explicit if sid.startswith('codex:') and sid not in seen]
    if codex_ids and os.path.exists(CODEX_DB):
        conn = sqlite3.connect(CODEX_DB)
        conn.row_factory = sqlite3.Row
        try:
            for sid in codex_ids:
                thread_id = sid[len('codex:'):]
                row = conn.execute(
                    "SELECT id, COALESCE(NULLIF(name, ''), title) AS title, created_at, updated_at, recency_at FROM threads WHERE id=?",
                    (thread_id,),
                ).fetchone()
                if not row:
                    continue
                seen.add(sid)
                sessions.append({
                    'id': sid,
                    'title': row['title'] or '(无标题)',
                    'message_count': 0,
                    'last_activity_at': row['updated_at'] or row['recency_at'] or explicit.get(sid) or row['created_at'] or 0,
                    'input_tokens': 0,
                    'output_tokens': 0,
                    'source': 'codex',
                    'started_at': row['created_at'] or 0,
                    'first_user': '',
                    'last_assistant': '',
                })
        finally:
            conn.close()

    sessions.sort(key=lambda item: -(item.get('last_activity_at') or item.get('started_at') or 0))
    return {'ok': True, 'sessions': sessions}


def session_counts(db_path):
    wb = _connect(db_path)
    try:
        projects = {row['id']: row['name'] for row in wb.execute('SELECT id, name FROM projects').fetchall()}
        links = wb.execute('SELECT project_id, sid FROM project_sessions').fetchall()
    finally:
        wb.close()

    counts = {name: set() for name in projects.values()}
    for row in links:
        name = projects.get(row['project_id'])
        if name and row['sid']:
            counts[name].add(row['sid'])

    if os.path.exists(STATE_DB):
        conn = sqlite3.connect(STATE_DB)
        conn.row_factory = sqlite3.Row
        try:
            base = os.path.join(VAULT, PROJECT_ROOT) + '/'
            rows = conn.execute('SELECT id, cwd FROM sessions WHERE cwd LIKE ?', ('%' + os.path.join(VAULT, PROJECT_ROOT) + '%',)).fetchall()
            for row in rows:
                cwd = row['cwd'] or ''
                if cwd.startswith(base):
                    name = cwd[len(base):].split('/', 1)[0]
                    counts.setdefault(name, set()).add(row['id'])
        finally:
            conn.close()

    return {'ok': True, 'counts': {name: len(values) for name, values in counts.items()}}

def list_codex_thread_titles(ids):
    values = [str(value).strip() for value in ids if str(value).strip()]
    if not values:
        return {'ok': True, 'titles': []}
    codex_db = os.path.expanduser('~/.codex/state_5.sqlite')
    conn = sqlite3.connect(codex_db)
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ','.join('?' for _ in values)
        rows = conn.execute(
            f"SELECT id, COALESCE(NULLIF(name, ''), title) AS title FROM threads WHERE id IN ({placeholders})",
            values,
        ).fetchall()
        return {'ok': True, 'titles': [dict(row) for row in rows]}
    finally:
        conn.close()
