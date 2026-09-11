import os
import re
import sqlite3
import time

TASK_PATH_RE = re.compile(r'^2\. Project/2\.1 Project/([^/]+)/tasks/任务-(.+)\.md$')


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
