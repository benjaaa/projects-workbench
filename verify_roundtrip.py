#!/usr/bin/env python3
"""Round-trip 全量验证：DB → 渲染 vs 磁盘现存文件。
任务含 log_yaml 重建；项目含 project_sessions。逐字节比对（splitlines 兼容尾换行）。
"""
import os
import sqlite3
import sys
import difflib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from doc_renderer import render_task_doc, render_project_doc

DB = '/Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/workbench.db'
VAULT = '/Users/ben/Documents/Second Brain/Second Brain'


def task_log_yaml(conn, tid):
    out = ''
    for e in conn.execute("SELECT * FROM log_entries WHERE task_id=? ORDER BY date", (tid,)):
        out += f"- date: {e['date']}\n  id: {e['id']}\n  type: {e['type']}\n"
        if e['summary']:
            out += f"  summary: {e['summary']}\n"
        if e['window']:
            out += f'  window: "{e["window"]}"\n'
        sids = list(conn.execute("SELECT sid, source FROM log_sessions WHERE entry_id=?", (e['id'],)))
        for s in sids:
            if s['sid'] == sids[0]['sid']:
                out += '  sessions:\n'
            out += f"    - id: {s['sid']}\n      source: {s['source']}\n"
        for kind in ('outputs', 'risks', 'pending'):
            rows = conn.execute("SELECT text FROM log_detail WHERE entry_id=? AND kind=? ORDER BY seq", (e['id'], kind)).fetchall()
            if rows:
                out += f'  {kind}:\n'
                for r in rows:
                    out += f'    - {r["text"]}\n'
        decs = conn.execute("SELECT text, by FROM log_detail WHERE entry_id=? AND kind='decisions' ORDER BY seq", (e['id'],)).fetchall()
        if decs:
            out += '  decisions:\n'
            for d in decs:
                out += f'    - desc: {d["text"]}\n'
                if d['by']:
                    out += f'      by: {d["by"]}\n'
    return out


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    ok = drift = 0
    results = []
    for t in conn.execute('SELECT * FROM tasks'):
        rel = '2. Project/2.1 Project/%s/tasks/任务-%s.md' % (t['project_id'], t['id'])
        path = os.path.join(VAULT, rel)
        if not os.path.exists(path):
            results.append(('MISSING', t['id'], rel))
            continue
        sids = [r['sid'] for r in conn.execute('SELECT sid FROM task_sessions WHERE task_id=? ORDER BY linked_at', (t['id'],))]
        rendered = render_task_doc(dict(t), sids, task_log_yaml(conn, t['id']))
        actual = open(path, encoding='utf-8').read()
        d = list(difflib.unified_diff(actual.splitlines(), rendered.splitlines(), lineterm=''))
        if not d:
            ok += 1
        else:
            drift += 1
            results.append(('DRIFT', t['id'], f'{len(d)} diff lines'))
    pok = pdrift = 0
    for p in conn.execute('SELECT * FROM projects'):
        cands = [f for f in os.listdir(os.path.join(VAULT, '2. Project/2.1 Project', p['id']))
                 if f.startswith('项目说明-') and f.endswith('.md')] if os.path.isdir(os.path.join(VAULT, '2. Project/2.1 Project', p['id'])) else []
        if not cands:
            continue
        path = os.path.join(VAULT, '2. Project/2.1 Project', p['id'], cands[0])
        sids = [r['sid'] for r in conn.execute('SELECT sid FROM project_sessions WHERE project_id=?', (p['id'],))]
        rendered = render_project_doc(dict(p), sids)
        actual = open(path, encoding='utf-8').read()
        d = list(difflib.unified_diff(actual.splitlines(), rendered.splitlines(), lineterm=''))
        if not d:
            pok += 1
        else:
            pdrift += 1
            results.append(('P-DRIFT', p['id'], f'{len(d)} diff lines'))
    conn.close()
    print(f'tasks: OK={ok} DRIFT={drift} | projects: OK={pok} DRIFT={pdrift}')
    for r in results[:15]:
        print(' ', r)
    sys.exit(0 if (drift + pdrift == 0 and not results) else 1)


if __name__ == '__main__':
    main()
