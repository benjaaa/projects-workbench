#!/usr/bin/env python3
"""P2 第一批：schema 升级 + 存量 body/字段全量入 DB。

- workbench.db 已存在（v1 schema），用 ALTER TABLE 增量加列（幂等：查列存在才加）
- 解析任务 md：goal/body/acceptance 按 section 切；项目 md：background/goal
- 解析 frontmatter 补齐：tags/kanban_task_id/repeat_*/project version
- tasks.id 已在 fix_task_anchor.py 中锚定文件名，此处校验不回退
"""
import json
import os
import re
import sqlite3
import time

DB = '/Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/workbench.db'
VAULT = '/Users/ben/Documents/Second Brain/Second Brain'
PROOT = os.path.join(VAULT, '2. Project', '2.1 Project')

TASK_COLUMNS = [
    ('tags_json', "TEXT DEFAULT '[]'"), ('kanban_task_id', "TEXT DEFAULT ''"),
    ('goal', 'TEXT DEFAULT ""'), ('body', 'TEXT DEFAULT ""'), ('acceptance', 'TEXT DEFAULT ""'),
    ('repeat_mode', "TEXT DEFAULT ''"), ('repeat_unit', "TEXT DEFAULT ''"),
    ('repeat_every', 'INTEGER'), ('repeat_anchor', 'TEXT'),
]
PROJ_COLUMNS = [
    ('version', 'INTEGER NOT NULL DEFAULT 1'), ('tags_json', "TEXT DEFAULT '[]'"),
    ('background', 'TEXT DEFAULT ""'), ('goal', 'TEXT DEFAULT ""'),
]


def add_missing_columns(conn, table, cols):
    have = {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
    for name, decl in cols:
        if name not in have:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {decl}')


def parse_fm(text):
    m = re.match(r'^---\n([\s\S]*?)\n---\n?([\s\S]*)$', text)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).split('\n'):
        mm = re.match(r'^(\S+)\s*:\s*(.*)$', line)
        if mm:
            fm[mm.group(1)] = mm.group(2).strip().strip('"').strip("'")
    return fm, m.group(2)


def split_sections(body, keep_heading=False):
    """按 ## 标题切段。keep_heading=False 时存内容不含标题行（渲染器统一加回）。"""
    sections = {}
    cur = None
    buf = []
    for line in body.split('\n'):
        m = re.match(r'^## (.+)$', line)
        if m:
            if cur is not None:
                sections[cur] = '\n'.join(buf).strip()
            cur = m.group(1).strip()
            buf = [] if not keep_heading else [line]
        else:
            if cur is not None:
                buf.append(line)
    if cur is not None:
        sections[cur] = '\n'.join(buf).strip()
    return sections


def parse_tags_block(fm_text):
    """yaml tags 区块解析：支持行内 [a, b] 与多行 - item 两种形态。"""
    m = re.search(r'^tags:\s*(\[[^\]]*\])\s*$', fm_text, re.M)
    if m:
        return [t.strip().strip('"').strip("'") for t in m.group(1).strip('[]').split(',') if t.strip()]
    m = re.search(r'^tags:\s*\n((?:[ \t]+-[^\n]*\n?)+)', fm_text, re.M)
    if m:
        return [l.strip()[2:].strip().strip('"').strip("'")
                for l in m.group(1).strip().split('\n') if l.strip().startswith('-')]
    m = re.search(r'^tags:\s*([^\[\n][^\n]*)$', fm_text, re.M)
    if m and m.group(1).strip() and not re.match(r'^\w+:', m.group(1).strip()):
        return [m.group(1).strip().strip('"').strip("'")]
    return []


def parse_repeat_block(full_fm_text):
    """tags/repeat 字段可能多行（yaml list/缩进），用区块正则抓。"""
    def grab(key):
        m = re.search(rf'^{key}:\s*(.*)$', full_fm_text, re.M)
        return m.group(1).strip() if m else ''
    return {k: grab(k) for k in ('tags', 'kanban_task_id', 'repeat_mode', 'repeat_unit',
                                 'repeat_every', 'repeat_day', 'repeat_anchor', 'version')}


def parse_int(raw):
    if raw is None:
        return None
    s = str(raw).strip().strip('"').strip("'")
    return int(s) if s.isdigit() else None


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    add_missing_columns(conn, 'tasks', TASK_COLUMNS)
    add_missing_columns(conn, 'projects', PROJ_COLUMNS)
    conn.commit()
    now = int(time.time())
    stats = {'tasks': 0, 'projects': 0, 'nonstd_sections': []}

    for pname in sorted(os.listdir(PROOT)):
        pdir = os.path.join(PROOT, pname)
        if not os.path.isdir(pdir) or pname.startswith('.'):
            continue
        # 项目 md
        cands = [f for f in os.listdir(pdir) if f.startswith('项目说明-') and f.endswith('.md')]
        if cands:
            text = open(os.path.join(pdir, cands[0]), encoding='utf-8').read()
            fm, body = parse_fm(text)
            extra = parse_repeat_block(text[:text.find('\n---\n', 4) + 5] if '\n---\n' in text else text)
            secs = split_sections(body)
            bg = secs.get('项目背景', '')
            goal = secs.get('目标', '') or secs.get('项目目标', '')
            for k, v in secs.items():
                if k not in ('项目背景', '目标', '项目目标'):
                    # 非标准 section 内容并入 background 尾部，信息不丢
                    bg = (bg + '\n\n' + v).strip()
                    stats['nonstd_sections'].append((pname, k))
            conn.execute(
                'UPDATE projects SET version=?, tags_json=?, background=?, goal=?, updated_at=? WHERE id=?',
                (parse_int(extra.get('version')) or 1, json.dumps(parse_tags_block(text[:text.find('\n---\n', 4) + 5] if '\n---\n' in text else text), ensure_ascii=False),
                 bg, goal, now, pname))
            stats['projects'] += 1
        # 任务 md
        tdir = os.path.join(pdir, 'tasks')
        if not os.path.isdir(tdir):
            continue
        for fn in sorted(os.listdir(tdir)):
            if not (fn.startswith('任务-') and fn.endswith('.md')):
                continue
            full = os.path.join(tdir, fn)
            text = open(full, encoding='utf-8').read()
            fm, body = parse_fm(text)
            fmend = text.find('\n---\n', 4)
            extra = parse_repeat_block(text[:fmend + 5] if fmend > 0 else text)
            secs = split_sections(body)
            file_id = fn[3:-3]
            goal = secs.get('目标', '')
            detail = secs.get('任务详情', '')
            acc = secs.get('验收标准', '')
            for k, v in secs.items():
                if k not in ('目标', '任务详情', '验收标准', '推进记录'):
                    detail = (detail + '\n\n' + v).strip()
                    stats['nonstd_sections'].append((fn, k))
            # 推进记录 section 不入 body（真相在 log_entries）
            conn.execute(
                '''UPDATE tasks SET tags_json=?, kanban_task_id=?, goal=?, body=?, acceptance=?,
                   repeat_mode=?, repeat_unit=?, repeat_every=?, repeat_day=?, repeat_anchor=?,
                   version=?, updated_at=? WHERE id=?''',
                (json.dumps(parse_tags_block(text[:fmend + 5] if fmend > 0 else text), ensure_ascii=False), extra.get('kanban_task_id') or '',
                 goal, detail, acc,
                 extra.get('repeat_mode') or '', extra.get('repeat_unit') or '',
                 parse_int(extra.get('repeat_every')),
                 parse_int(extra.get('repeat_day')),
                 extra.get('repeat_anchor') or '',
                 parse_int(extra.get('version')) or 1, now, file_id))
            stats['tasks'] += 1

    conn.commit()
    # 校验
    chk1 = conn.execute("SELECT count(*) FROM tasks WHERE body='' AND goal='' AND acceptance=''").fetchone()[0]
    chk2 = conn.execute("SELECT count(*) FROM projects WHERE background='' AND goal=''").fetchone()[0]
    chk3 = conn.execute("SELECT count(*) FROM tasks WHERE id LIKE '任务-%'").fetchone()[0]
    conn.close()
    print('migrated:', {k: v for k, v in stats.items() if k != 'nonstd_sections'})
    print(f'tasks with all body empty: {chk1} (expect 0)')
    print(f'projects with all body empty: {chk2} (expect ~0, 新项目可能真空)')
    print(f'tasks with wrong anchor: {chk3} (expect 0)')
    if stats['nonstd_sections']:
        print('non-standard sections merged into body:')
        for s in stats['nonstd_sections'][:10]:
            print('  ', s)


if __name__ == '__main__':
    main()
