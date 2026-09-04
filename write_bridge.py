#!/usr/bin/env python3
"""P2 写入收口桥：在 obsidian-task.py 的写 op 执行点后挂接。

设计（Ben 2026-09-04 拍板）：
- 写 op（set_property/add_log/edit_yaml_log/toggle_ac/repeat_next…）仍由
  obsidian-task.py 原函数执行（Obsidian vault API，TCC 安全）
- 本桥在其后做三件事：
  1. sync_from_doc：从落盘后的 md 反向同步该实体行到 workbench.db
     —— 现阶段 DB 跟随 op 结果（op 仍是执行主体），但真相源切换的读取面
        （plugin.js/cron）已在 P3 切 DB，op 完成后 DB 与 md 必然一致
  2. change_log：字段级变更记录（含 changed_by）
  3. sid 校验：add_log YAML 条目引用的 sessions.id 必须在 state.db 存在
- P3 之后执行主体反转（先写 DB 再投影），本桥接口保持不变

用法（obsidian-task.py main() 内写 op 分支后调用）：
    from write_bridge import after_write_op
    result = after_write_op(op, spec, result, changed_by)
"""
import json
import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from workbench_db import connect as wb_connect

WB_DB = '/Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/workbench.db'
VAULT = '/Users/ben/Documents/Second Brain/Second Brain'
PROOT_DIR = '2. Project/2.1 Project'
STATE_DB = '/Users/ben/.hermes/profiles/business_analysis/state.db'

TASK_PATH_RE = re.compile(r'^2\. Project/2\.1 Project/([^/]+)/tasks/任务-(.+)\.md$')
PROJ_PATH_RE = re.compile(r'^2\. Project/2\.1 Project/([^/]+)/项目说明-')


def _entity_from_path(path):
    """从 vault 相对路径解析实体。返回 ('task', id) / ('project', id) / None。"""
    m = TASK_PATH_RE.match(path)
    if m:
        return ('task', m.group(2))
    m = PROJ_PATH_RE.match(path)
    if m:
        return ('project', m.group(1))
    return None


def _parse_task_doc(path):
    """解析任务 md（op 执行后的落盘版）→ 结构化 dict（与迁移脚本同规则）。"""
    full = os.path.join(VAULT, path)
    if not os.path.exists(full):
        return None
    text = open(full, encoding='utf-8').read()
    m = re.match(r'^---\n([\s\S]*?)\n---\n?([\s\S]*)$', text)
    if not m:
        return None
    fm_raw, body = m.group(1), m.group(2)
    def grab(key):
        mm = re.search(rf'^{key}:\s*(.*)$', fm_raw, re.M)
        return mm.group(1).strip().strip('"').strip("'") if mm else ''
    # tags 多行
    tags = []
    mm = re.search(r'^tags:\s*\n((?:[ \t]+-[^\n]*\n?)+)', fm_raw, re.M)
    if mm:
        tags = [l.strip()[2:].strip() for l in mm.group(1).strip().split('\n') if l.strip().startswith('-')]
    else:
        mm = re.search(r'^tags:\s*([^\[\n][^\n]*)$', fm_raw, re.M)
        if mm and mm.group(1).strip() and not re.match(r'^\w+:', mm.group(1).strip()):
            tags = [mm.group(1).strip()]
    # sections
    secs = {}
    cur, buf = None, []
    for line in body.split('\n'):
        sm = re.match(r'^## (.+)$', line)
        if sm:
            if cur: secs[cur] = '\n'.join(buf).strip()
            cur, buf = sm.group(1).strip(), []
        elif cur:
            buf.append(line)
    if cur: secs[cur] = '\n'.join(buf).strip()
    lm = re.search(r'^## 推进记录', body, re.M)
    body_text = (body[:lm.start()] if lm else body).strip('\n')
    new = {
        'title': grab('title'), 'status': grab('status'), 'priority': grab('priority'),
        'start': grab('start'), 'due': grab('due'), 'complete': grab('complete'),
        'handler': grab('handler'), 'version': int(grab('version') or 1),
        'kanban_task_id': grab('kanban_task_id'),
        'repeat_mode': grab('repeat_mode'), 'repeat_unit': grab('repeat_unit'),
        'repeat_every': int(grab('repeat_every')) if grab('repeat_every').isdigit() else None,
        'repeat_day': int(grab('repeat_day')) if grab('repeat_day').isdigit() else None,
        'repeat_anchor': grab('repeat_anchor'),
        'tags_json': json.dumps(tags, ensure_ascii=False),
        'session_ids': [s.strip() for s in (re.search(r'^session_ids:\s*(.*)$', fm_raw, re.M).group(1).split(',') if re.search(r'^session_ids:\s*(.*)$', fm_raw, re.M) else []) if s.strip()],
        'goal': secs.get('目标', ''), 'acceptance': secs.get('验收标准', ''),
        'body': secs.get('任务详情', ''),
    }
    # handler 值卫生：值含 ': ' 说明把相邻字段吸进了值（YAML 坏行产物），清空
    if ': ' in (new.get('handler') or ''):
        new['handler'] = ''
    return new


def sid_exists(sid):
    """sid 是否真实存在于 state.db sessions 表。"""
    import sqlite3 as _sq
    conn = _sq.connect(STATE_DB)
    try:
        return conn.execute('SELECT 1 FROM sessions WHERE id=?', (sid,)).fetchone() is not None
    finally:
        conn.close()


def validate_sids(sids):
    """sid 必须真实存在于 state.db（结构性拦截无效引用）。"""
    if not sids:
        return None
    conn = sqlite3.connect(STATE_DB)
    placeholders = ','.join('?' for _ in sids)
    rows = conn.execute(f'SELECT id FROM sessions WHERE id IN ({placeholders})', list(sids)).fetchall()
    conn.close()
    live = {r[0] for r in rows}
    dead = [s for s in sids if s not in live]
    return dead or None



def _parse_project_doc(path):
    """解析项目说明 md（op 执行后的落盘版）→ 结构化 dict（与 render_project_doc 对称）。

    body 拆解：H1 之后到 '## 目标' 之间 = background；'## 目标' 到文末 = goal
    （含其后的任何后续标题，保证 round-trip 无损）。无 '## 目标' 时全部归 background。
    """
    full = os.path.join(VAULT, path)
    if not os.path.exists(full):
        return None
    text = open(full, encoding='utf-8').read()
    m = re.match(r'^---\n([\s\S]*?)\n---\n?([\s\S]*)$', text)
    if not m:
        return None
    fm_raw, body = m.group(1), m.group(2)
    def grab(key):
        mm = re.search(rf'^{key}:\s*(.*)$', fm_raw, re.M)
        return mm.group(1).strip().strip('"').strip("'") if mm else ''
    # tags：多行列表优先，行内兼容
    tags = []
    mm = re.search(r'^tags:\s*\n((?:[ \t]+-[^\n]*\n?)+)', fm_raw, re.M)
    if mm:
        tags = [l.strip()[2:].strip() for l in mm.group(1).strip().split('\n') if l.strip().startswith('-')]
    else:
        mm = re.search(r'^tags:\s*([^\[\n][^\n]*)$', fm_raw, re.M)
        if mm and mm.group(1).strip() and not re.match(r'^\w+:', mm.group(1).strip()):
            tags = [mm.group(1).strip()]
    m_sids = re.search(r'^session_ids:\s*(.*)$', fm_raw, re.M)
    sids = [s.strip() for s in (m_sids.group(1).split(',') if m_sids else []) if s.strip()]
    # body 拆解
    lines = [l for l in body.strip('\n').split('\n')]
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].startswith('# '):
        lines = lines[1:]
    rest = '\n'.join(lines).strip('\n')
    gm = re.search(r'^## 目标\s*$', rest, re.M)
    if gm:
        background = rest[:gm.start()].strip('\n')
        goal = rest[gm.end():].strip('\n')
    else:
        background, goal = rest, ''
    return {
        'name': grab('title'), 'status': grab('status'),
        'start': grab('start'), 'due': grab('due'), 'complete': grab('complete'),
        'version': int(grab('version') or 1),
        'tags_json': json.dumps(tags, ensure_ascii=False),
        'session_ids': sids,
        'background': background, 'goal': goal,
    }




def _align_sessions(conn, table, fk_col, entity_id, sids, now, changed_by):
    """frontmatter session_ids → session 关联表对齐（带存活校验）。

    state.db 不可达时降级：跳过对齐并记入 _LAST_WARNINGS，不阻塞实体同步。"""
    try:
        for sid in sids:
            if not conn.execute(f"SELECT 1 FROM {table} WHERE {fk_col}=? AND sid=?", (entity_id, sid)).fetchone():
                if sid_exists(sid):
                    conn.execute(
                        f"INSERT OR IGNORE INTO {table}({fk_col},sid,linked_at,source) VALUES(?,?,?,?)",
                        (entity_id, sid, now, changed_by or 'op:sync'))
    except Exception as e:
        _LAST_WARNINGS.append(f'sid_align {table}: {type(e).__name__}: {e}')


_LAST_WARNINGS = []


def sync_entity(conn, entity_type, entity_id, changed_by):
    """op 落盘后，把该实体 md 的最新状态同步进 DB 行（含变更历史）。

    documents 映射缺失时自动补建（新建任务/项目场景：文件由 op 落盘，
    DB 行随后创建——创建时序原则的运行时形态）。"""
    global _LAST_WARNINGS
    _LAST_WARNINGS = []
    now = int(time.time())
    if entity_type == 'task':
        # 找到该任务的文档路径；无映射则按标准结构推导并补建
        rel = conn.execute(
            "SELECT path FROM documents WHERE entity_type='task' AND entity_id=?", (entity_id,)).fetchone()
        if not rel:
            # 推导：在标准 tasks 目录下找 任务-<id>.md
            import glob
            cands = glob.glob(os.path.join(VAULT, PROOT_DIR, '*', 'tasks', f'任务-{entity_id}.md'))
            if not cands:
                return False
            rel_path = os.path.relpath(cands[0], VAULT)
            pname = rel_path.split('/')[2]  # 段序: 2. Project / 2.1 Project / <项目名> / tasks / 文件
            conn.execute(
                "INSERT OR IGNORE INTO documents(entity_type,entity_id,path,filename,content_version,generated_at) "
                "VALUES('task',?,?,?,0,?)",
                (entity_id, rel_path, f'任务-{entity_id}.md', now))
            # 项目行若也缺失（新项目未注册），补建最小项目行
            if not conn.execute("SELECT 1 FROM projects WHERE id=?", (pname,)).fetchone():
                conn.execute(
                    "INSERT OR IGNORE INTO projects(id,name,status,version,created_at,updated_at) "
                    "VALUES(?,?,'open',1,?,?)", (pname, pname, now, now))
                conn.execute(
                    "INSERT INTO change_log(entity_type,entity_id,field,old_value,new_value,changed_at,changed_by) "
                    "VALUES('project',?,'__create__',NULL,?,?,?)", (pname, pname, now, changed_by))
            rel = {'path': rel_path}
        new = _parse_task_doc(rel['path'])
        if not new:
            return False
        old = dict(conn.execute('SELECT * FROM tasks WHERE id=?', (entity_id,)).fetchone() or {})
        if not old:
            # 新任务（op 创建）：整行插入
            conn.execute(
                '''INSERT OR IGNORE INTO tasks(id,project_id,title,status,priority,start,due,complete,
                   handler,version,tags_json,kanban_task_id,goal,body,acceptance,
                   repeat_mode,repeat_unit,repeat_every,repeat_day,repeat_anchor,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (entity_id, rel['path'].split('/')[2], new['title'], new['status'], new['priority'],
                 new['start'], new['due'], new['complete'], new['handler'], new['version'],
                 new['tags_json'], new['kanban_task_id'], new['goal'], new['body'], new['acceptance'],
                 new['repeat_mode'], new['repeat_unit'], new['repeat_every'],
                 new['repeat_day'], new['repeat_anchor'], now, now))
            conn.execute(
                "INSERT INTO change_log(entity_type,entity_id,field,old_value,new_value,changed_at,changed_by) "
                "VALUES('task',?,'__create__',NULL,?,?,?)", (entity_id, new['title'], now, changed_by))
            return True
        # 字段级 diff → change_log
        FIELD_MAP = [('status','status'),('priority','priority'),('start','start'),('due','due'),
                     ('complete','complete'),('handler','handler'),('version','version'),
                     ('kanban_task_id','kanban_task_id'),('tags_json','tags_json'),
                     ('goal','goal'),('acceptance','acceptance'),('body','body'),
                     ('repeat_mode','repeat_mode'),('repeat_unit','repeat_unit'),
                     ('repeat_every','repeat_every'),('repeat_day','repeat_day'),
                     ('repeat_anchor','repeat_anchor'),('title','title')]
        changed = [f for f, nk in FIELD_MAP if old.get(f) != new.get(nk)]
        FK = dict(FIELD_MAP)
        for f in changed:
            nk = FK.get(f, f)  # body 无 md 来源键，取自身
            conn.execute(
                "INSERT INTO change_log(entity_type,entity_id,field,old_value,new_value,changed_at,changed_by) "
                "VALUES('task',?,?,?,?,?,?)",
                (entity_id, f, str(old.get(f))[:200] if old.get(f) is not None else None,
                 str(new.get(nk))[:200] if new.get(nk) is not None else None, now, changed_by))
        # session_ids 对齐：frontmatter 新增的 sid 补进 task_sessions（有效性校验）
        _align_sessions(conn, 'task_sessions', 'task_id', entity_id,
                        new.get('session_ids', []), now, changed_by)
        conn.execute(
            '''UPDATE tasks SET title=?,status=?,priority=?,start=?,due=?,complete=?,handler=?,
               version=?,tags_json=?,kanban_task_id=?,goal=?,acceptance=?,body=?,
               repeat_mode=?,repeat_unit=?,repeat_every=?,repeat_day=?,repeat_anchor=?,updated_at=?
               WHERE id=?''',
            (new['title'], new['status'], new['priority'], new['start'], new['due'], new['complete'],
             new['handler'], new['version'], new['tags_json'], new['kanban_task_id'], new['goal'],
             new['acceptance'], new['body'],
             new['repeat_mode'], new['repeat_unit'],
             new['repeat_every'], new['repeat_day'], new['repeat_anchor'], now, entity_id))
        return True
    if entity_type == 'project':
        rel = conn.execute(
            "SELECT path FROM documents WHERE entity_type='project' AND entity_id=?",
            (entity_id,)).fetchone()
        if not rel:
            import glob
            cands = glob.glob(os.path.join(VAULT, PROOT_DIR, entity_id, '项目说明-*.md'))
            if not cands:
                return False
            rel_path = os.path.relpath(cands[0], VAULT)
            conn.execute(
                "INSERT OR IGNORE INTO documents(entity_type,entity_id,path,filename,content_version,generated_at) "
                "VALUES('project',?,?,?,0,?)",
                (entity_id, rel_path, os.path.basename(cands[0]), now))
            rel = {'path': rel_path}
        new = _parse_project_doc(rel['path'])
        if not new:
            return False
        old = dict(conn.execute('SELECT * FROM projects WHERE id=?', (entity_id,)).fetchone() or {})
        if not old:
            conn.execute(
                '''INSERT INTO projects(id,name,status,start,due,complete,version,tags_json,background,goal,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                (entity_id, new['name'], new['status'], new['start'], new['due'], new['complete'],
                 new['version'], new['tags_json'], new['background'], new['goal'], now, now))
            conn.execute(
                "INSERT INTO change_log(entity_type,entity_id,field,old_value,new_value,changed_at,changed_by) "
                "VALUES('project',?,'__create__',NULL,?,?,?)", (entity_id, new['name'], now, changed_by))
        else:
            PFIELDS = [('name','name'),('status','status'),('start','start'),('due','due'),
                       ('complete','complete'),('version','version'),('tags_json','tags_json'),
                       ('background','background'),('goal','goal')]
            for f, nk in PFIELDS:
                if old.get(f) != new.get(nk):
                    conn.execute(
                        "INSERT INTO change_log(entity_type,entity_id,field,old_value,new_value,changed_at,changed_by) "
                        "VALUES('project',?,?,?,?,?,?)",
                        (entity_id, f, str(old.get(f))[:200] if old.get(f) is not None else None,
                         str(new.get(nk))[:200] if new.get(nk) is not None else None, now, changed_by))
            conn.execute(
                '''UPDATE projects SET name=?,status=?,start=?,due=?,complete=?,version=?,
                   tags_json=?,background=?,goal=?,updated_at=? WHERE id=?''',
                (new['name'], new['status'], new['start'], new['due'], new['complete'], new['version'],
                 new['tags_json'], new['background'], new['goal'], now, entity_id))
        _align_sessions(conn, 'project_sessions', 'project_id', entity_id,
                        new.get('session_ids', []), now, changed_by)
        return True
    return False


def after_write_op(op, spec, result, changed_by=''):
    """obsidian-task.py 写 op 后的统一挂接点。返回（可能增强的）result。

    失败不阻塞主 op：sync/change_log 异常只记录日志（op 本身已成功）。"""
    if not isinstance(result, dict) or not result.get('ok'):
        # add_log 的 sid 校验在主 op 之前拦截（结构性拒绝）
        return result
    if op == 'add_log':
        text = spec.get('text', '')
        if text.startswith('- date:'):
            sids = re.findall(r'^\s+- id:\s*(\S+)', text, re.M)
            dead = validate_sids(sids)
            if dead:
                return {'ok': False, 'error': 'INVALID_SESSION_IDS',
                        'detail': f'以下 sid 不存在于 state.db，请先 task_ops link 或修正: {dead}',
                        'invalid_sids': dead}
    try:
        path = spec.get('path', '')
        # repeat_next 特殊处理：注册新实例实体（而非母任务）
        if op == 'repeat_next' and result.get('ok'):
            new_path = result.get('path', '')
            ent = _entity_from_path(new_path)
            if ent:
                conn = wb_connect()
                try:
                    sync_entity(conn, ent[0], ent[1], changed_by or 'op:repeat_next')
                    conn.commit()
                    from write_pipeline import project_write
                    result['projected'] = project_write(conn, ent[0], ent[1], changed_by or 'op:repeat_next')
                finally:
                    conn.close()
            return result
        ent = _entity_from_path(path)
        if not ent:
            return result
        entity_type, entity_id = ent
        conn = wb_connect()
        try:
            ok = sync_entity(conn, entity_type, entity_id, changed_by or f'op:{op}')
            if _LAST_WARNINGS:
                result['sync_warnings'] = list(_LAST_WARNINGS)
            conn.commit()
            if not ok:
                conn.close()
                return result
            # add_log：直接从 op 输入构造 log_entries 行（不解析文件）。
            # 纯文本 → manual 条目（date=now, id=YYYYMMDD_HHMMSS）；
            # YAML 条目（- date: 开头）→ 解析 id/date/type/summary。
            # 这保证 DB 与文件同步，投影不会用空 DB 覆盖刚写入的行。
            if op in ('add_log', 'edit_yaml_log'):
                try:
                    import time as _t
                    import re as _re
                    text = spec.get('text', '')
                    now_s = _t.strftime('%m-%d %H:%M:%S')
                    if op == 'edit_yaml_log':
                        text = spec.get('new_yaml_text', '')
                    if text.startswith('- date:'):
                        idm = _re.search(r'^\s+id:\s*(\S+)', text, _re.M)
                        dm = _re.search(r'^- date:\s*(.+)$', text, _re.M)
                        tm = _re.search(r'^\s+type:\s*(\S+)', text, _re.M)
                        eid = idm.group(1) if idm else _t.strftime('%Y%m%d%H%M%S')
                        date_s = dm.group(1).strip() if dm else now_s
                        typ = tm.group(1) if tm else 'manual'
                        bm = _re.search(r'^\s+summary:\s*\|\n((?:[ \t]*(?:.*\n?)+?))(?=^ {2}\S|\Z)', text, _re.M)
                        sm = _re.search(r'^\s+summary:\s*(.+)$', text, _re.M)
                        summary = bm.group(1).replace('    ', '') if bm else (sm.group(1).strip() if sm else '')
                    else:
                        eid = _t.strftime('%Y%m%d%H%M%S')
                        date_s = now_s
                        typ = 'manual'
                        summary = text
                    if conn.execute("SELECT 1 FROM log_entries WHERE id=?", (eid,)).fetchone():
                        old_row = conn.execute("SELECT summary FROM log_entries WHERE id=?", (eid,)).fetchone()
                        conn.execute("UPDATE log_entries SET summary=?, date=?, type=? WHERE id=?",
                                     (summary, date_s, typ, eid))
                        conn.execute(
                            "INSERT INTO change_log(entity_type,entity_id,field,old_value,new_value,changed_at,changed_by) "
                            "VALUES('task',?,'__log__',?,?,?,?)",
                            (entity_id, (old_row['summary'] or '')[:200], (summary or text)[:200],
                             int(_t.time()), changed_by or f'op:{op}'))
                        conn.commit()
                    else:
                        conn.execute(
                            "INSERT OR IGNORE INTO log_entries(id,task_id,date,type,summary,created_at) VALUES(?,?,?,?,?,?)",
                            (eid, entity_id, date_s, typ, summary, int(_t.time())))
                        conn.execute(
                            "INSERT INTO change_log(entity_type,entity_id,field,old_value,new_value,changed_at,changed_by) "
                            "VALUES('task',?,'__log__',NULL,?,?,?)",
                            (entity_id, (summary or text)[:200], int(_t.time()), changed_by or f'op:{op}'))
                except Exception as _log_err:
                    result['log_sync_warning'] = f'{type(_log_err).__name__}: {_log_err}'
            # 投影：op 产物已落盘，此处用 DB 状态再渲染一次做规范化收敛
            from write_pipeline import project_write
            pw = project_write(conn, entity_type, entity_id, changed_by or f'op:{op}')
            result['projected'] = pw
        finally:
            conn.close()
    except Exception as e:
        result['projection_warning'] = f'{type(e).__name__}: {e}'
    return result
