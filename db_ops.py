#!/usr/bin/env python3
"""db_ops.py — P3 执行主体反转：DB 先行的写 op 层。

架构语义（Ben 2026-09-05 拍板，多次强调）：
  workbench.db 是唯一真相源，md 文件只是投影（只出不进）。
  写 op = 写 DB（字段+change_log+version）→ project_write 投影渲染文件。
  文件不再作为写入的必经之路，也不再从文件反向解析。

覆盖 op：set_property / add_log / edit_log / toggle_ac / update_section / set_body
其余（create_project/ensure_dir/write 等文件系统结构类）维持原路径。
"""
import os
import re
import json
import time

from workbench_db import connect as wb_connect
from write_bridge import VAULT, PROOT_DIR, STATE_DB, sid_exists, validate_sids
from write_pipeline import project_write

TASK_RE = re.compile(r'^2\. Project/2\.1 Project/([^/]+)/tasks/任务-(.+)\.md$')
PROJ_RE = re.compile(r'^2\. Project/2\.1 Project/([^/]+)/项目说明-')

# 字段白名单（防注入 + 语义边界）
TASK_FIELDS = {'status', 'priority', 'start', 'due', 'complete', 'handler',
               'title', 'kanban_task_id', 'repeat_anchor'}
PROJ_FIELDS = {'status', 'start', 'due', 'complete', 'name'}
SECTION_FIELD = {'目标': 'goal', '任务详情': 'body', '验收标准': 'acceptance'}


def _entity(path):
    m = TASK_RE.match(path or '')
    if m:
        return 'task', m.group(2)
    m = PROJ_RE.match(path or '')
    if m:
        return 'project', m.group(1)
    return None


def _today():
    return time.strftime('%Y-%m-%d')


def _log_change(conn, etype, eid, field, old, new, changed_by):
    conn.execute(
        "INSERT INTO change_log(entity_type,entity_id,field,old_value,new_value,changed_at,changed_by) "
        "VALUES(?,?,?,?,?,?,?)",
        (etype, eid, field,
         None if old is None else str(old)[:200],
         None if new is None else str(new)[:200],
         int(time.time()), changed_by))


def _bump_version(conn, etype, eid, changed_by):
    table = 'tasks' if etype == 'task' else 'projects'
    row = conn.execute(f'SELECT version FROM {table} WHERE id=?', (eid,)).fetchone()
    v = (row['version'] or 1) + 1
    conn.execute(f'UPDATE {table} SET version=?, updated_at=? WHERE id=?', (v, int(time.time()), eid))
    _log_change(conn, etype, eid, 'version', (row['version'] or 1), v, changed_by)
    return v


def _project(conn, etype, eid, changed_by):
    from write_pipeline import project_write as _pw
    try:
        return _pw(conn, etype, eid, changed_by)
    except Exception as e:
        return {'error': f'{type(e).__name__}: {e}'}


# ────────────────────────── set_property ──────────────────────────

def set_property(path, field, value, if_version=None, changed_by=''):
    ent = _entity(path)
    if not ent:
        return {'ok': False, 'error': 'bad path: ' + (path or '')[:120]}
    etype, eid = ent
    fields = TASK_FIELDS if etype == 'task' else PROJ_FIELDS
    if field not in fields:
        return {'ok': False, 'error': f'field {field} not allowed on {etype}'}

    conn = wb_connect()
    try:
        table = 'tasks' if etype == 'task' else 'projects'
        row = conn.execute(f'SELECT * FROM {table} WHERE id=?', (eid,)).fetchone()
        if not row:
            return {'ok': False, 'error': f'{etype} not found: {eid}'}
        if if_version is not None and (row['version'] or 1) != int(if_version):
            return {'ok': False, 'error': 'VERSION_CONFLICT',
                    'current_version': row['version'] or 1}
        old = row[field]
        if old == value:
            conn.commit()
            return {'ok': True, 'unchanged': True, 'db_first': True}
        # Done/Dropped 联动 complete
        conn.execute(f'UPDATE {table} SET {field}=? WHERE id=?', (value, eid))
        _log_change(conn, etype, eid, field, old, value, changed_by)
        if field == 'status' and value in ('Done', 'Dropped') and not row['complete']:
            conn.execute(f'UPDATE {table} SET complete=? WHERE id=?', (_today(), eid))
            _log_change(conn, etype, eid, 'complete', row['complete'], _today(), changed_by)
        v = _bump_version(conn, etype, eid, changed_by)
        conn.commit()
        proj = _project(conn, etype, eid, changed_by)
        return {'ok': True, 'version': v, 'projected': proj, 'db_first': True}
    finally:
        conn.close()


# ────────────────────────── update_section / set_body ──────────────────────────

def update_section(path, section, text, if_version=None, changed_by=''):
    ent = _entity(path)
    if not ent:
        return {'ok': False, 'error': 'bad path: ' + (path or '')[:120]}
    etype, eid = ent
    if etype == 'task':
        field = SECTION_FIELD.get(section)
    else:
        field = {'项目背景': 'background', '项目目标': 'goal'}.get(section)
    if not field:
        return {'ok': False, 'error': f'unknown section: {section}'}

    conn = wb_connect()
    try:
        table = 'tasks' if etype == 'task' else 'projects'
        row = conn.execute(f'SELECT * FROM {table} WHERE id=?', (eid,)).fetchone()
        if not row:
            return {'ok': False, 'error': f'{etype} not found: {eid}'}
        if if_version is not None and (row['version'] or 1) != int(if_version):
            return {'ok': False, 'error': 'VERSION_CONFLICT',
                    'current_version': row['version'] or 1}
        old = row[field]
        conn.execute(f'UPDATE {table} SET {field}=? WHERE id=?', (text, eid))
        _log_change(conn, etype, eid, field, old, text, changed_by)
        v = _bump_version(conn, etype, eid, changed_by)
        conn.commit()
        proj = _project(conn, etype, eid, changed_by)
        return {'ok': True, 'version': v, 'projected': proj, 'db_first': True}
    finally:
        conn.close()


def set_body(path, text, if_version=None, changed_by=''):
    return update_section(path, '任务详情', text, if_version, changed_by)


# ────────────────────────── toggle_ac ──────────────────────────

def toggle_ac(path, idx, changed_by=''):
    """验收标准第 idx 项勾选态轮转 [ ]→[x]→[-]→[ ]（DB 内文本就地轮转）。"""
    ent = _entity(path)
    if not ent or ent[0] != 'task':
        return {'ok': False, 'error': 'toggle_ac requires task path'}
    eid = ent[1]
    conn = wb_connect()
    try:
        row = conn.execute('SELECT acceptance, version FROM tasks WHERE id=?', (eid,)).fetchone()
        if not row:
            return {'ok': False, 'error': 'task not found: ' + eid}
        lines = (row['acceptance'] or '').split('\n')
        n = 0
        hit = False
        for i, l in enumerate(lines):
            if re.match(r'^[-*]\s*\[.?\]\s*', l):
                if n == idx:
                    if '[x]' in l:
                        lines[i] = l.replace('[x]', '[-]')
                    elif '[-]' in l:
                        lines[i] = l.replace('[-]', '[ ]')
                    else:
                        lines[i] = l.replace('[ ]', '[x]')
                    hit = True
                    break
                n += 1
        if not hit:
            return {'ok': False, 'error': f'acceptance idx out of range: {idx}'}
        new_ac = '\n'.join(lines)
        conn.execute('UPDATE tasks SET acceptance=? WHERE id=?', (new_ac, eid))
        _log_change(conn, 'task', eid, 'acceptance', row['acceptance'], new_ac, changed_by)
        v = _bump_version(conn, 'task', eid, changed_by)
        conn.commit()
        proj = _project(conn, 'task', eid, changed_by)
        return {'ok': True, 'version': v, 'projected': proj, 'db_first': True}
    finally:
        conn.close()


# ────────────────────────── add_log ──────────────────────────

_ENTRY_ID_RE = re.compile(r'^\s+id:\s*(\S+)', re.M)
_LIST_KEYS = ('outputs', 'risks', 'pending')


def _parse_yaml_entry(text):
    """解析 YAML 推进记录条目 → dict（容错：块量/行内 summary、list、decisions.by）。"""
    e = {'date': '', 'id': '', 'type': 'manual', 'summary': '', 'window': '',
         'sessions': [], 'outputs': [], 'decisions': [], 'risks': [], 'pending': []}
    dm = re.match(r'- date:\s*(.+)', text)
    if dm:
        e['date'] = dm.group(1).strip()
    im = _ENTRY_ID_RE.search(text)
    if im:
        e['id'] = im.group(1)
    tm = re.search(r'^\s+type:\s*(\S+)', text, re.M)
    if tm:
        e['type'] = tm.group(1)
    bm = re.search(r'^\s+summary:\s*\|\s*\n((?:    .*\n?)+)', text, re.M)
    if bm:
        e['summary'] = '\n'.join(l[4:] if l.startswith('    ') else l.lstrip()
                                 for l in bm.group(1).rstrip('\n').split('\n'))
    else:
        sm = re.search(r'^\s+summary:\s*(.+)$', text, re.M)
        if sm:
            e['summary'] = sm.group(1).strip()
    wm = re.search(r'^\s+window:\s*"?([^"\n]*)"?', text, re.M)
    if wm:
        e['window'] = wm.group(1).strip()
    for sm2 in re.finditer(r'^\s+- id:\s*(\S+)\s*$', text, re.M):
        line_pos = sm2.start()
        after = text[line_pos:]
        srcm = re.match(r'\s+- id:\s*\S+\s*\n\s+source:\s*(\S+)', after)
        e['sessions'].append({'sid': sm2.group(1),
                              'source': srcm.group(1) if srcm else 'unknown'})
    for kind in _LIST_KEYS:
        km = re.search(rf'^\s+{kind}:\s*\n((?:    - .*\n?)+)', text, re.M)
        if km:
            e[kind] = [l.strip()[2:].strip() for l in km.group(1).rstrip('\n').split('\n')]
    dm2 = re.search(r'^\s+decisions:\s*\n((?:    - .*\n?)+)', text, re.M)
    if dm2:
        cur = None
        for l in dm2.group(1).rstrip('\n').split('\n'):
            dlm = re.match(r'\s+- desc:\s*(.*)$', l)
            blm = re.match(r'\s+by:\s*(.*)$', l)
            if dlm:
                cur = {'text': dlm.group(1).strip(), 'by': ''}
                e['decisions'].append(cur)
            elif blm and cur is not None:
                cur['by'] = blm.group(1).strip()
    return e


def add_log(path, text, changed_by=''):
    ent = _entity(path)
    if not ent or ent[0] != 'task':
        return {'ok': False, 'error': 'add_log requires task path'}
    eid = ent[1]
    now = int(time.time())

    if text.startswith('- date:'):
        entry = _parse_yaml_entry(text)
        sids = [s['sid'] for s in entry['sessions']]
        dead = validate_sids(sids)
        if dead:
            return {'ok': False, 'error': 'INVALID_SESSION_IDS',
                    'detail': '以下 sid 不存在于 state.db，请先 task_ops link 或修正: ' + str(dead),
                    'invalid_sids': dead}
        if not entry['id']:
            entry['id'] = entry['date'].replace('-', '') + '_' + time.strftime('%H%M%S')
    else:
        entry = {'date': _today(), 'id': time.strftime('%Y%m%d_%H%M%S'),
                 'type': 'manual', 'summary': text.strip(), 'window': '',
                 'sessions': [], 'outputs': [], 'decisions': [], 'risks': [], 'pending': []}

    conn = wb_connect()
    try:
        if not conn.execute('SELECT 1 FROM tasks WHERE id=?', (eid,)).fetchone():
            return {'ok': False, 'error': 'task not found: ' + eid}
        if conn.execute('SELECT 1 FROM log_entries WHERE id=?', (entry['id'],)).fetchone():
            return {'ok': False, 'error': 'ENTRY_EXISTS: ' + entry['id']}
        conn.execute(
            'INSERT INTO log_entries(id,task_id,date,type,summary,window,created_at) VALUES(?,?,?,?,?,?,?)',
            (entry['id'], eid, entry['date'], entry['type'], entry['summary'],
             entry['window'], now))
        for s in entry['sessions']:
            conn.execute('INSERT INTO log_sessions(entry_id,sid,source) VALUES(?,?,?)',
                         (entry['id'], s['sid'], s['source']))
        for kind in _LIST_KEYS:
            for seq, txt in enumerate(entry[kind]):
                conn.execute('INSERT INTO log_detail(entry_id,kind,seq,text) VALUES(?,?,?,?)',
                             (entry['id'], kind, seq, txt))
        for seq, d in enumerate(entry['decisions']):
            conn.execute('INSERT INTO log_detail(entry_id,kind,seq,text,by) VALUES(?,?,?,?,?)',
                         (entry['id'], 'decisions', seq, d['text'], d['by']))
        _log_change(conn, 'task', eid, '__log__', None, entry['summary'], changed_by)
        conn.commit()
        proj = _project(conn, 'task', eid, changed_by)
        return {'ok': True, 'entry_id': entry['id'], 'projected': proj, 'db_first': True}
    finally:
        conn.close()


def edit_log(path, idx, text, changed_by=''):
    """编辑第 idx 条推进记录（按 date 排序，与投影/读取顺序一致）。"""
    ent = _entity(path)
    if not ent or ent[0] != 'task':
        return {'ok': False, 'error': 'edit_log requires task path'}
    eid = ent[1]
    conn = wb_connect()
    try:
        rows = conn.execute(
            'SELECT id, summary FROM log_entries WHERE task_id=? ORDER BY date, created_at', (eid,)).fetchall()
        idx = int(idx)
        if idx < 0 or idx >= len(rows):
            return {'ok': False, 'error': f'log idx out of range: {idx}/{len(rows)}'}
        target = rows[idx]
        conn.execute('UPDATE log_entries SET summary=?, updated_at=? WHERE id=?',
                     (text, int(time.time()), target['id']))
        _log_change(conn, 'task', eid, '__log_edit__', target['summary'], text, changed_by)
        conn.commit()
        proj = _project(conn, 'task', eid, changed_by)
        return {'ok': True, 'entry_id': target['id'], 'projected': proj, 'db_first': True}
    finally:
        conn.close()


# ────────────────────────── 分发入口 ──────────────────────────

def run_db_first(op, spec, if_version=None):
    changed_by = spec.get('changed_by') or ('op:' + op)
    if op == 'set_property':
        return set_property(spec['path'], spec['field'], spec.get('value', ''),
                            if_version=if_version, changed_by=changed_by)
    if op == 'update_section':
        return update_section(spec['path'], spec['section'], spec.get('text', ''),
                              if_version=if_version, changed_by=changed_by)
    if op == 'set_body':
        return set_body(spec['path'], spec.get('text', ''),
                        if_version=if_version, changed_by=changed_by)
    if op == 'toggle_ac':
        return toggle_ac(spec['path'], int(spec.get('idx', -1)), changed_by=changed_by)
    if op == 'add_log':
        return add_log(spec['path'], spec.get('text', ''), changed_by=changed_by)
    if op == 'edit_log':
        return edit_log(spec['path'], spec.get('idx', -1), spec.get('text', ''),
                        changed_by=changed_by)
    return {'ok': False, 'error': 'unknown db-first op: ' + op}
