#!/usr/bin/env python3
"""tasks.id 锚定修复：id 从 frontmatter title 改为锚文件名（去 任务- 前缀/.md）。

时序原则（Ben 2026-09-04）：DB 先有记录 → 再创建文件 → 再完成映射。
存量修复按同方向：以文件名为锚（文件名是创建时序的起点），title 保留为显示名。
同步外键：task_sessions.task_id / log_entries.task_id / documents.entity_id(task)。
幂等：已锚定的（fm_title == file_id）跳过。
"""
import os
import re
import sqlite3
import time

DB = '/Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/workbench.db'
VAULT = '/Users/ben/Documents/Second Brain/Second Brain'


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    now = int(time.time())
    renamed = 0

    rows = conn.execute(
        "SELECT entity_id AS fname, path FROM documents WHERE entity_type='file' AND path LIKE '%/tasks/%'"
    ).fetchall()
    for r in rows:
        fn = r['fname'][:-3] if r['fname'].endswith('.md') else r['fname']
        if not fn.startswith('任务-'):
            continue
        file_id = fn[3:]
        full = os.path.join(VAULT, r['path'])
        head = open(full, encoding='utf-8').read(1500)
        m = re.match(r'^---\n([\s\S]*?)\n---', head)
        fm_title = ''
        if m:
            t = re.search(r'^title:\s*(.+)$', m.group(1), re.M)
            fm_title = t.group(1).strip() if t else ''
        if not fm_title or fm_title == file_id:
            continue
        # tasks.id: fm_title -> file_id；title 列保留 fm_title 作显示名
        conn.execute('UPDATE task_sessions SET task_id=? WHERE task_id=?', (file_id, fm_title))
        conn.execute('UPDATE log_entries SET task_id=? WHERE task_id=?', (file_id, fm_title))
        conn.execute("UPDATE documents SET entity_id=? WHERE entity_id=? AND entity_type='task'", (file_id, fm_title))
        conn.execute('UPDATE tasks SET id=?, title=? WHERE id=?', (file_id, fm_title, fm_title))
        renamed += 1

    conn.commit()

    # 验证：孤儿任务文档清零 + 外键完整
    orph = conn.execute(
        "SELECT count(*) FROM documents d WHERE entity_type='file' AND path LIKE '%/tasks/%'"
        " AND NOT EXISTS (SELECT 1 FROM tasks t WHERE d.filename = '任务-' || t.id || '.md')"
    ).fetchone()[0]
    fk = conn.execute('PRAGMA foreign_key_check').fetchall()
    # 引用完整：每个 log/task_session 的 task_id 都存在
    dangling = conn.execute(
        'SELECT count(*) FROM log_entries l LEFT JOIN tasks t ON l.task_id=t.id WHERE t.id IS NULL'
    ).fetchone()[0]
    dangling += conn.execute(
        'SELECT count(*) FROM task_sessions s LEFT JOIN tasks t ON s.task_id=t.id WHERE t.id IS NULL'
    ).fetchone()[0]
    conn.close()
    print(f'renamed={renamed} orphan_task_docs={orph} fk_violations={len(fk)} dangling_refs={dangling}')
    assert orph == 0 and len(fk) == 0 and dangling == 0, 'verification failed'
    print('ALL PASS')


if __name__ == '__main__':
    main()
