#!/usr/bin/env python3
"""P3 读切换：load_tasks/load_projects 的 DB 版本。

接口与原 md 解析版完全一致（返回字段名不变），plugin.js 无需改动调用方式。
数据源：workbench.db（P1 迁移 + P2 写入同步，DB 与 md 已收口一致）。
保留原 md 解析版为 fallback：DB 空表/损坏时自动降级。

新增 DB 版在原字段基础上补充（UI 可渐进采用）：
  raw_body / body_md（正文原文，plugin.js 兼容键名，源自 tasks.body）、goal 与 acceptance原文。
"""
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

WB_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workbench.db')
VAULT = '/Users/ben/Documents/Second Brain/Second Brain'
PROJ_DIR = '2. Project/2.1 Project'


def _wb():
    conn = sqlite3.connect(WB_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _logs_for(conn, task_id):
    """重建 logs/logs_yaml（与原 md 版字段语义一致）。"""
    logs = []
    yaml_parts = []
    for e in conn.execute("SELECT * FROM log_entries WHERE task_id=? ORDER BY date ASC", (task_id,)):
        text = e['summary'] or ''
        if e['window']:
            text = (text + '\n' if text else '') + e['window']
        logs.append({'date': e['date'], 'text': text})
        y = f"- date: {e['date']}\n  id: {e['id']}\n  type: {e['type']}\n"
        if e['summary']:
            if '\n' in e['summary']:
                y += '  summary: |\n' + '\n'.join(('    ' + l if l.strip() else '    ') for l in e['summary'].split('\n')) + '\n'
            else:
                y += f"  summary: {e['summary']}\n"
        if e['window']:
            y += f'  window: "{e["window"]}"\n'
        for s in conn.execute("SELECT sid, source FROM log_sessions WHERE entry_id=?", (e['id'],)):
            y += f"  sessions:\n    - id: {s['sid']}\n      source: {s['source']}\n"
        for kind in ('outputs', 'risks', 'pending'):
            rows = conn.execute("SELECT text FROM log_detail WHERE entry_id=? AND kind=? ORDER BY seq", (e['id'], kind)).fetchall()
            if rows:
                y += f'  {kind}:\n'
                for r in rows:
                    y += f'    - {r["text"]}\n'
        decs = conn.execute("SELECT text, by FROM log_detail WHERE entry_id=? AND kind='decisions' ORDER BY seq", (e['id'],)).fetchall()
        if decs:
            y += '  decisions:\n'
            for d in decs:
                y += f'    - desc: {d["text"]}\n'
                if d['by']:
                    y += f'      by: {d["by"]}\n'
        yaml_parts.append(y)
    return logs, '\n'.join(yaml_parts)


def _acceptance_criteria(acceptance_text):
    ac = []
    for line in (acceptance_text or '').split('\n'):
        m = re.match(r'^[-*]\s*\[([xX\- ]?)\]\s*(.*)', line.strip())
        if m:
            mark = m.group(1).lower()
            ac.append({'text': m.group(2).strip(), 'done': mark == 'x', 'failed': mark == '-'})
    return ac


def load_tasks_db():
    conn = _wb()
    try:
        n = conn.execute('SELECT count(*) FROM tasks').fetchone()[0]
        if n == 0:
            return None  # 触发 fallback
        tasks = []
        for t in conn.execute('SELECT * FROM tasks ORDER BY updated_at DESC'):
            logs, yaml_raw = _logs_for(conn, t['id'])
            rel = f'{PROJ_DIR}/{t["project_id"]}/tasks/任务-{t["id"]}.md'
            sids = [r['sid'] for r in conn.execute(
                'SELECT sid FROM task_sessions WHERE task_id=? ORDER BY linked_at', (t['id'],))]
            tasks.append({
                'path': rel, 'dir': t['project_id'],
                'title': t['title'], 'status': t['status'], 'priority': t['priority'] or 'p2',
                'project': t['project_id'],
                'session_ids': ','.join(sids),
                'kanban_task_id': t['kanban_task_id'] or '',
                'start': t['start'] or '', 'due': t['due'] or '', 'complete': t['complete'] or '',
                'handler': t['handler'] or '',
                'goal': t['goal'] or '', 'task_detail': t['body'] or '',
                'raw_body': t['body'] or '', 'body_md': t['body'] or '',
                'logs': logs, 'logs_yaml': yaml_raw,
                'acceptance_criteria': _acceptance_criteria(t['acceptance']),
                'acceptance_raw': t['acceptance'] or '',
                'version': str(t['version']),
                'repeat_mode': t['repeat_mode'] or '', 'repeat_unit': t['repeat_unit'] or '',
                'repeat_every': t['repeat_every'] or '', 'repeat_day': t['repeat_day'] or '',
                'repeat_anchor': t['repeat_anchor'] or '',
                'tags': json.loads(t['tags_json'] or '[]'),
            })
        return {'tasks': tasks}
    finally:
        conn.close()


def load_projects_db():
    conn = _wb()
    try:
        n = conn.execute('SELECT count(*) FROM projects').fetchone()[0]
        if n == 0:
            return None
        projects = []
        for p in conn.execute('SELECT * FROM projects ORDER BY updated_at DESC'):
            sids = [r['sid'] for r in conn.execute(
                'SELECT sid FROM project_sessions WHERE project_id=?', (p['id'],))]
            rel = f'{PROJ_DIR}/{p["id"]}/项目说明-{p["id"]}.md'
            projects.append({
                'path': rel, 'dir': p['id'], 'title': p['name'],
                'status': p['status'], 'start': p['start'] or '', 'due': p['due'] or '',
                'complete': p['complete'] or '',
                'background': p['background'] or '', 'goal': p['goal'] or '',
                'session_ids': ','.join(sids),
                'version': str(p['version']),
                'tags': json.loads(p['tags_json'] or '[]'),
            })
        return {'projects': projects}
    finally:
        conn.close()


def load_tasks_safe():
    """DB 优先，失败/为空降级 md 解析。"""
    try:
        r = load_tasks_db()
        if r is not None:
            return r
    except Exception as e:
        print(f'[write_bridge] load_tasks_db failed, fallback to md: {e}', file=sys.stderr)
    return None  # 调用方走原 md 版


def load_projects_safe():
    try:
        r = load_projects_db()
        if r is not None:
            return r
    except Exception as e:
        print(f'[write_bridge] load_projects_db failed, fallback to md: {e}', file=sys.stderr)
    return None
