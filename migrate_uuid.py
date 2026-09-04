"""UUID 主键迁移脚本：projects/tasks 改用 UUID，保留 title/name 映射。

迁移策略：
1. 创建新表（projects_new, tasks_new, task_sessions_new, log_entries_new, documents_new）
2. 旧 id → 新 UUID 映射写入 migration_map 表
3. 所有外键关联更新为新 UUID
4. 验证后切换表名
"""
import os
import sqlite3
import uuid
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WB_DB = os.path.join(SCRIPT_DIR, 'workbench.db')
LOG_DB = os.path.join(SCRIPT_DIR, 'workbench-log.db')


def gen_uuid():
    return uuid.uuid4().hex[:12]


def migrate():
    conn = sqlite3.connect(WB_DB)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=OFF')
    
    # ─── 1. 创建映射表 ─────────────────────────────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS migration_map (
            old_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            new_id TEXT NOT NULL,
            old_title TEXT,
            created_at INTEGER NOT NULL,
            PRIMARY KEY (old_id, entity_type)
        )
    ''')
    
    # ─── 2. 迁移 projects ─────────────────────────────────────
    print('迁移 projects...')
    projects = conn.execute('SELECT * FROM projects').fetchall()
    proj_map = {}  # old_id → new_id
    
    for p in projects:
        old_id = p['id']
        new_id = gen_uuid()
        proj_map[old_id] = new_id
        conn.execute(
            'INSERT INTO migration_map(old_id, entity_type, new_id, old_title, created_at) VALUES(?,?,?,?,?)',
            (old_id, 'project', new_id, p['name'], int(time.time()))
        )
    
    # 创建新 projects 表
    conn.execute('''
        CREATE TABLE projects_new (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            background TEXT DEFAULT '',
            goal TEXT DEFAULT '',
            created_at INTEGER,
            updated_at INTEGER,
            version INTEGER DEFAULT 1,
            tags_json TEXT DEFAULT '[]',
            session_ids TEXT DEFAULT ''
        )
    ''')
    
    for p in projects:
        old_id = p['id']
        new_id = proj_map[old_id]
        conn.execute(
            '''INSERT INTO projects_new(id, name, status, background, goal, created_at, updated_at, version, tags_json, session_ids)
               VALUES(?,?,?,?,?,?,?,?,?,?)''',
            (new_id, p['name'], p['status'], p['background'], p['goal'],
             p['created_at'], p['updated_at'], p['version'], p['tags_json'], '')
        )
    
    print(f'  projects: {len(projects)} 条')
    
    # ─── 3. 迁移 tasks ─────────────────────────────────────────
    print('迁移 tasks...')
    tasks = conn.execute('SELECT * FROM tasks').fetchall()
    task_map = {}  # old_id → new_id
    
    for t in tasks:
        old_id = t['id']
        new_id = gen_uuid()
        task_map[old_id] = new_id
        conn.execute(
            'INSERT INTO migration_map(old_id, entity_type, new_id, old_title, created_at) VALUES(?,?,?,?,?)',
            (old_id, 'task', new_id, t['title'], int(time.time()))
        )
    
    conn.execute('''
        CREATE TABLE tasks_new (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects_new(id),
            title TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            priority TEXT DEFAULT 'p2',
            start INTEGER,
            due INTEGER,
            complete INTEGER,
            handler TEXT DEFAULT '',
            goal TEXT DEFAULT '',
            body TEXT DEFAULT '',
            acceptance TEXT DEFAULT '',
            repeat_mode TEXT DEFAULT '',
            repeat_unit TEXT DEFAULT '',
            repeat_every INTEGER,
            repeat_day INTEGER,
            repeat_anchor TEXT DEFAULT '',
            created_at INTEGER,
            updated_at INTEGER,
            version INTEGER DEFAULT 1,
            tags_json TEXT DEFAULT '[]',
            kanban_task_id TEXT DEFAULT '',
            session_ids TEXT DEFAULT '',
            UNIQUE(project_id, title)
        )
    ''')
    
    skipped_tasks = []
    for t in tasks:
        old_id = t['id']
        old_project_id = t['project_id']
        new_id = task_map[old_id]
        new_project_id = proj_map.get(old_project_id)
        
        if not new_project_id:
            skipped_tasks.append((old_id, old_project_id))
            continue
        
        conn.execute(
            '''INSERT INTO tasks_new(id, project_id, title, status, priority, start, due, complete,
                   handler, goal, body, acceptance, repeat_mode, repeat_unit, repeat_every,
                   repeat_day, repeat_anchor, created_at, updated_at, version, tags_json,
                   kanban_task_id, session_ids)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (new_id, new_project_id, t['title'], t['status'], t['priority'],
             t['start'], t['due'], t['complete'], t['handler'], t['goal'], t['body'],
             t['acceptance'], t['repeat_mode'], t['repeat_unit'], t['repeat_every'],
             t['repeat_day'], t['repeat_anchor'], t['created_at'], t['updated_at'],
             t['version'], t['tags_json'], t['kanban_task_id'], '')
        )
    
    print(f'  tasks: {len(tasks)} 条, 跳过 {len(skipped_tasks)} 条孤儿任务')
    for tid, pid in skipped_tasks:
        print(f'    跳过: {tid} (project_id={pid} 不存在)')
    
    # ─── 4. 迁移 task_sessions ─────────────────────────────────
    print('迁移 task_sessions...')
    conn.execute('''
        CREATE TABLE task_sessions_new (
            task_id TEXT NOT NULL REFERENCES tasks_new(id),
            sid TEXT NOT NULL,
            linked_at INTEGER NOT NULL,
            source TEXT DEFAULT '',
            PRIMARY KEY (task_id, sid)
        )
    ''')
    
    ts_rows = conn.execute('SELECT * FROM task_sessions').fetchall()
    skipped_ts = 0
    for r in ts_rows:
        old_tid = r['task_id']
        new_tid = task_map.get(old_tid)
        if not new_tid:
            skipped_ts += 1
            continue
        conn.execute(
            'INSERT INTO task_sessions_new(task_id, sid, linked_at, source) VALUES(?,?,?,?)',
            (new_tid, r['sid'], r['linked_at'], r['source'])
        )
    print(f'  task_sessions: {len(ts_rows)} 条, 跳过 {skipped_ts} 条')
    
    # ─── 5. 迁移 project_sessions ──────────────────────────────
    print('迁移 project_sessions...')
    conn.execute('''
        CREATE TABLE project_sessions_new (
            project_id TEXT NOT NULL REFERENCES projects_new(id),
            sid TEXT NOT NULL,
            linked_at INTEGER NOT NULL,
            source TEXT DEFAULT '',
            PRIMARY KEY (project_id, sid)
        )
    ''')
    
    ps_rows = conn.execute('SELECT * FROM project_sessions').fetchall()
    skipped_ps = 0
    for r in ps_rows:
        old_pid = r['project_id']
        new_pid = proj_map.get(old_pid)
        if not new_pid:
            skipped_ps += 1
            continue
        conn.execute(
            'INSERT INTO project_sessions_new(project_id, sid, linked_at, source) VALUES(?,?,?,?)',
            (new_pid, r['sid'], r['linked_at'], r['source'])
        )
    print(f'  project_sessions: {len(ps_rows)} 条, 跳过 {skipped_ps} 条')
    
    # ─── 6. 迁移 log_entries ───────────────────────────────────
    print('迁移 log_entries...')
    conn.execute('''
        CREATE TABLE log_entries_new (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES tasks_new(id),
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            summary TEXT DEFAULT '',
            window TEXT DEFAULT '',
            created_at INTEGER,
            updated_at INTEGER
        )
    ''')
    
    log_rows = conn.execute('SELECT * FROM log_entries').fetchall()
    skipped_logs = 0
    for r in log_rows:
        old_tid = r['task_id']
        new_tid = task_map.get(old_tid)
        if not new_tid:
            skipped_logs += 1
            continue
        conn.execute(
            'INSERT INTO log_entries_new(id, task_id, date, type, summary, window, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)',
            (r['id'], new_tid, r['date'], r['type'], r['summary'], r['window'],
             r['created_at'], r['updated_at'])
        )
    print(f'  log_entries: {len(log_rows)} 条, 跳过 {skipped_logs} 条')
    
    # ─── 7. 迁移 documents ─────────────────────────────────────
    print('迁移 documents...')
    conn.execute('''
        CREATE TABLE documents_new (
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            path TEXT NOT NULL,
            content TEXT DEFAULT '',
            updated_at INTEGER,
            PRIMARY KEY (entity_type, entity_id, doc_type)
        )
    ''')
    
    doc_rows = conn.execute('SELECT * FROM documents').fetchall()
    skipped_docs = 0
    for r in doc_rows:
        etype = r['entity_type']
        old_id = r['entity_id']
        if etype == 'project':
            new_id = proj_map.get(old_id)
        elif etype == 'task':
            new_id = task_map.get(old_id)
        else:
            new_id = old_id
        
        if not new_id:
            skipped_docs += 1
            continue
        
        # 旧表有 path/filename/content_version/generated_at，新表用 doc_type 存 path
        conn.execute(
            'INSERT INTO documents_new(entity_type, entity_id, doc_type, path, content, updated_at) VALUES(?,?,?,?,?,?)',
            (etype, new_id, r['path'], r['path'], '', r['generated_at'])
        )
    print(f'  documents: {len(doc_rows)} 条, 跳过 {skipped_docs} 条')
    
    # ─── 8. 迁移 log_detail / log_sessions ─────────────────────
    print('迁移 log_detail...')
    conn.execute('''
        CREATE TABLE log_detail_new (
            entry_id TEXT NOT NULL REFERENCES log_entries_new(id),
            kind TEXT NOT NULL,
            seq INTEGER NOT NULL,
            text TEXT DEFAULT '',
            by TEXT DEFAULT '',
            PRIMARY KEY (entry_id, kind, seq)
        )
    ''')
    ld_rows = conn.execute('SELECT * FROM log_detail').fetchall()
    for r in ld_rows:
        conn.execute(
            'INSERT INTO log_detail_new(entry_id, kind, seq, text, by) VALUES(?,?,?,?,?)',
            (r['entry_id'], r['kind'], r['seq'], r['text'], r['by'])
        )
    print(f'  log_detail: {len(ld_rows)} 条')
    
    print('迁移 log_sessions...')
    conn.execute('''
        CREATE TABLE log_sessions_new (
            entry_id TEXT NOT NULL REFERENCES log_entries_new(id),
            sid TEXT NOT NULL,
            source TEXT DEFAULT '',
            PRIMARY KEY (entry_id, sid)
        )
    ''')
    ls_rows = conn.execute('SELECT * FROM log_sessions').fetchall()
    for r in ls_rows:
        conn.execute(
            'INSERT INTO log_sessions_new(entry_id, sid, source) VALUES(?,?,?)',
            (r['entry_id'], r['sid'], r['source'])
        )
    print(f'  log_sessions: {len(ls_rows)} 条')
    
    # ─── 9. 验证 ──────────────────────────────────────────────
    print()
    print('验证...')
    
    p_old = conn.execute('SELECT COUNT(*) FROM projects').fetchone()[0]
    p_new = conn.execute('SELECT COUNT(*) FROM projects_new').fetchone()[0]
    print(f'  projects: {p_old} → {p_new}')
    
    t_old = conn.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
    t_new = conn.execute('SELECT COUNT(*) FROM tasks_new').fetchone()[0]
    print(f'  tasks: {t_old} → {t_new}')
    
    ts_old = conn.execute('SELECT COUNT(*) FROM task_sessions').fetchone()[0]
    ts_new = conn.execute('SELECT COUNT(*) FROM task_sessions_new').fetchone()[0]
    print(f'  task_sessions: {ts_old} → {ts_new}')
    
    ps_old = conn.execute('SELECT COUNT(*) FROM project_sessions').fetchone()[0]
    ps_new = conn.execute('SELECT COUNT(*) FROM project_sessions_new').fetchone()[0]
    print(f'  project_sessions: {ps_old} → {ps_new}')
    
    le_old = conn.execute('SELECT COUNT(*) FROM log_entries').fetchone()[0]
    le_new = conn.execute('SELECT COUNT(*) FROM log_entries_new').fetchone()[0]
    print(f'  log_entries: {le_old} → {le_new}')
    
    # 验证外键完整性
    orphan_tasks = conn.execute('''
        SELECT COUNT(*) FROM tasks_new t LEFT JOIN projects_new p ON t.project_id = p.id WHERE p.id IS NULL
    ''').fetchone()[0]
    print(f'  孤儿任务: {orphan_tasks} 条')
    
    orphan_ts = conn.execute('''
        SELECT COUNT(*) FROM task_sessions_new ts LEFT JOIN tasks_new t ON ts.task_id = t.id WHERE t.id IS NULL
    ''').fetchone()[0]
    print(f'  孤儿 task_sessions: {orphan_ts} 条')
    
    orphan_le = conn.execute('''
        SELECT COUNT(*) FROM log_entries_new le LEFT JOIN tasks_new t ON le.task_id = t.id WHERE t.id IS NULL
    ''').fetchone()[0]
    print(f'  孤儿 log_entries: {orphan_le} 条')
    
    # ─── 12. 切换表名 ──────────────────────────────────────────
    print()
    print('切换表名...')
    
    conn.execute('ALTER TABLE projects RENAME TO projects_old')
    conn.execute('ALTER TABLE tasks RENAME TO tasks_old')
    conn.execute('ALTER TABLE task_sessions RENAME TO task_sessions_old')
    conn.execute('ALTER TABLE project_sessions RENAME TO project_sessions_old')
    conn.execute('ALTER TABLE log_entries RENAME TO log_entries_old')
    conn.execute('ALTER TABLE documents RENAME TO documents_old')
    conn.execute('ALTER TABLE log_detail RENAME TO log_detail_old')
    conn.execute('ALTER TABLE log_sessions RENAME TO log_sessions_old')
    
    conn.execute('ALTER TABLE projects_new RENAME TO projects')
    conn.execute('ALTER TABLE tasks_new RENAME TO tasks')
    conn.execute('ALTER TABLE task_sessions_new RENAME TO task_sessions')
    conn.execute('ALTER TABLE project_sessions_new RENAME TO project_sessions')
    conn.execute('ALTER TABLE log_entries_new RENAME TO log_entries')
    conn.execute('ALTER TABLE documents_new RENAME TO documents')
    conn.execute('ALTER TABLE log_detail_new RENAME TO log_detail')
    conn.execute('ALTER TABLE log_sessions_new RENAME TO log_sessions')
    
    # 创建索引
    conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_log_entries_task ON log_entries(task_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_task_sessions_task ON task_sessions(task_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_project_sessions_project ON project_sessions(project_id)')
    
    conn.commit()
    conn.execute('PRAGMA foreign_keys=ON')
    conn.close()
    
    print()
    print('=' * 50)
    print('迁移完成')
    print('=' * 50)
    print(f'projects: {p_new} 条')
    print(f'tasks: {t_new} 条')
    print(f'task_sessions: {ts_new} 条')
    print(f'project_sessions: {ps_new} 条')
    print(f'log_entries: {le_new} 条')
    print(f'跳过孤儿任务: {len(skipped_tasks)} 条')
    print()
    print('旧表已保留为 *_old，验证后可手动删除')


if __name__ == '__main__':
    migrate()
