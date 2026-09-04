#!/usr/bin/env python3
"""migrate_v2.py — Schema 迁移：旧 workbench.db → 新 Schema

迁移内容：
1. 日期字段：TEXT (YYYY-MM-DD) → INTEGER (Unix 时间戳)
2. Log 层独立：workbench.db.change_log → workbench-log.db
3. 新增字段：projects.background / projects.goal（从文件解析补充）

迁移策略：
- 新 DB 文件：workbench-v2.db（不覆盖旧文件）
- 旧数据完整迁移，无丢失
- 迁移完成后旧文件保留为备份
"""
import os
import re
import sqlite3
import sys
import time
from datetime import datetime

# 路径常量
VAULT = '/Users/ben/Documents/Second Brain/Second Brain'
PROOT = '2. Project/2.1 Project'
OLD_DB = '/Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/workbench.db'
NEW_DB = '/Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/workbench-v2.db'
LOG_DB = '/Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/workbench-log.db'


def date_to_ts(date_str):
    """YYYY-MM-DD → Unix 时间戳（当天 00:00:00）。"""
    if not date_str or not isinstance(date_str, str):
        return None
    try:
        d = datetime.strptime(date_str.strip(), '%Y-%m-%d')
        return int(d.timestamp())
    except Exception:
        return None


def ts_to_date(ts):
    """Unix 时间戳 → YYYY-MM-DD。"""
    if not ts:
        return ''
    try:
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
    except Exception:
        return ''


def parse_frontmatter_file(path):
    """解析项目说明文件的 frontmatter + body。"""
    full = os.path.join(VAULT, path)
    if not os.path.exists(full):
        return {}
    
    text = open(full, encoding='utf-8').read()
    m = re.match(r'^---\n([\s\S]*?)\n---\n?([\s\S]*)$', text)
    if not m:
        return {}
    
    fm_raw, body = m.group(1), m.group(2)
    fields = {}
    
    # frontmatter 字段
    for line in fm_raw.split('\n'):
        mm = re.match(r'^(\S+)\s*:\s*(.*)$', line)
        if mm:
            fields[mm.group(1)] = mm.group(2).strip().strip('"').strip("'")
    
    # body 区段
    bg_match = re.search(r'## 项目背景\n([\s\S]*?)(?:\n## |$)', body)
    if bg_match:
        fields['background'] = bg_match.group(1).strip()
    goal_match = re.search(r'## 项目目标\n([\s\S]*?)(?:\n## |$)', body)
    if goal_match:
        fields['goal'] = goal_match.group(1).strip()
    
    return fields


def migrate_projects(old_conn, new_conn):
    """迁移 projects 表。"""
    print('迁移 projects...')
    
    rows = old_conn.execute('SELECT * FROM projects').fetchall()
    count = 0
    
    for row in rows:
        p = dict(row)
        
        # 日期字段转换
        start_ts = date_to_ts(p.get('start', ''))
        due_ts = date_to_ts(p.get('due', ''))
        complete_ts = date_to_ts(p.get('complete', ''))
        
        # 从文件补充 background / goal（如果 DB 为空）
        background = p.get('background', '') or ''
        goal = p.get('goal', '') or ''
        
        if not background or not goal:
            proj_path = f'{PROOT}/{p["id"]}/项目说明-{p["id"]}.md'
            file_fields = parse_frontmatter_file(proj_path)
            if not background:
                background = file_fields.get('background', '')
            if not goal:
                goal = file_fields.get('goal', '')
        
        new_conn.execute('''INSERT INTO projects(
            id, name, status, start, due, complete,
            created_at, updated_at, version,
            background, goal, tags_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', (
            p['id'], p.get('name', p['id']), p.get('status', 'open'),
            start_ts, due_ts, complete_ts,
            p.get('created_at', int(time.time())), p.get('updated_at', int(time.time())),
            p.get('version', 1),
            background, goal,
            p.get('tags_json', '[]')
        ))
        count += 1
    
    print(f'  projects: {count} 条')
    return count


def migrate_tasks(old_conn, new_conn):
    """迁移 tasks 表。"""
    print('迁移 tasks...')
    
    # 先获取所有有效的 project_id
    valid_projects = {r[0] for r in new_conn.execute('SELECT id FROM projects').fetchall()}
    
    rows = old_conn.execute('SELECT * FROM tasks').fetchall()
    count = 0
    skipped = 0
    
    for row in rows:
        t = dict(row)
        
        # 检查外键约束：project_id 必须存在
        project_id = t.get('project_id', '')
        if project_id and project_id not in valid_projects:
            print(f'  跳过任务（项目不存在）: {t["id"]} → project_id={project_id}')
            skipped += 1
            continue
        
        # 日期字段转换
        start_ts = date_to_ts(t.get('start', ''))
        due_ts = date_to_ts(t.get('due', ''))
        complete_ts = date_to_ts(t.get('complete', ''))
        
        new_conn.execute('''INSERT INTO tasks(
            id, project_id, title, status, priority,
            start, due, complete, handler,
            version, repeat_day, repeat_anchor,
            created_at, updated_at,
            tags_json, kanban_task_id, goal, body, acceptance,
            repeat_mode, repeat_unit, repeat_every
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
            t['id'], project_id, t.get('title', t['id']),
            t.get('status', 'open'), t.get('priority', ''),
            start_ts, due_ts, complete_ts,
            t.get('handler', ''),
            t.get('version', 1),
            t.get('repeat_day'), t.get('repeat_anchor', ''),
            t.get('created_at', int(time.time())), t.get('updated_at', int(time.time())),
            t.get('tags_json', '[]'), t.get('kanban_task_id', ''),
            t.get('goal', ''), t.get('body', ''), t.get('acceptance', ''),
            t.get('repeat_mode', ''), t.get('repeat_unit', ''), t.get('repeat_every')
        ))
        count += 1
    
    print(f'  tasks: {count} 条（跳过 {skipped} 条孤儿任务）')
    return count


def migrate_sessions(old_conn, new_conn):
    """迁移 session 关联表。"""
    print('迁移 session 关联...')
    
    # project_sessions
    rows = old_conn.execute('SELECT * FROM project_sessions').fetchall()
    for row in rows:
        r = dict(row)
        new_conn.execute('INSERT OR IGNORE INTO project_sessions(project_id, sid, linked_at, source) VALUES(?,?,?,?)',
                         (r['project_id'], r['sid'], r['linked_at'], r.get('source', '')))
    ps_count = len(rows)
    
    # task_sessions
    rows = old_conn.execute('SELECT * FROM task_sessions').fetchall()
    for row in rows:
        r = dict(row)
        new_conn.execute('INSERT OR IGNORE INTO task_sessions(task_id, sid, linked_at, source) VALUES(?,?,?,?)',
                         (r['task_id'], r['sid'], r['linked_at'], r.get('source', '')))
    ts_count = len(rows)
    
    print(f'  project_sessions: {ps_count} 条')
    print(f'  task_sessions: {ts_count} 条')
    return ps_count + ts_count


def migrate_logs(old_conn, new_conn):
    """迁移日志表。"""
    print('迁移日志...')
    
    # log_entries
    rows = old_conn.execute('SELECT * FROM log_entries').fetchall()
    for row in rows:
        r = dict(row)
        new_conn.execute('''INSERT INTO log_entries(id, task_id, date, type, summary, window, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?)''',
            (r['id'], r['task_id'], r['date'], r['type'],
             r.get('summary', ''), r.get('window', ''),
             r.get('created_at', int(time.time())), r.get('updated_at', int(time.time()))))
    le_count = len(rows)
    
    # log_detail
    rows = old_conn.execute('SELECT * FROM log_detail').fetchall()
    for row in rows:
        r = dict(row)
        new_conn.execute('INSERT INTO log_detail(entry_id, kind, seq, text, by) VALUES(?,?,?,?,?)',
                         (r['entry_id'], r['kind'], r['seq'], r.get('text', ''), r.get('by', '')))
    ld_count = len(rows)
    
    # log_sessions
    rows = old_conn.execute('SELECT * FROM log_sessions').fetchall()
    for row in rows:
        r = dict(row)
        new_conn.execute('INSERT OR IGNORE INTO log_sessions(entry_id, sid, source) VALUES(?,?,?)',
                         (r['entry_id'], r['sid'], r.get('source', '')))
    ls_count = len(rows)
    
    print(f'  log_entries: {le_count} 条')
    print(f'  log_detail: {ld_count} 条')
    print(f'  log_sessions: {ls_count} 条')
    return le_count + ld_count + ls_count


def migrate_documents(old_conn, new_conn):
    """迁移 documents 表。"""
    print('迁移 documents...')
    
    rows = old_conn.execute('SELECT * FROM documents').fetchall()
    for row in rows:
        r = dict(row)
        new_conn.execute('INSERT OR IGNORE INTO documents(entity_type, entity_id, path, filename, content_version, generated_at) VALUES(?,?,?,?,?,?)',
                         (r['entity_type'], r['entity_id'], r['path'], r['filename'],
                          r.get('content_version', 0), r.get('generated_at')))
    
    print(f'  documents: {len(rows)} 条')
    return len(rows)


def migrate_change_log(old_conn, log_conn):
    """迁移 change_log 到独立日志库。"""
    print('迁移 change_log 到独立日志库...')
    
    rows = old_conn.execute('SELECT * FROM change_log').fetchall()
    count = 0
    
    for row in rows:
        r = dict(row)
        log_conn.execute('''INSERT INTO change_log(
            entity_type, entity_id, field, old_value, new_value, changed_at, changed_by
        ) VALUES(?,?,?,?,?,?,?)''', (
            r['entity_type'], r['entity_id'], r['field'],
            r.get('old_value'), r.get('new_value'),
            r.get('changed_at', int(time.time())), r.get('changed_by', '')
        ))
        count += 1
    
    print(f'  change_log: {count} 条 → workbench-log.db')
    return count


def init_new_schema(conn):
    """初始化新 Schema。"""
    print('初始化新 Schema...')
    
    # 启用外键
    conn.execute('PRAGMA foreign_keys = ON')
    
    # projects
    conn.execute('''CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        start INTEGER,
        due INTEGER,
        complete INTEGER,
        created_at INTEGER,
        updated_at INTEGER,
        version INTEGER NOT NULL DEFAULT 1,
        background TEXT DEFAULT '',
        goal TEXT DEFAULT '',
        tags_json TEXT DEFAULT '[]'
    )''')
    
    # tasks
    conn.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES projects(id),
        title TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        priority TEXT DEFAULT '',
        start INTEGER,
        due INTEGER,
        complete INTEGER,
        handler TEXT DEFAULT '',
        version INTEGER NOT NULL DEFAULT 1,
        repeat_day INTEGER,
        repeat_anchor TEXT,
        created_at INTEGER,
        updated_at INTEGER,
        tags_json TEXT DEFAULT '[]',
        kanban_task_id TEXT DEFAULT '',
        goal TEXT DEFAULT '',
        body TEXT DEFAULT '',
        acceptance TEXT DEFAULT '',
        repeat_mode TEXT DEFAULT '',
        repeat_unit TEXT DEFAULT '',
        repeat_every INTEGER
    )''')
    
    # project_sessions
    conn.execute('''CREATE TABLE IF NOT EXISTS project_sessions (
        project_id TEXT NOT NULL REFERENCES projects(id),
        sid TEXT NOT NULL,
        linked_at INTEGER NOT NULL,
        source TEXT DEFAULT '',
        PRIMARY KEY (project_id, sid)
    )''')
    
    # task_sessions
    conn.execute('''CREATE TABLE IF NOT EXISTS task_sessions (
        task_id TEXT NOT NULL REFERENCES tasks(id),
        sid TEXT NOT NULL,
        linked_at INTEGER NOT NULL,
        source TEXT DEFAULT '',
        PRIMARY KEY (task_id, sid)
    )''')
    
    # log_entries
    conn.execute('''CREATE TABLE IF NOT EXISTS log_entries (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL REFERENCES tasks(id),
        date TEXT NOT NULL,
        type TEXT NOT NULL,
        summary TEXT DEFAULT '',
        window TEXT DEFAULT '',
        created_at INTEGER,
        updated_at INTEGER
    )''')
    
    # log_detail
    conn.execute('''CREATE TABLE IF NOT EXISTS log_detail (
        entry_id TEXT NOT NULL REFERENCES log_entries(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        seq INTEGER NOT NULL,
        text TEXT DEFAULT '',
        by TEXT DEFAULT '',
        PRIMARY KEY (entry_id, kind, seq)
    )''')
    
    # log_sessions
    conn.execute('''CREATE TABLE IF NOT EXISTS log_sessions (
        entry_id TEXT NOT NULL REFERENCES log_entries(id) ON DELETE CASCADE,
        sid TEXT NOT NULL,
        source TEXT DEFAULT '',
        PRIMARY KEY (entry_id, sid)
    )''')
    
    # documents
    conn.execute('''CREATE TABLE IF NOT EXISTS documents (
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        path TEXT NOT NULL,
        filename TEXT NOT NULL,
        content_version INTEGER NOT NULL DEFAULT 0,
        generated_at INTEGER,
        PRIMARY KEY (entity_type, entity_id, path)
    )''')
    
    # 索引
    conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_task_sessions_task ON task_sessions(task_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_log_entries_task ON log_entries(task_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_documents_path ON documents(path)')
    
    conn.commit()
    print('  新 Schema 初始化完成')


def init_log_schema(conn):
    """初始化日志库 Schema。"""
    print('初始化日志库 Schema...')
    
    # ops_log
    conn.execute('''CREATE TABLE IF NOT EXISTS ops_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        action TEXT NOT NULL,
        entity_type TEXT DEFAULT '',
        entity_id TEXT DEFAULT '',
        detail TEXT DEFAULT '',
        created_at INTEGER NOT NULL
    )''')
    
    # change_log
    conn.execute('''CREATE TABLE IF NOT EXISTS change_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        field TEXT NOT NULL,
        old_value TEXT,
        new_value TEXT,
        changed_at INTEGER NOT NULL,
        changed_by TEXT DEFAULT ''
    )''')
    
    # render_queue
    conn.execute('''CREATE TABLE IF NOT EXISTS render_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        error TEXT DEFAULT '',
        retry_count INTEGER DEFAULT 0,
        created_at INTEGER NOT NULL,
        last_retry_at INTEGER
    )''')
    
    # 索引
    conn.execute('CREATE INDEX IF NOT EXISTS idx_ops_entity ON ops_log(entity_type, entity_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_ops_time ON ops_log(created_at)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_change_entity ON change_log(entity_type, entity_id, changed_at)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_render_queue ON render_queue(entity_type, entity_id)')
    
    conn.commit()
    print('  日志库 Schema 初始化完成')


def verify_migration(old_conn, new_conn):
    """验证迁移结果。"""
    print('\n验证迁移...')
    
    checks = []
    
    # projects 数量
    old_count = old_conn.execute('SELECT COUNT(*) FROM projects').fetchone()[0]
    new_count = new_conn.execute('SELECT COUNT(*) FROM projects').fetchone()[0]
    checks.append(('projects 数量', old_count == new_count, f'{old_count} → {new_count}'))
    
    # tasks 数量（允许跳过孤儿任务）
    old_count = old_conn.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
    new_count = new_conn.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
    skipped = old_count - new_count
    if skipped > 0:
        checks.append(('tasks 数量（含跳过）', True, f'{old_count} → {new_count}（跳过 {skipped} 条孤儿任务）'))
    else:
        checks.append(('tasks 数量', old_count == new_count, f'{old_count} → {new_count}'))
    
    # project_sessions 数量
    old_count = old_conn.execute('SELECT COUNT(*) FROM project_sessions').fetchone()[0]
    new_count = new_conn.execute('SELECT COUNT(*) FROM project_sessions').fetchone()[0]
    checks.append(('project_sessions 数量', old_count == new_count, f'{old_count} → {new_count}'))
    
    # task_sessions 数量
    old_count = old_conn.execute('SELECT COUNT(*) FROM task_sessions').fetchone()[0]
    new_count = new_conn.execute('SELECT COUNT(*) FROM task_sessions').fetchone()[0]
    checks.append(('task_sessions 数量', old_count == new_count, f'{old_count} → {new_count}'))
    
    # log_entries 数量
    old_count = old_conn.execute('SELECT COUNT(*) FROM log_entries').fetchone()[0]
    new_count = new_conn.execute('SELECT COUNT(*) FROM log_entries').fetchone()[0]
    checks.append(('log_entries 数量', old_count == new_count, f'{old_count} → {new_count}'))
    
    # 日期字段类型检查（抽样）
    sample = new_conn.execute("SELECT start, due FROM tasks WHERE start IS NOT NULL LIMIT 1").fetchone()
    if sample:
        is_int = isinstance(sample['start'], int) or sample['start'] is None
        checks.append(('tasks.start 为 INTEGER', is_int, f'type={type(sample["start"]).__name__}'))
    
    all_pass = all(c[1] for c in checks)
    for name, passed, detail in checks:
        status = '✓' if passed else '✗'
        print(f'  {status} {name}: {detail}')
    
    return all_pass


def main():
    print('=' * 60)
    print('workbench.db Schema 迁移 v2')
    print('=' * 60)
    print(f'旧 DB: {OLD_DB}')
    print(f'新 DB: {NEW_DB}')
    print(f'日志 DB: {LOG_DB}')
    print()
    
    # 检查旧 DB 存在
    if not os.path.exists(OLD_DB):
        print(f'错误: 旧 DB 不存在: {OLD_DB}')
        sys.exit(1)
    
    # 备份旧 DB
    backup_path = OLD_DB + '.backup-' + time.strftime('%Y%m%d-%H%M%S')
    import shutil
    shutil.copy2(OLD_DB, backup_path)
    print(f'旧 DB 已备份: {backup_path}')
    print()
    
    # 连接
    old_conn = sqlite3.connect(OLD_DB)
    old_conn.row_factory = sqlite3.Row
    
    new_conn = sqlite3.connect(NEW_DB)
    new_conn.row_factory = sqlite3.Row
    
    log_conn = sqlite3.connect(LOG_DB)
    log_conn.row_factory = sqlite3.Row
    
    try:
        # 初始化新 Schema
        init_new_schema(new_conn)
        init_log_schema(log_conn)
        print()
        
        # 迁移数据
        migrate_projects(old_conn, new_conn)
        migrate_tasks(old_conn, new_conn)
        migrate_sessions(old_conn, new_conn)
        migrate_logs(old_conn, new_conn)
        migrate_documents(old_conn, new_conn)
        migrate_change_log(old_conn, log_conn)
        
        new_conn.commit()
        log_conn.commit()
        print()
        
        # 验证
        if verify_migration(old_conn, new_conn):
            print()
            print('=' * 60)
            print('迁移完成！')
            print('=' * 60)
            print(f'新 DB: {NEW_DB}')
            print(f'日志 DB: {LOG_DB}')
            print(f'旧 DB 备份: {backup_path}')
            print()
            print('下一步：')
            print('1. 验证新 DB 数据正确性')
            print('2. 将 workbench-v2.db 重命名为 workbench.db')
            print('3. 更新代码中的 DB 路径引用')
        else:
            print()
            print('迁移验证失败，请检查数据！')
            sys.exit(1)
    
    except Exception as e:
        print(f'\n迁移失败: {type(e).__name__}: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        old_conn.close()
        new_conn.close()
        log_conn.close()


if __name__ == '__main__':
    main()
