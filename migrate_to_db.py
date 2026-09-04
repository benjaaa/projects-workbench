#!/usr/bin/env python3
"""P1 存量迁移：vault 内全部项目/任务 md → workbench.db。

读 vault 直读（不受 TCC 限制），投影写仍由 Obsidian 侧完成（后续生成器）。
脏数据清洗：09-02 review 条目的 sessions 中 aa0e0b（state.db 不存在）丢弃。
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from workbench_db import init_db, connect

VAULT = '/Users/ben/Documents/Second Brain/Second Brain'
PROOT = os.path.join(VAULT, '2. Project', '2.1 Project')


def parse_frontmatter(text):
    m = re.match(r'^---\n([\s\S]*?)\n---\n?([\s\S]*)$', text)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).split('\n'):
        mm = re.match(r'^(\S+)\s*:\s*(.*)$', line)
        if mm:
            v = mm.group(2).strip().strip('"').strip("'")
            fm[mm.group(1)] = v
    return fm, m.group(2)


def parse_yaml_logs(body):
    """解析 ## 推进记录 内的 ```yaml 围栏块 → 条目列表（简易解析，与插件同规则）。"""
    m = re.search(r'## 推进记录\n([\s\S]*?)(\n## |$)', body)
    if not m:
        return []
    ym = re.search(r'```yaml\n([\s\S]*?)```', m.group(1))
    if not ym:
        return []
    entries = []
    for block in re.split(r'\n(?=- date:)', ym.group(1)):
        if not block.strip():
            continue
        e = {'id': '', 'date': '', 'type': '', 'summary': '', 'window': '',
             'sessions': [], 'outputs': [], 'decisions': [], 'risks': [], 'pending': []}
        cur = None
        cur_sub = None
        for line in block.split('\n'):
            mm = re.match(r'^-\s+date:\s*(.+)', line)
            if mm:
                e['date'] = mm.group(1).strip(); cur = None; continue
            mm = re.match(r'^\s+id:\s*(.+)', line)
            if mm:
                e['id'] = mm.group(1).strip(); cur = None; continue
            mm = re.match(r'^\s+type:\s*(.+)', line)
            if mm:
                e['type'] = mm.group(1).strip(); cur = None; continue
            mm = re.match(r'^\s+summary:\s*(.+)', line)
            if mm:
                e['summary'] = mm.group(1).strip(); cur = None; continue
            mm = re.match(r'^\s+window:\s*(.+)', line)
            if mm:
                e['window'] = mm.group(1).strip(); cur = None; continue
            if re.match(r'^\s+sessions:', line):
                cur = 'sessions'; cur_sub = None; continue
            if re.match(r'^\s+(outputs|deliverables):', line):
                cur = 'outputs'; continue
            if re.match(r'^\s+decisions:', line):
                cur = 'decisions'; cur_sub = None; continue
            if re.match(r'^\s+risks:', line):
                cur = 'risks'; continue
            if re.match(r'^\s+pending:', line):
                cur = 'pending'; continue
            if cur == 'sessions':
                mm = re.match(r'^\s+-\s+id:\s*(.+)', line)
                if mm:
                    cur_sub = {'id': mm.group(1).strip(), 'source': ''}
                    e['sessions'].append(cur_sub); continue
                mm = re.match(r'^\s+source:\s*(.+)', line)
                if mm and cur_sub:
                    cur_sub['source'] = mm.group(1).strip(); continue
            elif cur == 'outputs':
                mm = re.match(r'^\s+-\s+(.+)', line)
                if mm:
                    e['outputs'].append(mm.group(1).strip())
            elif cur == 'decisions':
                mm = re.match(r'^\s+-\s+desc:\s*(.+)', line)
                if mm:
                    cur_sub = {'desc': mm.group(1).strip(), 'by': ''}
                    e['decisions'].append(cur_sub); continue
                mm = re.match(r'^\s+by:\s*(.+)', line)
                if mm and cur_sub:
                    cur_sub['by'] = mm.group(1).strip()
            elif cur == 'risks':
                mm = re.match(r'^\s+-\s+(.+)', line)
                if mm:
                    e['risks'].append(mm.group(1).strip())
            elif cur == 'pending':
                mm = re.match(r'^\s+-\s+(.+)', line)
                if mm:
                    e['pending'].append(mm.group(1).strip())
        if e['date']:
            if not e['id']:
                ts = time.strftime('%Y%m%d_%H%M%S')
                e['id'] = ts  # 迁移兜底
            entries.append(e)
    return entries


def main():
    init_db()
    conn = connect()
    now = int(time.time())
    stats = {'projects': 0, 'tasks': 0, 'task_sessions': 0, 'project_sessions': 0,
             'log_entries': 0, 'log_detail': 0, 'log_sessions': 0, 'skipped_sid': []}

    if not os.path.isdir(PROOT):
        print('project root missing:', PROOT)
        return

    for pname in sorted(os.listdir(PROOT)):
        pdir = os.path.join(PROOT, pname)
        if not os.path.isdir(pdir):
            continue
        # 项目文档：项目说明-<name>.md
        pf = os.path.join(pdir, '项目说明-%s.md' % pname)
        if not os.path.exists(pf):
            # 容错：任意 项目说明-*.md
            cands = [f for f in os.listdir(pdir) if f.startswith('项目说明-') and f.endswith('.md')]
            pf = os.path.join(pdir, cands[0]) if cands else None
        if pf:
            text = open(pf, encoding='utf-8').read()
            fm, body = parse_frontmatter(text)
            conn.execute(
                'INSERT OR REPLACE INTO projects(id,name,status,start,due,complete,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                (pname, fm.get('title', pname), fm.get('status', 'open'), fm.get('start', ''),
                 fm.get('due', ''), fm.get('complete', ''), now, now))
            stats['projects'] += 1
            rel = os.path.relpath(pf, VAULT)
            conn.execute(
                'INSERT OR REPLACE INTO documents(entity_type,entity_id,path,filename,content_version,generated_at) VALUES(?,?,?,?,0,?)',
                ('project', pname, rel, os.path.basename(pf), now))
            # 项目 session_ids 投影入库
            for sid in [s.strip() for s in fm.get('session_ids', '').split(',') if s.strip()]:
                conn.execute(
                    'INSERT OR IGNORE INTO project_sessions(project_id,sid,linked_at,source) VALUES(?,?,?,?)',
                    (pname, sid, now, 'migrate'))
                stats['project_sessions'] += 1
        else:
            # 无项目说明文件的目录跳过任务扫描
            continue

        # 任务文档
        tdir = os.path.join(pdir, 'tasks')
        if not os.path.isdir(tdir):
            continue
        for tf in sorted(os.listdir(tdir)):
            if not (tf.startswith('任务-') and tf.endswith('.md')):
                continue
            full = os.path.join(tdir, tf)
            text = open(full, encoding='utf-8').read()
            fm, body = parse_frontmatter(text)
            title = fm.get('title') or tf[3:-3]
            conn.execute(
                'INSERT OR REPLACE INTO tasks(id,project_id,title,status,priority,start,due,complete,handler,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (title, pname, title, fm.get('status', 'open'), fm.get('priority', ''),
                 fm.get('start', ''), fm.get('due', ''), fm.get('complete', ''),
                 fm.get('handler', ''), int(fm.get('version', '1') or 1), now, now))
            stats['tasks'] += 1
            rel = os.path.relpath(full, VAULT)
            conn.execute(
                'INSERT OR REPLACE INTO documents(entity_type,entity_id,path,filename,content_version,generated_at) VALUES(?,?,?,?,0,?)',
                ('task', title, rel, tf, now))
            for sid in [s.strip() for s in fm.get('session_ids', '').split(',') if s.strip()]:
                conn.execute(
                    'INSERT OR IGNORE INTO task_sessions(task_id,sid,linked_at,source) VALUES(?,?,?,?)',
                    (title, sid, now, 'migrate'))
                stats['task_sessions'] += 1
            # 推进记录
            for e in parse_yaml_logs(body):
                conn.execute(
                    'INSERT OR REPLACE INTO log_entries(id,task_id,date,type,summary,window,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                    (e['id'], title, e['date'], e['type'] or 'manual', e['summary'], e['window'], now, now))
                stats['log_entries'] += 1
                for kind in ('outputs', 'decisions', 'risks', 'pending'):
                    for seq, item in enumerate(e[kind]):
                        if isinstance(item, dict):
                            conn.execute(
                                'INSERT OR REPLACE INTO log_detail(entry_id,kind,seq,text,by) VALUES(?,?,?,?,?)',
                                (e['id'], kind, seq, item['desc'], item.get('by', '')))
                        else:
                            conn.execute(
                                'INSERT OR REPLACE INTO log_detail(entry_id,kind,seq,text,by) VALUES(?,?,?,?,?)',
                                (e['id'], kind, seq, item, ''))
                        stats['log_detail'] += 1
                for s in e['sessions']:
                    sid = s['id']
                    # 脏数据清洗：sid 必须真实存在（state.db）
                    if not sid_exists(sid):
                        stats['skipped_sid'].append((title, e['id'], sid))
                        continue
                    conn.execute(
                        'INSERT OR IGNORE INTO log_sessions(entry_id,sid,source) VALUES(?,?,?)',
                        (e['id'], sid, s.get('source', '')))
                    stats['log_sessions'] += 1
                    # 记录引用的 sid 若不在 task_sessions，补 link（273413 案例）
                    conn.execute(
                        'INSERT OR IGNORE INTO task_sessions(task_id,sid,linked_at,source) VALUES(?,?,?,?)',
                        (title, sid, now, 'log-backfill'))
                    stats['task_sessions'] += 1

    conn.commit()
    conn.close()
    print('migrated:', stats)


_state_db = '/Users/ben/.hermes/profiles/business_analysis/state.db'
_sids_cache = None


def sid_exists(sid):
    """sid 是否真实存在于 state.db（防无效 id 混入）。"""
    global _sids_cache
    if _sids_cache is None:
        import sqlite3
        conn = sqlite3.connect(_state_db)
        _sids_cache = {r[0] for r in conn.execute('SELECT id FROM sessions')}
        conn.close()
    return sid in _sids_cache


if __name__ == '__main__':
    main()
