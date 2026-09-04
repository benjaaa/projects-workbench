#!/usr/bin/env python3
"""P2 投影管道：DB 写入 → change_log → 自动投影（按实体局部触发）。

project_write(conn, entity_type, entity_id, changed_by) 是唯一投影入口：
  1. 从 DB 读该实体最新状态（含推进记录重建 log_yaml）
  2. doc_renderer 渲染全文
  3. osascript cp 写回 vault（TCC 绕行配方：临时文件 + cp）
  4. documents.content_version+1

变更历史 helper：
  log_change(conn, entity_type, entity_id, field, old, new, changed_by)
  大文本（>200字）截断存储。
"""
import os
import sqlite3
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from doc_renderer import render_task_doc, render_project_doc

DB = '/Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/workbench.db'
VAULT = '/Users/ben/Documents/Second Brain/Second Brain'
PROOT = '2. Project/2.1 Project'
TRUNC = 200


def log_change(conn, entity_type, entity_id, field, old, new, changed_by=''):
    """字段级变更历史；大文本截断。"""
    def tr(v):
        if v is None:
            return None
        v = str(v)
        if len(v) > TRUNC:
            return v[:TRUNC] + f'…[len={len(v)}]'
        return v
    conn.execute(
        'INSERT INTO change_log(entity_type,entity_id,field,old_value,new_value,changed_at,changed_by) VALUES(?,?,?,?,?,?,?)',
        (entity_type, entity_id, field, tr(old), tr(new), int(time.time()), changed_by))


def _task_log_yaml(conn, tid):
    out = ''
    for e in conn.execute("SELECT * FROM log_entries WHERE task_id=? ORDER BY date", (tid,)):
        out += f"- date: {e['date']}\n  id: {e['id']}\n  type: {e['type']}\n"
        if e['summary']:
            if '\n' in e['summary']:
                out += '  summary: |\n' + '\n'.join('    ' + l for l in e['summary'].split('\n')) + '\n'
            else:
                out += f"  summary: {e['summary']}\n"
        if e['window']:
            out += f'  window: "{e["window"]}"\n'
        for s in conn.execute("SELECT sid, source FROM log_sessions WHERE entry_id=?", (e['id'],)):
            out += f"  sessions:\n    - id: {s['sid']}\n      source: {s['source']}\n"
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


def _osascript_cp(tmp_path, target):
    p = subprocess.run(['osascript', '-e',
                        f'do shell script "cp {tmp_path} \\"{target}\\" && rm {tmp_path}"'],
                       capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f'osascript cp failed: {p.stderr.decode()[:200]}')


def project_write(conn, entity_type, entity_id, changed_by=''):
    """唯一投影入口：按实体渲染并写回。conn 由调用方提供（未提交状态可见）。"""
    if entity_type == 'task':
        t = dict(conn.execute('SELECT * FROM tasks WHERE id=?', (entity_id,)).fetchone())
        if not t:
            raise ValueError(f'task not found: {entity_id}')
        sids = [r['sid'] for r in conn.execute(
            'SELECT sid FROM task_sessions WHERE task_id=? ORDER BY linked_at', (entity_id,))]
        rendered = render_task_doc(t, sids, _task_log_yaml(conn, entity_id))
        rel = f'{PROOT}/{t["project_id"]}/tasks/任务-{entity_id}.md'
    elif entity_type == 'project':
        p = dict(conn.execute('SELECT * FROM projects WHERE id=?', (entity_id,)).fetchone())
        if not p:
            raise ValueError(f'project not found: {entity_id}')
        sids = [r['sid'] for r in conn.execute(
            'SELECT sid FROM project_sessions WHERE project_id=?', (entity_id,))]
        rendered = render_project_doc(p, sids)
        cands = [f for f in os.listdir(os.path.join(VAULT, PROOT, entity_id))
                 if f.startswith('项目说明-') and f.endswith('.md')]
        rel = f'{PROOT}/{entity_id}/{cands[0]}' if cands else f'{PROOT}/{entity_id}/项目说明-{entity_id}.md'
    else:
        raise ValueError(f'unknown entity_type: {entity_type}')

    target = os.path.join(VAULT, rel)
    tmp = tempfile.mktemp(suffix='.md')
    with open(tmp, 'w', encoding='utf-8') as f:
        assert isinstance(rendered, str), 'full-mode render must return str'
        f.write(rendered)
    _osascript_cp(tmp, target)
    conn.execute(
        'UPDATE documents SET content_version=content_version+1, generated_at=? '
        "WHERE entity_type=? AND entity_id=? AND entity_id!=''",
        (int(time.time()), entity_type, entity_id))
    return {'path': rel, 'bytes': len(rendered.encode('utf-8'))}


def create_task(conn, project_id, title, sid=None, changed_by='', **fields):
    """创建时序原则落地：DB 先有行 → 建文件 → documents 映射。"""
    now = int(time.time())
    file_id = title  # tasks.id 锚文件名（去 任务- 前缀）
    conn.execute(
        '''INSERT OR IGNORE INTO tasks(id,project_id,title,status,priority,start,due,handler,
           version,tags_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,1,'["task"]',?,?)''',
        (file_id, project_id, fields.get('fm_title') or title, fields.get('status', 'open'),
         fields.get('priority', 'p2'), fields.get('start', ''), fields.get('due', ''),
         fields.get('handler', ''), now, now))
    log_change(conn, 'task', file_id, '__create__', None, title, changed_by)
    if sid:
        conn.execute('INSERT OR IGNORE INTO task_sessions(task_id,sid,linked_at,source) VALUES(?,?,?,?)',
                     (file_id, sid, now, changed_by or 'create'))
    if sid:  # frontmatter session_ids 同步
        pass  # project_write 渲染时从 task_sessions 读取，无需冗余写
    doc_path = os.path.join(VAULT, PROOT, project_id, 'tasks', f'任务-{file_id}.md')
    if not os.path.exists(doc_path):
        conn.execute(
            "INSERT OR IGNORE INTO documents(entity_type,entity_id,path,filename,content_version,generated_at) "
            "VALUES('task',?,?,?,0,?)",
            (file_id, f'{PROOT}/{project_id}/tasks/任务-{file_id}.md', f'任务-{file_id}.md', now))
    result = project_write(conn, 'task', file_id, changed_by)
    return {'task_id': file_id, **result}


if __name__ == '__main__':
    # 自检：对已投影过的试点任务再跑一次，应为零变化（幂等）
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    r = project_write(conn, 'task', '低ADR老客效果二轮试验', 'selftest')
    conn.commit()
    print('self-test project_write:', r)
    print('change_log rows:', conn.execute('SELECT count(*) FROM change_log').fetchone()[0])
    conn.close()
