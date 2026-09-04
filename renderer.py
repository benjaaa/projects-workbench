#!/usr/bin/env python3
"""renderer.py — 纯渲染器：DB 行 → Markdown 字符串 → 文件

职责：
- 从 DB 行渲染 Markdown 文档（项目/任务）
- 写入文件（osascript cp 绕 TCC）
- 无 DB 写入，无副作用（除文件写入）

设计原则：
- 纯函数：render_project / render_task 输入 DB 行，输出字符串
- 写文件独立：write_rendered 有副作用，单独隔离
- 可测试：render 函数可单元测试，无需 DB 连接
"""
import os
import subprocess
import tempfile

# 路径常量
VAULT = '/Users/ben/Documents/Second Brain/Second Brain'
PROOT = '2. Project/2.1 Project'


def _ts_to_date(ts):
    """Unix 时间戳 → YYYY-MM-DD。"""
    if not ts:
        return ''
    try:
        from datetime import datetime
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
    except Exception:
        return ''


def render_project(project, session_ids):
    """渲染项目说明文档。
    
    Args:
        project: dict，projects 表行（含 background, goal, status, start, due 等）
        session_ids: list[str]，关联的 session id 列表
    
    Returns:
        str: 完整 Markdown 文档
    """
    lines = []
    
    # Frontmatter
    lines.append('---')
    lines.append(f'title: {project.get("name", "")}')
    lines.append(f'status: {project.get("status", "open")}')
    if project.get('start'):
        lines.append(f'start: {_ts_to_date(project["start"])}')
    if project.get('due'):
        lines.append(f'due: {_ts_to_date(project["due"])}')
    if project.get('complete'):
        lines.append(f'complete: {_ts_to_date(project["complete"])}')
    if project.get('version'):
        lines.append(f'version: {project["version"]}')
    lines.append('tags:')
    lines.append('  - project')
    if session_ids:
        lines.append(f'session_ids: {",".join(session_ids)}')
    lines.append('---')
    lines.append('')
    
    # Body
    lines.append(f'# {project.get("name", "")}')
    lines.append('')
    lines.append('## 项目背景')
    lines.append(project.get('background', '') or '（暂无）')
    lines.append('')
    lines.append('## 项目目标')
    lines.append(project.get('goal', '') or '（暂无）')
    lines.append('')
    
    return '\n'.join(lines)


def render_task(task, session_ids, log_entries):
    """渲染任务文档。
    
    Args:
        task: dict，tasks 表行（含 title, status, priority, goal, body, acceptance 等）
        session_ids: list[str]，关联的 session id 列表
        log_entries: list[dict]，推进记录列表（含 date, type, summary, sessions, outputs 等）
    
    Returns:
        str: 完整 Markdown 文档
    """
    lines = []
    
    # Frontmatter
    lines.append('---')
    lines.append(f'title: {task.get("title", "")}')
    lines.append(f'status: {task.get("status", "open")}')
    if task.get('priority'):
        lines.append(f'priority: {task["priority"]}')
    if task.get('handler'):
        lines.append(f'handler: {task["handler"]}')
    if task.get('project_id'):
        lines.append(f'project: {task["project_id"]}')
    if task.get('start'):
        lines.append(f'start: {_ts_to_date(task["start"])}')
    if task.get('due'):
        lines.append(f'due: {_ts_to_date(task["due"])}')
    if task.get('complete'):
        lines.append(f'complete: {_ts_to_date(task["complete"])}')
    if task.get('kanban_task_id'):
        lines.append(f'kanban_task_id: {task["kanban_task_id"]}')
    # 重复任务字段
    if task.get('repeat_mode'):
        lines.append(f'repeat_mode: {task["repeat_mode"]}')
    if task.get('repeat_unit'):
        lines.append(f'repeat_unit: {task["repeat_unit"]}')
    if task.get('repeat_every') is not None:
        lines.append(f'repeat_every: {task["repeat_every"]}')
    if task.get('repeat_day') is not None:
        lines.append(f'repeat_day: {task["repeat_day"]}')
    if task.get('repeat_anchor'):
        lines.append(f'repeat_anchor: {task["repeat_anchor"]}')
    if task.get('version'):
        lines.append(f'version: {task["version"]}')
    lines.append('tags:')
    lines.append('  - task')
    if session_ids:
        lines.append(f'session_ids: {",".join(session_ids)}')
    lines.append('---')
    lines.append('')
    
    # Body
    lines.append(f'# {task.get("title", "")}')
    lines.append('')
    lines.append('## 目标')
    lines.append(task.get('goal', '') or '（暂无）')
    lines.append('')
    lines.append('## 任务详情')
    lines.append(task.get('body', '') or '（任务背景、目的、方案等补充信息，可自由组织子标题）')
    lines.append('')
    lines.append('## 验收标准')
    acceptance = task.get('acceptance', '') or ''
    if acceptance.strip():
        for line in acceptance.split('\n'):
            if line.strip():
                lines.append(line)
    else:
        lines.append('- [ ] （待补充）')
    lines.append('')
    lines.append('## 推进记录')
    
    # YAML 推进记录
    if log_entries:
        lines.append('```yaml')
        for entry in log_entries:
            lines.append(f'- date: {entry.get("date", "")}')
            if entry.get('id'):
                lines.append(f'  id: {entry["id"]}')
            lines.append(f'  type: {entry.get("type", "manual")}')
            summary = entry.get('summary', '')
            if summary:
                if '\n' in summary:
                    lines.append('  summary: |')
                    for sl in summary.split('\n'):
                        lines.append(f'    {sl}')
                else:
                    lines.append(f'  summary: {summary}')
            if entry.get('window'):
                lines.append(f'  window: "{entry["window"]}"')
            # sessions
            sessions = entry.get('sessions', [])
            if sessions:
                lines.append('  sessions:')
                for s in sessions:
                    lines.append(f'    - id: {s.get("sid", "")}')
                    if s.get('source'):
                        lines.append(f'      source: {s["source"]}')
            # outputs / risks / pending / decisions
            for kind in ('outputs', 'risks', 'pending'):
                items = entry.get(kind, [])
                if items:
                    lines.append(f'  {kind}:')
                    for item in items:
                        lines.append(f'    - {item}')
            decisions = entry.get('decisions', [])
            if decisions:
                lines.append('  decisions:')
                for d in decisions:
                    lines.append(f'    - desc: {d.get("text", "")}')
                    if d.get('by'):
                        lines.append(f'      by: {d["by"]}')
        lines.append('```')
    else:
        lines.append('- （暂无）')
    lines.append('')
    
    return '\n'.join(lines)


def write_rendered(path, content):
    """将渲染内容写入文件（osascript cp 绕 TCC）。
    
    Args:
        path: vault 相对路径，如 '2. Project/2.1 Project/test专项/项目说明-test专项.md'
        content: Markdown 字符串
    
    Returns:
        bool: 写入成功返回 True，失败返回 False
    
    Raises:
        RuntimeError: osascript 执行失败时抛出
    """
    full_path = os.path.join(VAULT, path)
    
    # 确保目录存在
    dir_path = os.path.dirname(full_path)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
    
    # 内容比对：无变化则跳过写入（减少文件系统事件）
    if os.path.exists(full_path):
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                existing = f.read()
            if existing == content:
                return True  # 无变化，视为成功
        except Exception:
            pass  # 读取失败继续写入
    
    # 写临时文件
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.md', prefix='hpw_render_')
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # osascript cp 绕 TCC
        p = subprocess.run(
            ['osascript', '-e', f'do shell script "cp {tmp_path} \\"{full_path}\\" && rm {tmp_path}"'],
            capture_output=True,
            timeout=30
        )
        if p.returncode != 0:
            raise RuntimeError(f'osascript cp failed: {p.stderr.decode()[:200]}')
        return True
    except Exception as e:
        # 清理临时文件
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise RuntimeError(f'write_rendered failed: {e}')


# ─── 辅助函数：从 DB 构建渲染参数 ─────────────────────────────

def build_task_render_args(conn, task_id):
    """从 DB 查询渲染任务所需的所有数据。
    
    Args:
        conn: sqlite3.Connection（workbench.db）
        task_id: str，任务 ID
    
    Returns:
        tuple: (task_dict, session_ids, log_entries)
        
    Raises:
        ValueError: 任务不存在
    """
    # 任务主表
    row = conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
    if not row:
        raise ValueError(f'task not found: {task_id}')
    task = dict(row)
    
    # 关联会话
    session_ids = [r[0] for r in conn.execute(
        'SELECT sid FROM task_sessions WHERE task_id=? ORDER BY linked_at', (task_id,)
    ).fetchall()]
    
    # 推进记录
    log_entries = []
    for entry_row in conn.execute(
        'SELECT * FROM log_entries WHERE task_id=? ORDER BY date DESC', (task_id,)
    ).fetchall():
        entry = dict(entry_row)
        
        # 会话
        entry['sessions'] = [dict(r) for r in conn.execute(
            'SELECT sid, source FROM log_sessions WHERE entry_id=?', (entry['id'],)
        ).fetchall()]
        
        # 明细（outputs / risks / pending / decisions）
        for kind in ('outputs', 'risks', 'pending', 'decisions'):
            rows = conn.execute(
                'SELECT text, by FROM log_detail WHERE entry_id=? AND kind=? ORDER BY seq',
                (entry['id'], kind)
            ).fetchall()
            if kind == 'decisions':
                entry[kind] = [{'text': r['text'], 'by': r['by']} for r in rows]
            else:
                entry[kind] = [r['text'] for r in rows]
        
        log_entries.append(entry)
    
    return task, session_ids, log_entries


def build_project_render_args(conn, project_id):
    """从 DB 查询渲染项目所需的所有数据。
    
    Args:
        conn: sqlite3.Connection（workbench.db）
        project_id: str，项目 ID
    
    Returns:
        tuple: (project_dict, session_ids)
        
    Raises:
        ValueError: 项目不存在
    """
    row = conn.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
    if not row:
        raise ValueError(f'project not found: {project_id}')
    project = dict(row)
    
    session_ids = [r[0] for r in conn.execute(
        'SELECT sid FROM project_sessions WHERE project_id=? ORDER BY linked_at', (project_id,)
    ).fetchall()]
    
    return project, session_ids


# ─── 完整渲染入口（供 db_core 调用）────────────────────────────

def render_entity(conn, entity_type, entity_id):
    """渲染指定实体并写入文件。
    
    Args:
        conn: sqlite3.Connection（workbench.db）
        entity_type: 'project' | 'task'
        entity_id: str
    
    Returns:
        dict: {'ok': True, 'path': str} 或 {'ok': False, 'error': str}
    """
    try:
        if entity_type == 'task':
            task, sids, logs = build_task_render_args(conn, entity_id)
            content = render_task(task, sids, logs)
            # 用 title 生成文件名（可改），不用 UUID
            # project_id 是 UUID，需要解析为项目名
            proj_row = conn.execute('SELECT name FROM projects WHERE id=?', (task['project_id'],)).fetchone()
            proj_name = proj_row['name'] if proj_row else task['project_id']
            path = f'{PROOT}/{proj_name}/tasks/任务-{task["title"]}.md'
        elif entity_type == 'project':
            project, sids = build_project_render_args(conn, entity_id)
            content = render_project(project, sids)
            # 用 name 生成文件名（可改），不用 UUID
            proj_dir = os.path.join(VAULT, PROOT, project['name'])
            cands = [f for f in os.listdir(proj_dir) if f.startswith('项目说明-') and f.endswith('.md')] if os.path.exists(proj_dir) else []
            filename = cands[0] if cands else f'项目说明-{project["name"]}.md'
            path = f'{PROOT}/{project["name"]}/{filename}'
        else:
            return {'ok': False, 'error': f'unknown entity_type: {entity_type}'}
        
        write_rendered(path, content)
        return {'ok': True, 'path': path}
    except Exception as e:
        return {'ok': False, 'error': f'{type(e).__name__}: {e}'}
