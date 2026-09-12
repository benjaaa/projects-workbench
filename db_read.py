#!/usr/bin/env python3
"""db_read.py — 统一读入口：查询 → 补关联 → 返回

职责：
- 从 workbench.db 读取项目/任务数据
- 补充关联信息（session_ids 从 task_sessions/project_sessions 合并）
- 返回与现有 plugin.js 兼容的数据结构

设计原则：
- 读路径唯一入口，替代 read_bridge.py + load_projects/load_tasks
- 接口兼容：返回字段与现有 frontmatter 解析版完全一致
- DB 异常时返回空列表（不抛异常，前端有兜底）
"""
import os
import sqlite3
import time

from db_transaction import current_transaction

# 路径常量
VAULT = '/Users/ben/Documents/Second Brain/Second Brain'
PROOT = '2. Project/2.1 Project'
WB_DB = '/Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/workbench.db'


def _conn():
    """获取 DB 连接（只读模式）。"""
    active = current_transaction()
    if active:
        return active.proxy
    conn = sqlite3.connect(WB_DB)
    conn.row_factory = sqlite3.Row
    return conn


def _today():
    return time.strftime('%Y-%m-%d')


def _ts_to_date(ts):
    """Unix 时间戳 → YYYY-MM-DD。"""
    if not ts:
        return ''
    try:
        from datetime import datetime
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
    except Exception:
        return ''


def _add_days(n):
    """今天起 n 天后的日期串（YYYY-MM-DD）。"""
    import datetime
    d = datetime.date.today() + datetime.timedelta(days=n)
    return d.strftime('%Y-%m-%d')


def _enrich_task(conn, task):
    """补充任务关联信息。
    
    - session_ids: 从 task_sessions 表合并（替代 frontmatter session_ids）
    - logs: 从 log_entries + log_detail + log_sessions 重建
    - acceptance_criteria: 从 acceptance 文本解析为数组
    """
    task = dict(task)
    
    # 1. session_ids 从 DB 合并
    sids = [r[0] for r in conn.execute(
        'SELECT sid FROM task_sessions WHERE task_id=? ORDER BY linked_at', (task['id'],)
    ).fetchall()]
    task['session_ids'] = ','.join(sids) if sids else ''
    
    # 2. acceptance_criteria 解析
    acceptance = task.get('acceptance', '') or ''
    ac_list = []
    for line in acceptance.split('\n'):
        line = line.strip()
        if not line:
            continue
        # 解析 - [x] / - [ ] / - [-] 格式
        import re
        m = re.match(r'^[-*]\s*\[([xX\- ])\]\s*(.*)$', line)
        if m:
            mark = m.group(1).lower()
            ac_list.append({
                'text': m.group(2).strip(),
                'done': mark == 'x',
                'failed': mark == '-',
            })
        else:
            # 非标准格式，保留原文本
            ac_list.append({'text': line, 'done': False, 'failed': False})
    task['acceptance_criteria'] = ac_list
    
    # 3. logs 从 DB 重建为结构化列表
    log_entries = []
    for entry_row in conn.execute(
        'SELECT * FROM log_entries WHERE task_id=? ORDER BY date DESC', (task['id'],)
    ).fetchall():
        entry = dict(entry_row)
        
        # 会话
        entry['sessions'] = [{'id': r['sid'], 'source': r['source']} for r in conn.execute(
            'SELECT sid, source FROM log_sessions WHERE entry_id=?', (entry['id'],)
        ).fetchall()]
        
        # 明细
        for kind in ('outputs', 'risks', 'pending', 'decisions'):
            rows = conn.execute(
                'SELECT text, by FROM log_detail WHERE entry_id=? AND kind=? ORDER BY seq',
                (entry['id'], kind)
            ).fetchall()
            if kind == 'decisions':
                entry[kind] = [{'desc': r['text'], 'by': r['by']} for r in rows]
            else:
                entry[kind] = [r['text'] for r in rows]
        
        log_entries.append(entry)
    
    # 4. 结构化 logs（Codex UI / Agent 的规范格式）
    task['logs'] = log_entries
    
    # 5. 补充 path 和 dir（plugin.js 依赖）
    # UUID 主键后：path 用 title（可改），dir 需要解析项目名
    proj_row = conn.execute('SELECT name FROM projects WHERE id=?', (task['project_id'],)).fetchone()
    proj_name = proj_row['name'] if proj_row else task['project_id']
    task['path'] = f'{PROOT}/{proj_name}/tasks/任务-{task["title"]}.md'
    task['dir'] = proj_name
    
    # 6. 字段名映射（DB → frontmatter 兼容）
    task['title'] = task.get('title', task['id'])
    task['status'] = task.get('status', 'open')
    task['priority'] = task.get('priority', 'p2')
    task['handler'] = task.get('handler', '')
    # 日期字段：INTEGER → TEXT 转换（兼容前端）
    task['start'] = _ts_to_date(task.get('start'))
    task['due'] = _ts_to_date(task.get('due'))
    task['complete'] = _ts_to_date(task.get('complete'))
    task['created'] = task.get('created_at', '')
    task['updated'] = task.get('updated_at', '')
    task['goal'] = task.get('goal', '')
    task['task_detail'] = task.get('body', '')
    task['output'] = []  # 暂无输出跟踪
    task['tags'] = []
    
    return task


def _enrich_project(conn, project):
    """补充项目关联信息。
    
    - session_ids: 从 project_sessions 表合并
    - path / dir: 补充路径信息
    """
    project = dict(project)
    
    # session_ids 从 DB 合并
    sids = [r[0] for r in conn.execute(
        'SELECT sid FROM project_sessions WHERE project_id=? ORDER BY linked_at', (project['id'],)
    ).fetchall()]
    project['session_ids'] = ','.join(sids) if sids else ''
    
    # 补充 path 和 dir
    # UUID 主键后：dir 用 name（可改），不是 id（UUID）
    proj_dir = os.path.join(VAULT, PROOT, project['name'])
    cands = [f for f in os.listdir(proj_dir) if f.startswith('项目说明-') and f.endswith('.md')] if os.path.exists(proj_dir) else []
    filename = cands[0] if cands else f'项目说明-{project["name"]}.md'
    project['path'] = f'{PROOT}/{project["name"]}/{filename}'
    project['dir'] = project['name']
    
    # 字段名映射
    project['title'] = project.get('name', project['id'])
    project['status'] = project.get('status', 'open')
    # 日期字段：INTEGER → TEXT 转换（兼容前端）
    project['start'] = _ts_to_date(project.get('start'))
    project['due'] = _ts_to_date(project.get('due'))
    project['complete'] = _ts_to_date(project.get('complete'))
    project['background'] = project.get('background', '')
    project['goal'] = project.get('goal', '')
    
    return project


def load_projects():
    """加载所有项目（DB 优先）。
    
    Returns:
        dict: {'projects': [...]} 与现有 load_projects() 格式一致
    """
    try:
        conn = _conn()
        try:
            rows = conn.execute('SELECT * FROM projects ORDER BY created_at DESC').fetchall()
            projects = [_enrich_project(conn, dict(r)) for r in rows]
            return {'projects': projects}
        finally:
            conn.close()
    except Exception as e:
        # DB 异常时返回空列表（前端有降级逻辑）
        return {'projects': [], 'error': str(e)}


def load_tasks():
    """加载所有任务（DB 优先）。
    
    Returns:
        dict: {'tasks': [...]} 与现有 load_tasks() 格式一致
    """
    try:
        conn = _conn()
        try:
            rows = conn.execute('SELECT * FROM tasks ORDER BY created_at DESC').fetchall()
            tasks = [_enrich_task(conn, dict(r)) for r in rows]
            return {'tasks': tasks}
        finally:
            conn.close()
    except Exception as e:
        return {'tasks': [], 'error': str(e)}


def get_task(task_id):
    """获取单个任务（含完整关联）。
    
    Args:
        task_id: str，任务 ID
    
    Returns:
        dict | None: 任务数据，不存在返回 None
    """
    try:
        conn = _conn()
        try:
            row = conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            if not row:
                return None
            return _enrich_task(conn, dict(row))
        finally:
            conn.close()
    except Exception:
        return None


def get_project(project_id):
    """获取单个项目。
    
    Args:
        project_id: str，项目 ID
    
    Returns:
        dict | None: 项目数据，不存在返回 None
    """
    try:
        conn = _conn()
        try:
            row = conn.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
            if not row:
                return None
            return _enrich_project(conn, dict(row))
        finally:
            conn.close()
    except Exception:
        return None


# ─── 兼容接口（供 obsidian-task.py 调用）────────────────────────

def load_projects_safe():
    """安全加载项目（DB 优先，异常返回 None 供降级）。"""
    try:
        result = load_projects()
        if result.get('error'):
            return None
        return result
    except Exception:
        return None


def load_tasks_safe():
    """安全加载任务（DB 优先，异常返回 None 供降级）。"""
    try:
        result = load_tasks()
        if result.get('error'):
            return None
        return result
    except Exception:
        return None
