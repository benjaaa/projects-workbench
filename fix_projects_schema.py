#!/usr/bin/env python3
"""fix_projects_schema.py — 修复 projects 表 schema 与数据

内容：
1. projects 表加回 start/due/complete 三列（UUID 迁移时漏搬）
2. 从 fkfix 备份经 migration_map 回填日期数据
3. 删除 session_ids 死列（重建表）
"""
import sqlite3, sys, time, shutil

DB = '/Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/workbench.db'
BACKUP = '/Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/workbench.db.backup-fkfix-20260907-102927'


def main():
    # 备份当前库
    bak = DB + '.backup-projfix-' + time.strftime('%Y%m%d-%H%M%S')
    shutil.copy2(DB, bak)
    print(f'backup: {bak}')

    conn = sqlite3.connect(DB)
    conn.execute('PRAGMA foreign_keys = OFF')
    try:
        # ── 1. 重建 projects：加回 start/due/complete，去掉 session_ids 死列 ──
        print('重建 projects 表...')
        conn.execute('''CREATE TABLE projects_fixed (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            status TEXT DEFAULT 'open',
            start INTEGER,
            due INTEGER,
            complete INTEGER,
            background TEXT DEFAULT '',
            goal TEXT DEFAULT '',
            created_at INTEGER,
            updated_at INTEGER,
            version INTEGER DEFAULT 1,
            tags_json TEXT DEFAULT '[]'
        )''')
        conn.execute('''INSERT INTO projects_fixed
            (id, name, status, background, goal, created_at, updated_at, version, tags_json)
            SELECT id, name, status, background, goal, created_at, updated_at, version, tags_json
            FROM projects''')
        conn.execute('DROP TABLE projects')
        conn.execute('ALTER TABLE projects_fixed RENAME TO projects')
        n = conn.execute('SELECT COUNT(*) FROM projects').fetchone()[0]
        print(f'  projects 重建完成: {n} 行（+start/due/complete，-session_ids，+name UNIQUE）')

        # ── 2. 从备份回填日期 ──
        print('回填日期数据...')
        bak_conn = sqlite3.connect(BACKUP)
        bak_conn.row_factory = sqlite3.Row
        # migration_map: old_id(name) → new_id(uuid)
        mapping = {r['old_id']: r['new_id'] for r in bak_conn.execute(
            "SELECT old_id, new_id FROM migration_map WHERE entity_type='project'").fetchall()}
        rows = bak_conn.execute('SELECT name, start, due, complete FROM projects_old').fetchall()
        bak_conn.close()

        filled = 0
        for r in rows:
            new_id = mapping.get(r['name'])
            if not new_id:
                continue
            conn.execute('UPDATE projects SET start=?, due=?, complete=? WHERE id=?',
                         (r['start'], r['due'], r['complete'], new_id))
            if r['start'] or r['due'] or r['complete']:
                filled += 1
        print(f'  日期回填: {filled}/{len(rows)} 个项目有日期数据')

        # ── 3. tasks 表去 session_ids 死列 ──
        print('重建 tasks 表（去 session_ids）...')
        conn.execute('''CREATE TABLE tasks_fixed (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id),
            title TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            priority TEXT DEFAULT 'p2',
            start INTEGER, due INTEGER, complete INTEGER,
            handler TEXT DEFAULT '',
            goal TEXT DEFAULT '', body TEXT DEFAULT '', acceptance TEXT DEFAULT '',
            repeat_mode TEXT DEFAULT '', repeat_unit TEXT DEFAULT '',
            repeat_every INTEGER, repeat_day INTEGER, repeat_anchor TEXT DEFAULT '',
            created_at INTEGER, updated_at INTEGER,
            version INTEGER DEFAULT 1,
            tags_json TEXT DEFAULT '[]',
            kanban_task_id TEXT DEFAULT '',
            UNIQUE(project_id, title)
        )''')
        conn.execute('''INSERT INTO tasks_fixed
            (id, project_id, title, status, priority, start, due, complete, handler,
             goal, body, acceptance, repeat_mode, repeat_unit, repeat_every, repeat_day,
             repeat_anchor, created_at, updated_at, version, tags_json, kanban_task_id)
            SELECT id, project_id, title, status, priority, start, due, complete, handler,
                   goal, body, acceptance, repeat_mode, repeat_unit, repeat_every, repeat_day,
                   repeat_anchor, created_at, updated_at, version, tags_json, kanban_task_id
            FROM tasks''')
        conn.execute('DROP TABLE tasks')
        conn.execute('ALTER TABLE tasks_fixed RENAME TO tasks')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)')
        tn = conn.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
        print(f'  tasks 重建完成: {tn} 行（-session_ids）')

        conn.commit()

        # ── 验证 ──
        conn.execute('PRAGMA foreign_keys = ON')
        viol = conn.execute('PRAGMA foreign_key_check').fetchall()
        print(f'foreign_key_check: {len(viol)} violations')
        cols = [r[1] for r in conn.execute('PRAGMA table_info(projects)').fetchall()]
        assert 'start' in cols and 'due' in cols and 'complete' in cols, '日期列缺失'
        assert 'session_ids' not in cols, 'session_ids 未删'
        print('projects 列:', cols)
        # 抽查回填
        row = conn.execute("SELECT name, start, complete FROM projects WHERE complete IS NOT NULL").fetchall()
        for r in row:
            import datetime
            s = datetime.datetime.fromtimestamp(r[1]).strftime('%Y-%m-%d') if r[1] else ''
            c = datetime.datetime.fromtimestamp(r[2]).strftime('%Y-%m-%d') if r[2] else ''
            print(f'  {r[0]}: start={s} complete={c}')
        print('schema 修复完成')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
