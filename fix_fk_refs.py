#!/usr/bin/env python3
"""fix_fk_refs.py — 修复 UUID 迁移残留的外键引用（*_new → 正式表名）

背景：UUID 迁移时表被重建为 xxx_new 再改名，但外键引用仍指向旧临时表名。
SQLite 不支持 ALTER 修改外键，需按「建新表→拷数据→删旧表→改名」流程重建。
"""
import sqlite3, sys, time, shutil

DB = '/Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/workbench.db'

FIXES = {
    'tasks': '''CREATE TABLE tasks_fixed (
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
        session_ids TEXT DEFAULT '',
        UNIQUE(project_id, title)
    )''',
    'task_sessions': '''CREATE TABLE task_sessions_fixed (
        task_id TEXT NOT NULL REFERENCES tasks(id),
        sid TEXT NOT NULL,
        linked_at INTEGER NOT NULL,
        source TEXT DEFAULT '',
        PRIMARY KEY (task_id, sid)
    )''',
    'project_sessions': '''CREATE TABLE project_sessions_fixed (
        project_id TEXT NOT NULL REFERENCES projects(id),
        sid TEXT NOT NULL,
        linked_at INTEGER NOT NULL,
        source TEXT DEFAULT '',
        PRIMARY KEY (project_id, sid)
    )''',
    'log_entries': '''CREATE TABLE log_entries_fixed (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL REFERENCES tasks(id),
        date TEXT NOT NULL,
        type TEXT NOT NULL,
        summary TEXT DEFAULT '',
        window TEXT DEFAULT '',
        created_at INTEGER, updated_at INTEGER
    )''',
    'log_detail': '''CREATE TABLE log_detail_fixed (
        entry_id TEXT NOT NULL REFERENCES log_entries(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        seq INTEGER NOT NULL,
        text TEXT DEFAULT '',
        by TEXT DEFAULT '',
        PRIMARY KEY (entry_id, kind, seq)
    )''',
    'log_sessions': '''CREATE TABLE log_sessions_fixed (
        entry_id TEXT NOT NULL REFERENCES log_entries(id) ON DELETE CASCADE,
        sid TEXT NOT NULL,
        source TEXT DEFAULT '',
        PRIMARY KEY (entry_id, sid)
    )''',
}

# 重建顺序：先被引用方（tasks/log_entries），后引用方
ORDER = ['tasks', 'task_sessions', 'project_sessions', 'log_entries', 'log_detail', 'log_sessions']


def main():
    backup = DB + '.backup-fkfix-' + time.strftime('%Y%m%d-%H%M%S')
    shutil.copy2(DB, backup)
    print(f'backup: {backup}')

    conn = sqlite3.connect(DB)
    # 重建期间关闭外键（改名过程中引用会短暂悬空）
    conn.execute('PRAGMA foreign_keys = OFF')
    try:
        for tbl in ORDER:
            sql = conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (tbl,)).fetchone()[0]
            if '_new' not in sql:
                print(f'skip {tbl} (no _new ref)')
                continue
            print(f'fixing {tbl}...')
            conn.execute(FIXES[tbl])
            # 拷贝数据（列名一致，直接 INSERT SELECT）
            cols = [r[1] for r in conn.execute(f'PRAGMA table_info({tbl})').fetchall()]
            col_list = ','.join(cols)
            conn.execute(f'INSERT INTO {tbl}_fixed ({col_list}) SELECT {col_list} FROM {tbl}')
            n = conn.execute(f'SELECT COUNT(*) FROM {tbl}_fixed').fetchone()[0]
            conn.execute(f'DROP TABLE {tbl}')
            conn.execute(f'ALTER TABLE {tbl}_fixed RENAME TO {tbl}')
            print(f'  {tbl}: {n} rows migrated')
        conn.commit()

        # 验证：开启外键后应无违规
        conn.execute('PRAGMA foreign_keys = ON')
        violations = conn.execute('PRAGMA foreign_key_check').fetchall()
        if violations:
            print(f'FK violations after fix: {len(violations)}')
            for v in violations[:5]:
                print(f'  {v}')
            sys.exit(1)
        # 确认无 _new 残留
        bad = conn.execute("SELECT name FROM sqlite_master WHERE sql LIKE '%_new(%'").fetchall()
        bad = [b[0] for b in bad if '_new(' in str(b)]
        refs_bad = conn.execute("SELECT name, sql FROM sqlite_master WHERE sql LIKE '%REFERENCES %_new%'").fetchall()
        if refs_bad:
            print(f'REMAINING bad refs: {[r[0] for r in refs_bad]}')
            sys.exit(1)
        print('FK fix complete, no violations, no _new refs remain')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
