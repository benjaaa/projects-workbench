#!/usr/bin/env python3
"""db_core.py — 统一写入口：校验 → 写 DB → 写日志 → 触发渲染

职责：
- 所有写操作的唯一入口（set_property / update_section / set_body / toggle_ac / add_log 等）
- 字段校验、枚举值校验、乐观锁校验
- 写 workbench.db（事务）
- 写 workbench.log.db（操作日志 + 变更日志）
- 调用 renderer.py 触发投影渲染（失败进重试队列）

设计原则：
- DB 唯一真相源：写操作只写 DB，文件由渲染器投影
- 单文件模块：无外部依赖（除 sqlite3、renderer、db_read）
- 接口兼容：函数签名与现有 db_ops.py 一致，供 obsidian-task.py 调用
"""
import os
import re
import sqlite3
import subprocess
import time
import json

from db_transaction import current_transaction

# 路径常量
VAULT = '/Users/ben/Documents/Second Brain/Second Brain'
PROOT = '2. Project/2.1 Project'
WB_DB = '/Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/workbench.db'
LOG_DB = '/Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/workbench-log.db'

# 正则
TASK_RE = re.compile(r'^2\. Project/2\.1 Project/([^/]+)/tasks/任务-(.+)\.md$')
PROJ_RE = re.compile(r'^2\. Project/2\.1 Project/([^/]+)/项目说明-')

# 字段白名单
TASK_FIELDS = {'status', 'priority', 'start', 'due', 'complete', 'handler',
               'title', 'kanban_task_id', 'repeat_anchor'}
PROJ_FIELDS = {'status', 'start', 'due', 'complete', 'name'}
SECTION_FIELD = {'目标': 'goal', '任务详情': 'body', '验收标准': 'acceptance',
                 '项目背景': 'background', '项目目标': 'goal'}

# 合法枚举值
VALID_PROJECT_STATUSES = {'open', 'In-Progress', 'Waiting', 'Routine', 'Done', 'Dropped'}
VALID_TASK_STATUSES = {'open', 'In-Progress', 'Waiting', 'Agent', 'Review', 'Done', 'Dropped'}
VALID_DRAFT_STATUSES = {'open', 'archived'}
VALID_PRIORITIES = {'p0', 'p1', 'p2'}

# Inbox 收集箱（draft）目录：与项目目录平行，独立实体，不进 tasks 表
INBOX_DIR = '2. Project/Inbox'
DRAFT_RE = re.compile(r'^2\. Project/Inbox/(.+)\.md$')


def _ts_to_date(ts):
    """Unix 时间戳 → YYYY-MM-DD。"""
    if not ts:
        return ''
    try:
        from datetime import datetime
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
    except Exception:
        return ''


def _date_to_ts(date_str):
    """YYYY-MM-DD → Unix 时间戳。"""
    if not date_str:
        return None
    try:
        from datetime import datetime
        d = datetime.strptime(str(date_str).strip(), '%Y-%m-%d')
        return int(d.timestamp())
    except Exception:
        return None


# ─── 连接管理 ─────────────────────────────────────────────────

def _wb_conn():
    """获取业务 DB 连接（读写模式，启用外键约束）。"""
    active = current_transaction()
    if active:
        return active.proxy
    conn = sqlite3.connect(WB_DB)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def _log_conn():
    """获取日志 DB 连接（读写模式）。"""
    conn = sqlite3.connect(LOG_DB)
    conn.row_factory = sqlite3.Row
    _ensure_log_tables(conn)
    return conn


def _ensure_log_tables(conn):
    """确保日志表存在。"""
    conn.execute('''CREATE TABLE IF NOT EXISTS ops_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        action TEXT NOT NULL,
        entity_type TEXT DEFAULT '',
        entity_id TEXT DEFAULT '',
        detail TEXT DEFAULT '',
        created_at INTEGER NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS change_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        field TEXT NOT NULL,
        old_value TEXT,
        new_value TEXT,
        changed_at INTEGER NOT NULL,
        changed_by TEXT DEFAULT ''
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_ops_entity ON ops_log(entity_type, entity_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_ops_time ON ops_log(created_at)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_change_entity ON change_log(entity_type, entity_id, changed_at)')
    conn.commit()


# ─── Inbox 收集箱（draft）：独立实体，与 tasks 完全隔离 ──────────

def _ensure_draft_table(conn):
    """确保 drafts 表存在（draft=信息不完整、尚未立项的暂存条目）。"""
    conn.execute('''CREATE TABLE IF NOT EXISTS drafts (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL UNIQUE,
        body TEXT DEFAULT '',
        ts INTEGER,
        status TEXT DEFAULT 'open',
        converted_task_id TEXT DEFAULT '',
        created_at INTEGER,
        updated_at INTEGER,
        version INTEGER DEFAULT 1
    )''')


def create_draft(title, body='', changed_by=''):
    """创建收集箱条目（DB 先行，文件由渲染投影到 2. Project/Inbox/）。

    Returns:
        dict: {'ok': True, 'draft_id': str, 'path': str} 或 {'ok': False, 'error': str}
    """
    try:
        title = (title or '').strip() or '未命名'
        # 安全校验：标题将进入文件路径（Inbox/<title>.md）与 shell 命令
        _validate_safe_name(title, 'title')
        conn = _wb_conn()
        try:
            _ensure_draft_table(conn)
            # 同名去重：已存在则直接返回现有条目（幂等）
            row = conn.execute('SELECT id, status FROM drafts WHERE title=?', (title,)).fetchone()
            if row:
                return {'ok': True, 'draft_id': row['id'], 'existed': True,
                        'path': f'{INBOX_DIR}/{title}.md'}
            import uuid
            draft_id = uuid.uuid4().hex[:12]
            now = int(time.time())
            conn.execute('''INSERT INTO drafts(id, title, body, ts, status, created_at, updated_at, version)
                VALUES(?,?,?,?,?,?,?,?)''', (draft_id, title, body, now, 'open', now, now, 1))
            conn.execute('''INSERT OR REPLACE INTO documents(entity_type, entity_id, doc_type, path, updated_at)
                VALUES(?,?,?,?,?)''', ('draft', draft_id, 'main', f'{INBOX_DIR}/{title}.md', now))
            _log_change('draft', draft_id, 'created', None, draft_id, changed_by)
            conn.commit()
            _trigger_render('draft', draft_id)
            _log_op(changed_by or 'plugin', 'inbox_create', 'draft', draft_id, f'创建收集「{title}」')
            return {'ok': True, 'draft_id': draft_id, 'path': f'{INBOX_DIR}/{title}.md'}
        finally:
            conn.close()
    except Exception as e:
        return {'ok': False, 'error': f'{type(e).__name__}: {e}'}


def list_drafts(include_archived=True):
    """列出收集箱条目（按 ts 倒序），输出形状与旧 inbox_list 文件扫描版一致。

    Returns:
        dict: {'ok': True, 'items': [{'name','path','title','ts','first','content','draft_id','status'}]}
    """
    try:
        conn = _wb_conn()
        try:
            _ensure_draft_table(conn)
            sql = 'SELECT * FROM drafts'
            if not include_archived:
                sql += " WHERE status='open'"
            sql += ' ORDER BY ts DESC'
            rows = conn.execute(sql).fetchall()
            items = []
            for r in rows:
                body = r['body'] or ''
                first = body.strip().split('\n')[0] if body.strip() else ''
                # ts 保持 ISO 字符串形状（与旧版 frontmatter ts 一致）
                ts_str = ''
                if r['ts']:
                    from datetime import datetime
                    ts_str = datetime.fromtimestamp(r['ts']).strftime('%Y-%m-%dT%H:%M')
                content = _render_draft_md(r)
                items.append({
                    'name': r['title'], 'path': f'{INBOX_DIR}/{r["title"]}.md',
                    'title': r['title'], 'ts': ts_str, 'first': first,
                    'body': body, 'content': content, 'draft_id': r['id'], 'status': r['status']
                })
            return {'ok': True, 'items': items}
        finally:
            conn.close()
    except Exception as e:
        return {'ok': False, 'error': f'{type(e).__name__}: {e}', 'items': []}


def _render_draft_md(row):
    """渲染 draft 的 md 投影（frontmatter + 正文）。"""
    from datetime import datetime
    lines = ['---', f'title: {row["title"]}']
    if row['ts']:
        lines.append(f'ts: {datetime.fromtimestamp(row["ts"]).strftime("%Y-%m-%dT%H:%M")}')
    lines.append(f'status: {row["status"] or "open"}')
    lines.append('---')
    lines.append('')
    lines.append(row['body'] or '')
    return '\n'.join(lines)


def delete_draft(draft_id_or_title, changed_by=''):
    """删除收集箱条目（DB 记录 + 物理文件，各自独立互不阻塞）。

    Returns:
        dict: {'ok': True, 'db_deleted': bool, 'file_deleted': bool} 或 {'ok': False, ...}
    """
    try:
        conn = _wb_conn()
        db_deleted = False
        file_deleted = False
        try:
            _ensure_draft_table(conn)
            row = conn.execute('SELECT * FROM drafts WHERE id=?', (draft_id_or_title,)).fetchone()
            if not row:
                row = conn.execute('SELECT * FROM drafts WHERE title=?', (draft_id_or_title,)).fetchone()
            if row:
                real_id = row['id']
                title = row['title']
                conn.execute('DELETE FROM documents WHERE entity_type=? AND entity_id=?', ('draft', real_id))
                conn.execute('DELETE FROM drafts WHERE id=?', (real_id,))
                _log_change('draft', real_id, 'deleted', title, None, changed_by)
                conn.commit()
                db_deleted = True
            else:
                title = draft_id_or_title
        finally:
            conn.close()

        file_path = os.path.join(VAULT, INBOX_DIR, f'{title}.md')
        if os.path.exists(file_path):
            try:
                os.unlink(file_path)
                file_deleted = True
            except Exception:
                pass

        if not db_deleted and not file_deleted:
            return {'ok': False, 'error': f'draft not found: {draft_id_or_title}'}
        _log_op(changed_by or 'plugin', 'inbox_delete', 'draft', draft_id_or_title,
                f'删除收集「{title}」（db={db_deleted}, file={file_deleted}）')
        return {'ok': True, 'db_deleted': db_deleted, 'file_deleted': file_deleted}
    except Exception as e:
        return {'ok': False, 'error': f'{type(e).__name__}: {e}'}


def convert_draft(draft_id_or_title, project_id, changed_by=''):
    """draft 立项为正式任务：create_task → 文件移入项目 tasks/ → draft 置 archived 留痕。

    Returns:
        dict: {'ok': True, 'task_id': str, 'task_path': str} 或 {'ok': False, 'error': str}
    """
    try:
        conn = _wb_conn()
        try:
            _ensure_draft_table(conn)
            row = conn.execute('SELECT * FROM drafts WHERE id=?', (draft_id_or_title,)).fetchone()
            if not row:
                row = conn.execute('SELECT * FROM drafts WHERE title=?', (draft_id_or_title,)).fetchone()
            if not row:
                return {'ok': False, 'error': f'draft not found: {draft_id_or_title}'}
            if row['status'] == 'archived':
                return {'ok': False, 'error': f'draft 已归档（converted_task_id={row["converted_task_id"]}）'}
            draft_id = row['id']
            draft_title = row['title']
            draft_body = row['body'] or ''
        finally:
            conn.close()

        # 创建正式任务（复用现有 create_task，body 带入 draft 正文）
        result = create_task(project_id, draft_title, task_detail=draft_body, changed_by=changed_by)
        if not result.get('ok'):
            return result
        task_id = result['task_id']

        # 更新 draft：archived + converted_task_id
        conn = _wb_conn()
        try:
            now = int(time.time())
            conn.execute('UPDATE drafts SET status=?, converted_task_id=?, updated_at=?, version=version+1 WHERE id=?',
                         ('archived', task_id, now, draft_id))
            _log_change('draft', draft_id, 'status', 'open', 'archived', changed_by)
            _log_change('draft', draft_id, 'converted_task_id', None, task_id, changed_by)
            conn.commit()
        finally:
            conn.close()

        # 删除 Inbox 下的旧文件（任务文件已由 create_task 渲染到项目 tasks/）
        old_file = os.path.join(VAULT, INBOX_DIR, f'{draft_title}.md')
        if os.path.exists(old_file):
            try:
                os.unlink(old_file)
            except Exception:
                pass

        _log_op(changed_by or 'plugin', 'draft_convert', 'draft', draft_id,
                f'收集「{draft_title}」立项为任务 {task_id}')
        return {'ok': True, 'task_id': task_id, 'draft_id': draft_id}
    except Exception as e:
        return {'ok': False, 'error': f'{type(e).__name__}: {e}'}


# ─── 日志写入 ─────────────────────────────────────────────────

def _log_op(source, action, entity_type='', entity_id='', detail=''):
    """写操作日志。"""
    try:
        conn = _log_conn()
        try:
            conn.execute(
                'INSERT INTO ops_log(source, action, entity_type, entity_id, detail, created_at) VALUES(?,?,?,?,?,?)',
                (source, action, entity_type, entity_id, detail, int(time.time() * 1000))
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass  # 日志失败不阻塞主流程


def _log_change(entity_type, entity_id, field, old_value, new_value, changed_by=''):
    """写变更日志。"""
    try:
        conn = _log_conn()
        try:
            conn.execute(
                'INSERT INTO change_log(entity_type, entity_id, field, old_value, new_value, changed_at, changed_by) VALUES(?,?,?,?,?,?,?)',
                (entity_type, entity_id, field,
                 None if old_value is None else str(old_value),
                 None if new_value is None else str(new_value),
                 int(time.time()), changed_by)
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


# ─── 渲染触发 ─────────────────────────────────────────────────

def _trigger_render(entity_type, entity_id):
    """触发渲染（失败进重试队列）。"""
    active = current_transaction()
    if active:
        active.defer_render(entity_type, entity_id)
        return {'ok': True, 'render_pending': True}
    return _render_now(entity_type, entity_id)


def flush_deferred_renders(renders):
    """Render entities after the domain transaction has committed."""
    results = []
    for entity_type, entity_id in renders or []:
        result = _render_now(entity_type, entity_id)
        results.append({'entity_type': entity_type, 'entity_id': entity_id, **result})
    return results


def _render_now(entity_type, entity_id):
    """Render outside a domain transaction."""
    try:
        import renderer
        # 获取 DB 连接（需要新连接，因为当前连接可能已关闭）
        conn = _wb_conn()
        try:
            result = renderer.render_entity(conn, entity_type, entity_id)
            if not result.get('ok'):
                _queue_render_retry(entity_type, entity_id, result.get('error', ''))
                return {'ok': True, 'render_pending': True, 'render_error': result.get('error')}
            return {'ok': True, 'rendered': result.get('path')}
        finally:
            conn.close()
    except Exception as e:
        _queue_render_retry(entity_type, entity_id, str(e))
        return {'ok': True, 'render_pending': True, 'render_error': str(e)}


def _queue_render_retry(entity_type, entity_id, error):
    """将渲染失败记录到重试队列。"""
    try:
        conn = _log_conn()
        try:
            conn.execute('''CREATE TABLE IF NOT EXISTS render_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                error TEXT DEFAULT '',
                retry_count INTEGER DEFAULT 0,
                created_at INTEGER NOT NULL,
                last_retry_at INTEGER
            )''')
            conn.execute(
                'INSERT INTO render_queue(entity_type, entity_id, error, created_at) VALUES(?,?,?,?)',
                (entity_type, entity_id, error, int(time.time()))
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def _process_render_queue(max_retries=3):
    """处理渲染重试队列：重试 → 成功删除 / 超上限标记死信。

    策略：
    - retry_count < max_retries: 重试，成功则删除记录，失败则 retry_count+1
    - retry_count >= max_retries: 标记为死信（error 加前缀），保留记录供人工排查
    """
    try:
        import renderer
        wb_conn = _wb_conn()
        log_conn = _log_conn()
        try:
            rows = log_conn.execute(
                'SELECT id, entity_type, entity_id, retry_count FROM render_queue ORDER BY created_at'
            ).fetchall()
            for row in rows:
                qid, etype, eid, rc = row['id'], row['entity_type'], row['entity_id'], row['retry_count']
                if rc >= max_retries:
                    # 标记死信：error 加前缀，不再重试
                    log_conn.execute(
                        "UPDATE render_queue SET error = '[DEAD] ' || error WHERE id = ?",
                        (qid,)
                    )
                    log_conn.commit()
                    continue
                # 尝试重试
                result = renderer.render_entity(wb_conn, etype, eid)
                if result.get('ok'):
                    # 成功：删除队列记录
                    log_conn.execute('DELETE FROM render_queue WHERE id = ?', (qid,))
                else:
                    # 失败：更新重试计数
                    log_conn.execute(
                        'UPDATE render_queue SET retry_count = retry_count + 1, last_retry_at = ?, error = ? WHERE id = ?',
                        (int(time.time()), result.get('error', ''), qid)
                    )
                log_conn.commit()
        finally:
            wb_conn.close()
            log_conn.close()
    except Exception:
        pass


# ─── 校验 ─────────────────────────────────────────────────────

class ValidationError(Exception):
    pass


def _validate_path(path):
    """校验路径格式，返回 (entity_type, display_name, project_name)。

    UUID 主键后，路径中的名字是显示名（title/name），不是 DB 主键。
    调用方需通过 _resolve_entity_id 解析为 UUID。
    """
    m = TASK_RE.match(path or '')
    if m:
        return 'task', m.group(2), m.group(1)  # title, project_name
    m = PROJ_RE.match(path or '')
    if m:
        return 'project', m.group(1), m.group(1)  # name, name
    raise ValidationError(f'invalid path: {path[:120]}')


def _resolve_entity_id(conn, entity_type, display_name, project_name=None):
    """将路径中的显示名解析为 DB 中的真实 UUID。

    优先级：id（UUID 匹配）> title/name（显示名匹配）
    """
    if entity_type == 'task':
        # 先按 id 查（UUID）
        row = conn.execute('SELECT id FROM tasks WHERE id=?', (display_name,)).fetchone()
        if row:
            return row['id']
        # 再按 title + project 查
        if project_name:
            row = conn.execute(
                'SELECT t.id FROM tasks t JOIN projects p ON t.project_id = p.id WHERE t.title=? AND p.name=?',
                (display_name, project_name)
            ).fetchone()
            if row:
                return row['id']
        # 最后按 title 全局查
        row = conn.execute('SELECT id FROM tasks WHERE title=?', (display_name,)).fetchone()
        if row:
            return row['id']
    elif entity_type == 'project':
        # 先按 id 查（UUID）
        row = conn.execute('SELECT id FROM projects WHERE id=?', (display_name,)).fetchone()
        if row:
            return row['id']
        # 再按 name 查
        row = conn.execute('SELECT id FROM projects WHERE name=?', (display_name,)).fetchone()
        if row:
            return row['id']
    return None


def _resolve_task_id(conn, path_id):
    """将路径中的任务名解析为 DB 中的真实 id。

    路径中的名字可能是 id 也可能是 title（任务被重命名后两者分叉）。
    先按 id 查，找不到则按 title 查。
    """
    row = conn.execute('SELECT id FROM tasks WHERE id=?', (path_id,)).fetchone()
    if row:
        return row['id']
    row = conn.execute('SELECT id FROM tasks WHERE title=?', (path_id,)).fetchone()
    if row:
        return row['id']
    return None


def _validate_field(entity_type, field):
    """校验字段白名单。"""
    fields = TASK_FIELDS if entity_type == 'task' else PROJ_FIELDS
    if field not in fields:
        raise ValidationError(f'field {field} not allowed on {entity_type}')


def _validate_status(entity_type, value):
    """校验状态枚举值。"""
    valid = VALID_TASK_STATUSES if entity_type == 'task' else VALID_PROJECT_STATUSES
    if value and value not in valid:
        raise ValidationError(f'invalid status: {value}')


def _validate_priority(value):
    """校验优先级枚举值。"""
    if value and value not in VALID_PRIORITIES:
        raise ValidationError(f'invalid priority: {value}')


# 标题/目录名安全校验：禁止 shell 特殊字符与路径分隔符（防 osascript 注入 + 路径穿越）
# 覆盖场景：标题可能由 Agent 生成（原则5：AI 一等写入者），LLM 输出存在被诱导出特殊字符的现实概率
UNSAFE_NAME_CHARS = set('/\\"\'`;$(){}[]|&<>!\n\r')
UNSAFE_NAME_PATTERN = re.compile(r'\.\.')


def _validate_safe_name(name, field_name='name'):
    """校验名称/标题对 shell 与文件系统安全。

    - 禁止路径分隔符与 shell 元字符（osascript do shell script 拼接注入面）
    - 禁止 '..'（路径穿越）
    - 禁止空串与超长
    """
    if not name or not str(name).strip():
        raise ValidationError(f"'{field_name}' cannot be empty")
    name = str(name)
    if len(name) > 200:
        raise ValidationError(f"'{field_name}' exceeds 200 characters")
    bad = sorted({c for c in name if c in UNSAFE_NAME_CHARS})
    if bad:
        raise ValidationError(f"'{field_name}' contains unsafe characters: {' '.join(bad)}")
    if UNSAFE_NAME_PATTERN.search(name):
        raise ValidationError(f"'{field_name}' contains path traversal '..'")
    return name.strip()


def _get_entity(conn, entity_type, entity_id):
    """获取实体行，不存在返回 None。

    task 类型时支持 id 或 title 查找（任务重命名后 id 与 title 分叉，
    路径中的名字可能是 title）。
    """
    table = 'tasks' if entity_type == 'task' else 'projects'
    row = conn.execute(f'SELECT * FROM {table} WHERE id=?', (entity_id,)).fetchone()
    if row or entity_type != 'task':
        return row
    # task fallback: 按 title 查
    return conn.execute('SELECT * FROM tasks WHERE title=?', (entity_id,)).fetchone()


def _bump_version(conn, entity_type, entity_id, changed_by=''):
    """版本号 +1，返回新版本号。"""
    table = 'tasks' if entity_type == 'task' else 'projects'
    row = conn.execute(f'SELECT version FROM {table} WHERE id=?', (entity_id,)).fetchone()
    old_v = (row['version'] or 1) if row else 1
    new_v = old_v + 1
    conn.execute(f'UPDATE {table} SET version=?, updated_at=? WHERE id=?', (new_v, int(time.time()), entity_id))
    _log_change(entity_type, entity_id, 'version', old_v, new_v, changed_by)
    return new_v


# ─── 写操作实现 ───────────────────────────────────────────────

def set_property(path, field, value, if_version=None, changed_by=''):
    """设置 frontmatter 属性（DB 先行）。
    
    Args:
        path: 实体路径
        field: 字段名
        value: 新值
        if_version: 乐观锁版本号
        changed_by: 变更来源
    
    Returns:
        dict: {'ok': True, 'version': int, 'db_first': True} 或 {'ok': False, 'error': str}
    """
    try:
        entity_type, entity_id, project_id = _validate_path(path)
        _validate_field(entity_type, field)
        if field == 'status':
            _validate_status(entity_type, value)
        if field == 'priority':
            _validate_priority(value)
        # 安全校验：title（任务）/name（项目）会进入文件路径与 shell 命令（osascript 渲染/删除），
        # set_property 是通用入口（含 TaskDetailPage 行内编辑），不能指望调用方走专用入口
        if field in ('title', 'name'):
            _validate_safe_name(value, field)
        
        conn = _wb_conn()
        try:
            # 解析显示名为 UUID
            resolved_id = _resolve_entity_id(conn, entity_type, entity_id, project_id)
            if not resolved_id:
                return {'ok': False, 'error': f'{entity_type} not found: {entity_id}'}
            entity_id = resolved_id
            
            # 获取当前行
            table = 'tasks' if entity_type == 'task' else 'projects'
            row = conn.execute(f'SELECT * FROM {table} WHERE id=?', (entity_id,)).fetchone()
            if not row:
                return {'ok': False, 'error': f'{entity_type} not found: {entity_id}'}
            if if_version is not None and (row['version'] or 1) != int(if_version):
                return {'ok': False, 'error': 'VERSION_CONFLICT', 'current_version': row['version'] or 1}
            
            old = row[field]
            # 日期字段：TEXT → INTEGER 转换
            if field in ('start', 'due', 'complete') and isinstance(value, str):
                value = _date_to_ts(value)
            if old == value:
                return {'ok': True, 'unchanged': True, 'db_first': True}
            
            table = 'tasks' if entity_type == 'task' else 'projects'
            conn.execute(f'UPDATE {table} SET {field}=? WHERE id=?', (value, entity_id))
            _log_change(entity_type, entity_id, field, old, value, changed_by)
            
            # Done/Dropped 联动 complete（存 INTEGER 时间戳，与主字段类型转换一致）
            if field == 'status' and value in ('Done', 'Dropped') and not row['complete']:
                today_ts = _date_to_ts(time.strftime('%Y-%m-%d'))
                conn.execute(f'UPDATE {table} SET complete=? WHERE id=?', (today_ts, entity_id))
                _log_change(entity_type, entity_id, 'complete', row['complete'], today_ts, changed_by)
            
            v = _bump_version(conn, entity_type, entity_id, changed_by)
            conn.commit()
            
            render_result = _trigger_render(entity_type, entity_id)
            return {'ok': True, 'version': v, 'db_first': True, **render_result}
        finally:
            conn.close()
    except ValidationError as e:
        return {'ok': False, 'error': str(e)}
    except Exception as e:
        return {'ok': False, 'error': f'{type(e).__name__}: {e}'}


def update_section(path, section, text, if_version=None, changed_by=''):
    """更新文档区段（DB 先行）。
    
    Args:
        path: 实体路径
        section: 区段名（目标/任务详情/验收标准/项目背景/项目目标）
        text: 新内容
        if_version: 乐观锁版本号
        changed_by: 变更来源
    
    Returns:
        dict: {'ok': True, 'version': int, 'db_first': True} 或 {'ok': False, 'error': str}
    """
    try:
        entity_type, entity_id, project_id = _validate_path(path)
        field = SECTION_FIELD.get(section)
        if not field:
            return {'ok': False, 'error': f'unknown section: {section}'}
        
        conn = _wb_conn()
        try:
            # 解析显示名为 UUID
            resolved_id = _resolve_entity_id(conn, entity_type, entity_id, project_id)
            if not resolved_id:
                return {'ok': False, 'error': f'{entity_type} not found: {entity_id}'}
            entity_id = resolved_id
            
            # 获取当前行用于版本校验和旧值记录
            table = 'tasks' if entity_type == 'task' else 'projects'
            row = conn.execute(f'SELECT * FROM {table} WHERE id=?', (entity_id,)).fetchone()
            if not row:
                return {'ok': False, 'error': f'{entity_type} not found: {entity_id}'}
            if if_version is not None and (row['version'] or 1) != int(if_version):
                return {'ok': False, 'error': 'VERSION_CONFLICT', 'current_version': row['version'] or 1}
            
            old = row[field]
            conn.execute(f'UPDATE {table} SET {field}=? WHERE id=?', (text, entity_id))
            _log_change(entity_type, entity_id, field, old, text, changed_by)
            v = _bump_version(conn, entity_type, entity_id, changed_by)
            conn.commit()
            
            render_result = _trigger_render(entity_type, entity_id)
            return {'ok': True, 'version': v, 'db_first': True, **render_result}
        finally:
            conn.close()
    except ValidationError as e:
        return {'ok': False, 'error': str(e)}
    except Exception as e:
        return {'ok': False, 'error': f'{type(e).__name__}: {e}'}


def set_body(path, text, if_version=None, changed_by=''):
    """整段替换任务详情（body）。"""
    return update_section(path, '任务详情', text, if_version, changed_by)


def toggle_ac(path, idx, changed_by=''):
    """验收标准勾选态轮转 [ ]→[x]→[-]→[ ]。
    
    Args:
        path: 任务路径
        idx: 验收标准索引
        changed_by: 变更来源
    
    Returns:
        dict: {'ok': True, 'version': int, 'db_first': True} 或 {'ok': False, 'error': str}
    """
    try:
        entity_type, entity_id, project_id = _validate_path(path)
        if entity_type != 'task':
            return {'ok': False, 'error': 'toggle_ac requires task path'}
        
        conn = _wb_conn()
        try:
            # 解析显示名为 UUID
            resolved_id = _resolve_entity_id(conn, 'task', entity_id, project_id)
            if not resolved_id:
                return {'ok': False, 'error': f'task not found: {entity_id}'}
            entity_id = resolved_id
            
            # 获取当前行
            row = conn.execute('SELECT * FROM tasks WHERE id=?', (entity_id,)).fetchone()
            if not row:
                return {'ok': False, 'error': f'task not found: {entity_id}'}
            
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
            conn.execute('UPDATE tasks SET acceptance=? WHERE id=?', (new_ac, entity_id))
            _log_change('task', entity_id, 'acceptance', row['acceptance'], new_ac, changed_by)
            v = _bump_version(conn, 'task', entity_id, changed_by)
            conn.commit()
            
            render_result = _trigger_render('task', entity_id)
            return {'ok': True, 'version': v, 'db_first': True, **render_result}
        finally:
            conn.close()
    except ValidationError as e:
        return {'ok': False, 'error': str(e)}
    except Exception as e:
        return {'ok': False, 'error': f'{type(e).__name__}: {e}'}


def add_log(path, text, changed_by=''):
    """添加推进记录（YAML 条目）。
    
    Args:
        path: 任务路径
        text: YAML 条目文本（以 '- date:' 开头）
        changed_by: 变更来源
    
    Returns:
        dict: {'ok': True, 'version': int, 'db_first': True} 或 {'ok': False, 'error': str}
    """
    try:
        entity_type, entity_id, project_id = _validate_path(path)
        if entity_type != 'task':
            return {'ok': False, 'error': 'add_log requires task path'}
        
        # 解析 YAML 条目
        entry = _parse_yaml_entry(text)
        if not entry['date']:
            return {'ok': False, 'error': 'invalid log entry: missing date'}
        
        # 校验 sessions 存在性
        from db_read import _conn as read_conn
        sids = [s['sid'] for s in entry['sessions'] if s.get('sid')]
        if sids:
            dead = _validate_sids(sids)
            if dead:
                return {'ok': False, 'error': f'INVALID_SESSION_IDS: {dead}'}
        
        conn = _wb_conn()
        try:
            # 解析显示名为 UUID
            entity_id = _resolve_entity_id(conn, 'task', entity_id, project_id)
            if not entity_id:
                return {'ok': False, 'error': f'task not found: {entity_id}'}
            
            # 插入 log_entries
            entry_id = entry.get('id') or f"{int(time.time())}"
            conn.execute(
                'INSERT INTO log_entries(id, task_id, date, type, summary, window, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)',
                (entry_id, entity_id, entry['date'], entry['type'], entry['summary'], entry.get('window', ''),
                 int(time.time()), int(time.time()))
            )
            
            # 插入 log_sessions
            for s in entry['sessions']:
                conn.execute(
                    'INSERT OR IGNORE INTO log_sessions(entry_id, sid, source) VALUES(?,?,?)',
                    (entry_id, s['sid'], s.get('source', ''))
                )
            
            # 插入 log_detail
            for kind in ('outputs', 'risks', 'pending'):
                for i, item in enumerate(entry[kind]):
                    conn.execute(
                        'INSERT INTO log_detail(entry_id, kind, seq, text) VALUES(?,?,?,?)',
                        (entry_id, kind, i, item)
                    )
            for i, d in enumerate(entry['decisions']):
                conn.execute(
                    'INSERT INTO log_detail(entry_id, kind, seq, text, by) VALUES(?,?,?,?,?)',
                    (entry_id, 'decisions', i, d.get('desc', ''), d.get('by', ''))
                )
            
            _log_change('task', entity_id, 'log_entries', None, entry_id, changed_by)
            v = _bump_version(conn, 'task', entity_id, changed_by)
            conn.commit()
            
            render_result = _trigger_render('task', entity_id)
            return {'ok': True, 'version': v, 'entry_id': entry_id, 'db_first': True, **render_result}
        finally:
            conn.close()
    except ValidationError as e:
        return {'ok': False, 'error': str(e)}
    except Exception as e:
        return {'ok': False, 'error': f'{type(e).__name__}: {e}'}


def _parse_yaml_entry(text):
    """解析 YAML 推进记录条目。"""
    entry = {'date': '', 'id': '', 'type': 'manual', 'summary': '', 'window': '',
             'sessions': [], 'outputs': [], 'risks': [], 'pending': [], 'decisions': []}
    
    lines = text.split('\n')
    cur_field = ''
    cur_sub = None
    in_block_summary = False
    block_lines = []
    
    for line in lines:
        # 块量 summary 收尾
        if in_block_summary:
            if re.match(r'^\s{4,}', line) or not line.strip():
                block_lines.append(line.replace(r'^\s{4}', '', 1) if re.match(r'^\s{4}', line) else line)
                continue
            else:
                in_block_summary = False
                entry['summary'] = '\n'.join(block_lines).rstrip('\n')
                block_lines = []
        
        m = re.match(r'^-\s+date:\s*(.+)', line)
        if m:
            entry['date'] = m.group(1).strip()
            cur_field = ''
            continue
        m = re.match(r'^\s+id:\s*(.+)', line)
        if m:
            entry['id'] = m.group(1).strip()
            cur_field = ''
            continue
        m = re.match(r'^\s+type:\s*(.+)', line)
        if m:
            entry['type'] = m.group(1).strip()
            cur_field = ''
            continue
        m = re.match(r'^\s+summary:\s*\|\s*$', line)
        if m:
            in_block_summary = True
            block_lines = []
            cur_field = ''
            continue
        m = re.match(r'^\s+summary:\s*(.+)', line)
        if m:
            entry['summary'] = m.group(1).strip()
            cur_field = ''
            continue
        m = re.match(r'^\s+window:\s*(.+)', line)
        if m:
            entry['window'] = m.group(1).strip().strip('"')
            cur_field = ''
            continue
        
        if re.match(r'^\s+sessions:', line):
            cur_field = 'sessions'
            cur_sub = None
            continue
        if re.match(r'^\s+outputs:', line) or re.match(r'^\s+deliverables:', line):
            cur_field = 'outputs'
            continue
        if re.match(r'^\s+decisions:', line):
            cur_field = 'decisions'
            cur_sub = None
            continue
        if re.match(r'^\s+risks:', line):
            cur_field = 'risks'
            continue
        if re.match(r'^\s+pending:', line):
            cur_field = 'pending'
            continue
        
        if cur_field == 'sessions':
            m = re.match(r'^\s+-\s+id:\s*(.+)', line)
            if m:
                cur_sub = {'sid': m.group(1).strip(), 'source': ''}
                entry['sessions'].append(cur_sub)
                continue
            m = re.match(r'^\s+source:\s*(.+)', line)
            if m and cur_sub:
                cur_sub['source'] = m.group(1).strip()
                continue
        
        if cur_field in ('outputs', 'risks', 'pending'):
            m = re.match(r'^\s+-\s+(.+)', line)
            if m:
                entry[cur_field].append(m.group(1).strip())
                continue
        
        if cur_field == 'decisions':
            m = re.match(r'^\s+-\s+desc:\s*(.+)', line)
            if m:
                cur_sub = {'desc': m.group(1).strip(), 'by': ''}
                entry['decisions'].append(cur_sub)
                continue
            m = re.match(r'^\s+by:\s*(.+)', line)
            if m and cur_sub:
                cur_sub['by'] = m.group(1).strip()
                continue
    
    # 收尾块量 summary
    if in_block_summary:
        entry['summary'] = '\n'.join(block_lines).rstrip('\n')
    
    return entry


def _validate_sids(sids, max_retries=3):
    """校验 session ID 是否真实存在于 state.db。

    对于刚创建的 session，state.db 可能还没落库，支持重试。
    """
    if not sids:
        return None
    state_db = os.path.join(os.path.expanduser('~'), '.hermes/profiles/business_analysis/state.db')
    if not os.path.exists(state_db):
        return None  # state.db 不存在，跳过校验
    
    dead = None
    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(state_db)
            placeholders = ','.join('?' for _ in sids)
            rows = conn.execute(f'SELECT id FROM sessions WHERE id IN ({placeholders})', list(sids)).fetchall()
            conn.close()
            live = {r[0] for r in rows}
            dead = [s for s in sids if s not in live]
            if not dead:
                return None  # 全部有效
            if attempt < max_retries - 1:
                time.sleep(0.1 * (attempt + 1))  # 递增延迟：100ms, 200ms, 300ms
        except Exception:
            return None
    return dead  # 重试后仍无效


def link_session(task_path=None, project_path=None, sid='', source='plugin', changed_by='', skip_validation=False):
    """Session 关联到任务/项目（显式绑定）。

    Args:
        skip_validation: 跳过 session 存在性校验（用于刚创建的 session）
    """
    if not sid:
        return {'ok': False, 'error': 'no sid'}
    
    sids = [s.strip() for s in str(sid).split(',') if s.strip()]
    if not sids:
        return {'ok': False, 'error': 'no sid'}
    
    if task_path:
        m = TASK_RE.match(task_path)
        if not m:
            return {'ok': False, 'error': f'bad task_path: {task_path[:120]}'}
        entity_type, entity_id = 'task', m.group(2)  # title
        project_name = m.group(1)
    elif project_path:
        m = PROJ_RE.match(project_path)
        if not m:
            return {'ok': False, 'error': f'bad project_path: {project_path[:120]}'}
        entity_type, entity_id = 'project', m.group(1)  # name
        project_name = None
    else:
        return {'ok': False, 'error': 'task_path or project_path required'}
    
    if not skip_validation:
        dead = _validate_sids(sids)
        if dead:
            return {'ok': False, 'error': 'INVALID_SESSION_IDS', 'invalid_sids': dead}
    
    table = 'task_sessions' if entity_type == 'task' else 'project_sessions'
    col = 'task_id' if entity_type == 'task' else 'project_id'
    
    conn = _wb_conn()
    try:
        # 解析显示名为 UUID
        resolved_id = _resolve_entity_id(conn, entity_type, entity_id, project_name)
        if not resolved_id:
            return {'ok': False, 'error': f'{entity_type} not found: {entity_id}'}
        entity_id = resolved_id
        
        now = int(time.time())
        added = []
        for sid_item in sids:
            cur = conn.execute(
                f'INSERT OR IGNORE INTO {table}({col}, sid, linked_at, source) VALUES(?,?,?,?)',
                (entity_id, sid_item, now, source)
            )
            if cur.rowcount:
                added.append(sid_item)
        
        if added:
            _log_change(entity_type, entity_id, 'sessions', None, ','.join(added), changed_by)
        
        conn.commit()
        _trigger_render(entity_type, entity_id)
        return {'ok': True, 'linked': added, 'skipped': len(sids) - len(added)}
    finally:
        conn.close()


def create_task(project_id, title, goal='', task_detail='', acceptance='', priority='p2', status='open', start='', due='', handler='', repeat_cfg=None, changed_by=''):
    """创建任务（DB 先行）。
    
    Args:
        project_id: 项目 ID
        title: 任务标题
        goal: 目标
        task_detail: 任务详情（body）
        acceptance: 验收标准文本
        priority: 优先级（p0/p1/p2）
        status: 状态
        start: 开始日期（YYYY-MM-DD）
        due: 截止日期（YYYY-MM-DD）
        handler: 处理人
        repeat_cfg: 重复配置 dict {mode, unit, every, day, anchor}
        changed_by: 变更来源
    
    Returns:
        dict: {'ok': True, 'task_id': str} 或 {'ok': False, 'error': str}
    """
    try:
        # 安全校验：标题将进入文件路径与 shell 命令（osascript），必须防注入
        _validate_safe_name(title, 'title')
        # 校验项目存在（支持 id 或 name 双路查找，与 _get_entity 一致）
        conn = _wb_conn()
        try:
            proj = conn.execute('SELECT id FROM projects WHERE id=?', (project_id,)).fetchone()
            if not proj:
                proj = conn.execute('SELECT id FROM projects WHERE name=?', (project_id,)).fetchone()
            if not proj:
                return {'ok': False, 'error': f'项目不存在: {project_id}'}
            project_id = proj['id']  # 归一化为真实 id

            # 生成 UUID 主键（与 title 解耦）
            import uuid
            task_id = uuid.uuid4().hex[:12]

            # 日期转换
            start_ts = _date_to_ts(start) if start else None
            due_ts = _date_to_ts(due) if due else None
            
            # 重复配置
            rep_mode = repeat_cfg.get('mode', '') if repeat_cfg else ''
            rep_unit = repeat_cfg.get('unit', '') if repeat_cfg else ''
            rep_every = repeat_cfg.get('every', 1) if repeat_cfg else None
            rep_day = repeat_cfg.get('day') if repeat_cfg else None
            rep_anchor = repeat_cfg.get('anchor', '') if repeat_cfg else ''
            
            now = int(time.time())
            conn.execute('''INSERT INTO tasks(
                id, project_id, title, status, priority, handler,
                start, due, complete, version,
                goal, body, acceptance,
                repeat_mode, repeat_unit, repeat_every, repeat_day, repeat_anchor,
                created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                task_id, project_id, title, status, priority, handler,
                start_ts, due_ts, None, 1,
                goal, task_detail, acceptance,
                rep_mode, rep_unit, rep_every, rep_day, rep_anchor,
                now, now
            ))
            _log_change('task', task_id, 'created', None, task_id, changed_by)

            # documents 登记：任务创建时一次性写入文档映射（与项目创建时的登记一致）
            # 路径 = 项目目录（=项目 name，强制一致原则）/tasks/任务-<title>.md
            proj_name_row = conn.execute('SELECT name FROM projects WHERE id=?', (project_id,)).fetchone()
            proj_name = proj_name_row['name'] if proj_name_row else project_id
            conn.execute('''INSERT OR REPLACE INTO documents(entity_type, entity_id, doc_type, path, updated_at)
                VALUES(?,?,?,?,?)''', ('task', task_id, 'main', f'{PROOT}/{proj_name}/tasks/任务-{title}.md', now))
            conn.commit()
            
            # 触发渲染
            _trigger_render('task', task_id)
            
            _log_op(changed_by or 'plugin', 'create_task', 'task', task_id, f'创建任务「{title}」')
            return {'ok': True, 'task_id': task_id}
        finally:
            conn.close()
    except Exception as e:
        return {'ok': False, 'error': f'{type(e).__name__}: {e}'}


def delete_task(path, changed_by=''):
    """删除任务（DB 与文件剥离：各自独立删除，互不阻塞）。

    Args:
        path: 任务路径
        changed_by: 变更来源

    Returns:
        dict: {'ok': True, 'db_deleted': bool, 'file_deleted': bool}
              或 {'ok': False, 'error': str}（仅当路径解析失败时）
    """
    try:
        entity_type, entity_id, project_id = _validate_path(path)
        if entity_type != 'task':
            return {'ok': False, 'error': 'delete_task requires task path'}

        db_deleted = False
        file_deleted = False
        db_error = None
        file_error = None

        # ─── DB 删除（独立事务）───────────────────────────
        conn = _wb_conn()
        try:
            row = _get_entity(conn, 'task', entity_id)
            if row:
                real_id = row['id']  # 归一化为真实 UUID，后续删除用 real_id
                title = row['title'] if hasattr(row, 'keys') else entity_id
                conn.execute('DELETE FROM task_sessions WHERE task_id=?', (real_id,))
                conn.execute('DELETE FROM log_sessions WHERE entry_id IN (SELECT id FROM log_entries WHERE task_id=?)', (real_id,))
                conn.execute('DELETE FROM log_detail WHERE entry_id IN (SELECT id FROM log_entries WHERE task_id=?)', (real_id,))
                conn.execute('DELETE FROM log_entries WHERE task_id=?', (real_id,))
                conn.execute('DELETE FROM documents WHERE entity_type=? AND entity_id=?', ('task', real_id))
                conn.execute('DELETE FROM tasks WHERE id=?', (real_id,))
                _log_change('task', real_id, 'deleted', title, None, changed_by)
                conn.commit()
                db_deleted = True
        except Exception as e:
            db_error = f'{type(e).__name__}: {e}'
        finally:
            conn.close()

        # ─── 文件删除（独立操作）───────────────────────────
        file_path = os.path.join(VAULT, path)
        if os.path.exists(file_path):
            try:
                os.unlink(file_path)
                file_deleted = True
            except Exception as e:
                file_error = f'{type(e).__name__}: {e}'

        # ─── 结果汇总 ────────────────────────────────────
        if db_error or file_error:
            parts = []
            if db_error:
                parts.append(f'DB: {db_error}')
            if file_error:
                parts.append(f'file: {file_error}')
            return {'ok': False, 'error': '; '.join(parts), 'db_deleted': db_deleted, 'file_deleted': file_deleted}

        if not db_deleted and not file_deleted:
            return {'ok': False, 'error': f'task not found in DB and file not exists: {entity_id}'}

        _log_op(changed_by or 'plugin', 'delete_task', 'task', entity_id,
                f'删除任务「{entity_id}」（db={db_deleted}, file={file_deleted}）')
        return {'ok': True, 'db_deleted': db_deleted, 'file_deleted': file_deleted}
    except Exception as e:
        return {'ok': False, 'error': f'{type(e).__name__}: {e}'}


def rename_task(path, new_title, changed_by=''):
    """重命名任务（DB 先行，文件名同步更新）。
    
    Args:
        path: 任务路径
        new_title: 新标题
        changed_by: 变更来源
    
    Returns:
        dict: {'ok': True, 'new_path': str} 或 {'ok': False, 'error': str}
    """
    try:
        entity_type, entity_id, project_id = _validate_path(path)
        if entity_type != 'task':
            return {'ok': False, 'error': 'rename_task requires task path'}
        # 安全校验：新标题将进入文件名与 shell 命令
        _validate_safe_name(new_title, 'new_title')
        
        conn = _wb_conn()
        try:
            row = _get_entity(conn, 'task', entity_id)
            if not row:
                return {'ok': False, 'error': f'task not found: {entity_id}'}
            entity_id = row['id']  # 使用真实 UUID，不是路径里的 title
            
            old_title = row['title']
            if old_title == new_title:
                return {'ok': True, 'unchanged': True, 'db_first': True}
            
            # 更新 DB（只更新 title，id 保持 UUID 不变）
            conn.execute('UPDATE tasks SET title=? WHERE id=?', (new_title, entity_id))
            _log_change('task', entity_id, 'title', old_title, new_title, changed_by)

            # documents 映射同步更新（title 变 → 文件名变 → path 变）
            proj_row2 = conn.execute('SELECT name FROM projects WHERE id=?', (row['project_id'],)).fetchone()
            proj_name2 = proj_row2['name'] if proj_row2 else row['project_id']
            new_doc_path = f'{PROOT}/{proj_name2}/tasks/任务-{new_title}.md'
            conn.execute('UPDATE documents SET path=?, updated_at=? WHERE entity_type=? AND entity_id=?',
                         (new_doc_path, int(time.time()), 'task', entity_id))
            v = _bump_version(conn, 'task', entity_id, changed_by)
            conn.commit()
            
            # 触发渲染（新标题写入新文件，旧文件删除）
            _trigger_render('task', entity_id)
            
            # 删除旧文件
            old_file = os.path.join(VAULT, path)
            if os.path.exists(old_file):
                try:
                    os.unlink(old_file)
                except Exception:
                    pass
            
            new_path = f'{PROOT}/{proj_name2}/tasks/任务-{new_title}.md'
            _log_op(changed_by or 'plugin', 'rename_task', 'task', entity_id, f'重命名：{old_title} → {new_title}')
            return {'ok': True, 'version': v, 'new_path': new_path, 'db_first': True}
        finally:
            conn.close()
    except Exception as e:
        return {'ok': False, 'error': f'{type(e).__name__}: {e}'}


def repeat_next(path, changed_by=''):
    """按 repeat 规则生成下一个周期任务。
    
    Args:
        path: 任务路径
        changed_by: 变更来源
    
    Returns:
        dict: {'ok': True, 'title': str, 'due': str} 或 {'ok': False, 'error': str}
    """
    try:
        entity_type, entity_id, project_id = _validate_path(path)
        if entity_type != 'task':
            return {'ok': False, 'error': 'repeat_next requires task path'}
        
        conn = _wb_conn()
        try:
            row = _get_entity(conn, 'task', entity_id)
            if not row:
                return {'ok': False, 'error': f'task not found: {entity_id}'}

            # project_id 归一化：路径里的是目录名（=name），外键要求 UUID，用任务行的真实 project_id
            project_id = row['project_id']

            # 校验重复配置
            if row['repeat_mode'] != 'fixed' or not row['repeat_unit'] or not row['repeat_anchor']:
                return {'ok': False, 'error': 'NO_REPEAT'}
            
            # 计算下一个周期
            from datetime import datetime, timedelta
            import calendar
            anchor = datetime.fromtimestamp(row['repeat_anchor']) if isinstance(row['repeat_anchor'], int) else datetime.strptime(row['repeat_anchor'], '%Y-%m-%d')
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            every = row['repeat_every'] or 1
            unit = row['repeat_unit']
            day = row['repeat_day'] or 1

            # 防御：every 必须为正整数，否则 while 倒退死循环（负数）或永不前进（0）
            try:
                every = int(every)
            except (TypeError, ValueError):
                return {'ok': False, 'error': f'invalid repeat_every: {every}'}
            if every < 1:
                return {'ok': False, 'error': f'invalid repeat_every: {every}（必须为正整数）'}

            def advance(d):
                x = d
                if unit == 'day':
                    x = d + timedelta(days=every)
                    while x <= today or x <= d:
                        x += timedelta(days=every)
                elif unit == 'week':
                    # UI 编号 周一=1…周日=7，Python weekday() 周一=0…周日=6，需 -1 对齐
                    wd = (day - 1) if 1 <= day <= 7 else 0
                    days_ahead = wd - x.weekday()
                    if days_ahead <= 0:
                        days_ahead += 7
                    x = x + timedelta(days=days_ahead)
                    while x <= today or x <= d:
                        x += timedelta(weeks=every)
                elif unit == 'month':
                    dd = day if 1 <= day <= 31 else 1
                    # 小月兜底：dd 超当月天数时落当月最后一天（replace(day=dd) 会 ValueError）
                    def _clamp(dt, daynum):
                        last = calendar.monthrange(dt.year, dt.month)[1]
                        return dt.replace(day=min(daynum, last))
                    x = _clamp(x, dd)
                    # every 作为月步长生效：每 N 月
                    def _add_months(dt, n):
                        m = dt.month - 1 + n
                        y = dt.year + m // 12
                        m = m % 12 + 1
                        last = calendar.monthrange(y, m)[1]
                        return datetime(y, m, min(dt.day, last))
                    while x <= today or x <= d:
                        x = _add_months(x, every)
                        x = _clamp(x, dd)
                return x
            
            next_due = advance(anchor)
            next_due_str = next_due.strftime('%Y-%m-%d')
            
            # 生成新任务标题（去日期后缀）
            base_title = re.sub(r'\s+\d{4}-\d{2}-\d{2}\s*$', '', row['title']).strip()
            new_title = f'{base_title} {next_due_str}'
            
            # 检查是否已存在（按 title + project 查，允许同名任务在不同项目）
            existing = conn.execute('SELECT id FROM tasks WHERE project_id=? AND title=?', (project_id, new_title)).fetchone()
            if existing:
                return {'ok': False, 'error': 'EXISTS'}

            # 生成 UUID 主键（与 title 解耦）
            import uuid
            new_task_id = uuid.uuid4().hex[:12]

            # 创建新任务（复制原任务字段，重置状态）
            # 判重竞态：并发触发时 SELECT 后 INSERT 之间无事务，UNIQUE 兜底会抛 IntegrityError，
            # 捕获后转为 'EXISTS' 语义（前端 plugin.js 专门处理该错误码）
            now = int(time.time())
            try:
                conn.execute('''INSERT INTO tasks(
                    id, project_id, title, status, priority, handler,
                    start, due, complete, version,
                    goal, body, acceptance,
                    repeat_mode, repeat_unit, repeat_every, repeat_day, repeat_anchor,
                    created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                    new_task_id, project_id, new_title, 'open', row['priority'], row['handler'],
                    None, _date_to_ts(next_due_str), None, 1,
                    row['goal'], row['body'], row['acceptance'],
                    row['repeat_mode'], row['repeat_unit'], row['repeat_every'], row['repeat_day'], next_due_str,
                    now, now
                ))
            except sqlite3.IntegrityError as ie:
                conn.rollback()
                if 'UNIQUE' in str(ie):
                    return {'ok': False, 'error': 'EXISTS'}
                raise
            _log_change('task', new_task_id, 'created', None, new_title, changed_by)

            # documents 登记：repeat_next 生成的周期任务同样登记（与 create_task 一致）
            rpt_proj_row = conn.execute('SELECT name FROM projects WHERE id=?', (project_id,)).fetchone()
            rpt_proj_name = rpt_proj_row['name'] if rpt_proj_row else project_id
            conn.execute('''INSERT OR REPLACE INTO documents(entity_type, entity_id, doc_type, path, updated_at)
                VALUES(?,?,?,?,?)''', ('task', new_task_id, 'main', f'{PROOT}/{rpt_proj_name}/tasks/任务-{new_title}.md', now))
            conn.commit()

            # 触发渲染
            _trigger_render('task', new_task_id)

            _log_op(changed_by or 'plugin', 'repeat_next', 'task', new_task_id, f'重复任务「{base_title}」生成下一周期')
            return {'ok': True, 'title': new_title, 'task_id': new_task_id, 'due': next_due_str}
        finally:
            conn.close()
    except Exception as e:
        return {'ok': False, 'error': f'{type(e).__name__}: {e}'}


# ─── Kanban 集成 ─────────────────────────────────────────────

def _kb_conn(board_name=None):
    """连接 kanban DB。"""
    import sys as _sys
    agent_root = os.path.join(os.path.expanduser('~'), '.hermes/hermes-agent')
    if agent_root not in _sys.path:
        _sys.path.insert(0, agent_root)
    from hermes_cli import kanban_db as kb
    return kb, kb.connect(board=board_name)


def kanban_bridge(op, spec):
    """转发 kanban 操作到 Hermes kanban DB。"""
    try:
        kb, conn = _kb_conn(board_name=spec.get('board'))
        try:
            if op == 'kanban_create':
                ws_path = spec.get('workspace_path') or None
                tid = kb.create_task(
                    conn,
                    title=spec.get('title', ''),
                    body=spec.get('body', '') or None,
                    assignee=spec.get('assignee') or None,
                    created_by='projects-workbench',
                    workspace_kind='dir' if ws_path else 'scratch',
                    workspace_path=ws_path,
                    idempotency_key=spec.get('idempotency_key'),
                )
                return {'ok': True, 'task_id': tid}
            if op == 'kanban_status':
                task = kb.get_task(conn, spec.get('task_id', ''))
                if task is None:
                    return {'ok': False, 'error': 'task not found'}
                return {
                    'ok': True,
                    'status': task.status,
                    'title': task.title,
                    'summary': (task.result or '')[:500],
                }
            if op == 'kanban_comment':
                ok = kb.add_comment(
                    conn, spec.get('task_id', ''),
                    body=spec.get('body', ''),
                    author=spec.get('author') or 'projects-workbench',
                )
                return {'ok': bool(ok), 'commented': True}
            if op == 'kanban_complete':
                ok = kb.complete_task(
                    conn, spec.get('task_id', ''),
                    summary=spec.get('summary') or None,
                    metadata=spec.get('metadata'),
                )
                return {'ok': bool(ok), 'completed': True}
            if op == 'kanban_reopen':
                ok = kb.unblock_task(conn, spec.get('task_id', ''))
                return {'ok': bool(ok), 'reopened': True}
            if op == 'kanban_worker_session':
                runs = conn.execute(
                    "SELECT metadata FROM task_runs WHERE task_id = ? AND outcome = 'completed' "
                    "ORDER BY started_at DESC LIMIT 1",
                    (spec.get('task_id', ''),),
                ).fetchall()
                for row in runs:
                    if not row or not row[0]:
                        continue
                    try:
                        md = json.loads(row[0])
                    except Exception:
                        continue
                    wsid = md.get('worker_session_id') or ''
                    if wsid:
                        return {'ok': True, 'worker_session_id': wsid}
                return {'ok': True, 'worker_session_id': ''}
            if op == 'kanban_link_session':
                stask = kb.get_task(conn, spec.get('task_id', ''))
                if not stask or not stask.workspace_path:
                    return {'ok': False, 'error': 'task not found or no workspace_path'}
                wsid = spec.get('worker_session_id', '')
                if not wsid:
                    return {'ok': False, 'error': 'no worker_session_id'}
                sdb = os.path.join(os.path.expanduser('~'), '.hermes/profiles/business_analysis/state.db')
                if not os.path.exists(sdb):
                    return {'ok': False, 'error': 'state.db not found'}
                sconn = sqlite3.connect(sdb)
                try:
                    sconn.execute("UPDATE sessions SET cwd = ? WHERE id = ?", (stask.workspace_path, wsid))
                    sconn.commit()
                    return {'ok': True, 'cwd': stask.workspace_path}
                except Exception as _e:
                    return {'ok': False, 'error': str(_e)[:200]}
                finally:
                    try: sconn.close()
                    except Exception: pass
            if op == 'kanban_dispatch':
                result = kb.dispatch_once(conn, board=spec.get('board') or 'default', max_spawn=spec.get('max', 3))
                return {'ok': True, 'spawned': len(result.spawned if hasattr(result, 'spawned') else [])}
            return {'ok': False, 'error': 'unknown kanban op: ' + op}
        finally:
            try: conn.close()
            except Exception: pass
    except Exception as e:
        return {'ok': False, 'error': str(e)[:300]}


def create_project(dir_path, project_content, agents_content, changed_by=''):
    """创建项目（DB 先行，文件由渲染器投影）。
    
    Args:
        dir_path: 项目目录路径（如 '2. Project/2.1 Project/新项目'）
        project_content: 项目说明 Markdown（用于提取字段，不直接写文件）
        agents_content: AGENTS.md 内容（用于提取字段，不直接写文件）
        changed_by: 变更来源
    
    Returns:
        dict: {'ok': True, 'project_id': str} 或 {'ok': False, 'error': str}
    """
    # 从路径提取项目名
    folder_name = dir_path.rstrip('/').split('/')[-1]

    # 安全校验：项目名将作为目录名并进入 shell 命令（osascript），必须防注入/路径穿越
    try:
        folder_name = _validate_safe_name(folder_name, 'project name')
    except ValidationError as e:
        return {'ok': False, 'error': str(e)}

    # 从 project_content 解析字段（frontmatter），提前取 title 做一致性校验
    fields = _parse_frontmatter(project_content)
    title = fields.get('title', '').strip()

    # 强制一致：目录名 == 项目显示名（单一信源，消除目录/名称分叉类问题）
    # 分叉会让 renderer（按 name 定位目录）与 delete_project（按 name 删目录）都失效
    if title and title != folder_name:
        return {'ok': False, 'error': f'目录名与项目名不一致: 目录「{folder_name}」≠ 项目「{title}」。请保持两者一致。'}
    if not title:
        # 无 title 时以目录名为准
        project_content = project_content.replace('---\n', f'---\ntitle: {folder_name}\n', 1) if 'title:' not in project_content else project_content
        fields['title'] = folder_name

    # 校验项目名称唯一性（按 name 查，id 是 UUID）
    conn = _wb_conn()
    try:
        existing = conn.execute('SELECT id FROM projects WHERE name=?', (folder_name,)).fetchone()
        if existing:
            return {'ok': False, 'error': f'项目已存在: {folder_name}'}

        # 生成 UUID 主键
        import uuid
        project_id = uuid.uuid4().hex[:12]

        # 插入 DB（id=UUID，name=目录名=显示名，强制一致后两者同一）
        now = int(time.time())
        conn.execute(
            'INSERT INTO projects(id, name, status, background, goal, created_at, updated_at, version) VALUES(?,?,?,?,?,?,?,?)',
            (project_id, folder_name, fields.get('status', 'open'),
             fields.get('background', ''), fields.get('goal', ''),
             now, now, 1)
        )
        _log_change('project', project_id, 'created', None, folder_name, changed_by)

        # documents 登记：项目创建时一次性写入骨架映射（此后不更新，仅创建时刻登记）
        # 主文档 + 5 个标准目录
        proj_rel = f'{PROOT}/{folder_name}'
        conn.execute('''INSERT OR REPLACE INTO documents(entity_type, entity_id, doc_type, path, updated_at)
            VALUES(?,?,?,?,?)''', ('project', project_id, 'main', f'{proj_rel}/项目说明-{folder_name}.md', now))
        for sub in ['raw', 'output', 'tmp', 'scripts', 'tasks']:
            conn.execute('''INSERT OR REPLACE INTO documents(entity_type, entity_id, doc_type, path, updated_at)
                VALUES(?,?,?,?,?)''', ('folder', f'{proj_rel}/{sub}', 'dir', f'{proj_rel}/{sub}', now))
        conn.commit()

        # 创建目录结构（文件系统）
        _create_project_dirs(dir_path)

        # 触发渲染（生成项目说明.md 和 AGENTS.md）
        _trigger_render('project', project_id)

        # AGENTS.md 单独写（不属于 DB 投影）
        agents_path = os.path.join(VAULT, dir_path, 'AGENTS.md')
        _write_file_direct(agents_path, agents_content)

        _log_op(changed_by or 'plugin', 'create_project', 'project', project_id, f'创建项目「{folder_name}」')

        return {'ok': True, 'project_id': project_id}
    finally:
        conn.close()


def _parse_frontmatter(content):
    """从 Markdown 内容解析 frontmatter。"""
    fields = {}
    m = re.match(r'^---\n([\s\S]*?)\n---', content)
    if m:
        for line in m.group(1).split('\n'):
            mm = re.match(r'^(\S+)\s*:\s*(.*)$', line)
            if mm:
                fields[mm.group(1)] = mm.group(2).strip().strip('"').strip("'")
    # 解析 body 区段
    bg_match = re.search(r'## 项目背景\n([\s\S]*?)(?:\n## |$)', content)
    if bg_match:
        fields['background'] = bg_match.group(1).strip()
    goal_match = re.search(r'## 项目目标\n([\s\S]*?)(?:\n## |$)', content)
    if goal_match:
        fields['goal'] = goal_match.group(1).strip()
    return fields


def _create_project_dirs(dir_path):
    """创建项目标准目录结构（统一走 osascript，与渲染/直接写文件的 TCC 绕过策略一致）。

    背景：Python 进程直接写 ~/Documents 下的 Vault 会被 macOS TCC 拦截，
    项目说明/AGENTS.md 都走 osascript do shell script；目录创建若用 os.makedirs
    会产生「DB 已 commit、目录未建成」的不一致态。此处统一改为 osascript。
    目录名已经过 _validate_safe_name 校验（无引号/分号/路径穿越），拼接安全。
    """
    full_path = os.path.join(VAULT, dir_path)
    subs = ' '.join('\\"' + full_path + '/' + sub + '\\"' for sub in ['raw', 'output', 'tmp', 'scripts', 'tasks'])
    cmd = 'mkdir -p \\"' + full_path + '\\" ' + subs + ' && touch \\"' + full_path + '/pipeline.md\\"'
    p = subprocess.run(
        ['osascript', '-e', 'do shell script "' + cmd + '"'],
        capture_output=True, timeout=30
    )
    if p.returncode != 0:
        raise RuntimeError(f'osascript mkdir failed: {p.stderr.decode()[:200]}')


def delete_project(path, changed_by=''):
    """删除项目（DB 先行，文件目录一并清理）。

    Args:
        path: 项目说明文档路径、项目目录路径、或项目 UUID
        changed_by: 变更来源

    Returns:
        dict: {'ok': True, 'deleted_tasks': int} 或 {'ok': False, 'error': str}
    """
    import shutil
    try:
        # 解析 project_id：支持 UUID 或名称
        p = (path or '').rstrip('/')
        project_id = None
        project_name = ''

        # 1. 尝试作为 UUID 直接匹配
        conn = _wb_conn()
        try:
            row = conn.execute('SELECT id, name FROM projects WHERE id=?', (p,)).fetchone()
            if row:
                project_id = row['id']
                project_name = row['name']
        finally:
            conn.close()

        # 2. 从路径提取名称，按 name 查
        if not project_id:
            if '/项目说明-' in p:
                project_name = p.split('/')[-2] if p.count('/') >= 1 else ''
            else:
                project_name = p.split('/')[-1]
            if not project_name:
                return {'ok': False, 'error': f'bad project path: {path[:120]}'}
            conn = _wb_conn()
            try:
                row = conn.execute('SELECT id, name FROM projects WHERE name=?', (project_name,)).fetchone()
                if not row:
                    return {'ok': False, 'error': f'project not found: {project_name}'}
                project_id = row['id']
                project_name = row['name']
            finally:
                conn.close()

        # 先取目录名（删 DB 前）：documents 表的项目主文档路径含真实目录名
        conn = _wb_conn()
        try:
            doc_row = conn.execute(
                "SELECT path FROM documents WHERE entity_type='project' AND entity_id=? AND doc_type='main' LIMIT 1",
                (project_id,)).fetchone()
        finally:
            conn.close()
        dir_name = project_name
        if doc_row and doc_row['path']:
            parts = doc_row['path'].split('/')
            if len(parts) >= 2:
                dir_name = parts[-2]

        # 删除 DB 记录
        conn = _wb_conn()
        try:
            # 项目下任务一并删除（含关联）
            task_ids = [r['id'] for r in conn.execute('SELECT id FROM tasks WHERE project_id=?', (project_id,)).fetchall()]
            for tid in task_ids:
                conn.execute('DELETE FROM task_sessions WHERE task_id=?', (tid,))
                conn.execute('DELETE FROM log_sessions WHERE entry_id IN (SELECT id FROM log_entries WHERE task_id=?)', (tid,))
                conn.execute('DELETE FROM log_detail WHERE entry_id IN (SELECT id FROM log_entries WHERE task_id=?)', (tid,))
                conn.execute('DELETE FROM log_entries WHERE task_id=?', (tid,))
                conn.execute('DELETE FROM documents WHERE entity_type=? AND entity_id=?', ('task', tid))
            conn.execute('DELETE FROM tasks WHERE project_id=?', (project_id,))

            # 项目自身关联
            conn.execute('DELETE FROM project_sessions WHERE project_id=?', (project_id,))
            conn.execute('DELETE FROM documents WHERE entity_type=? AND entity_id=?', ('project', project_id))
            # 清理创建时登记的 folder 骨架行（5 个标准目录），避免孤儿记录积累
            proj_rel_del = f'{PROOT}/{dir_name}'
            conn.execute("DELETE FROM documents WHERE entity_type='folder' AND entity_id LIKE ?", (f'{proj_rel_del}/%',))
            conn.execute('DELETE FROM projects WHERE id=?', (project_id,))

            _log_change('project', project_id, 'deleted', project_name, None, changed_by)
            conn.commit()
        finally:
            conn.close()

        # 删除目录（含全部文件）
        # TCC 约束：osascript do shell script 的 rm -rf 对 ~/Documents 被拦截（mkdir/cp/touch 放行），
        # 改用 AppleScript 原生 tell Finder to delete（进废纸篓，可恢复，TCC 友好）。
        proj_dir = os.path.join(VAULT, PROOT, dir_name)
        if os.path.isdir(proj_dir):
            try:
                p = subprocess.run(
                    ['osascript', '-e', 'tell application "Finder" to delete (POSIX file "' + proj_dir + '" as alias)'],
                    capture_output=True, timeout=30
                )
                if p.returncode != 0:
                    _log_op(changed_by or 'plugin', 'delete_project_dir_failed', 'project', project_id,
                            '目录删除失败(进废纸篓): ' + p.stderr.decode()[:150])
            except Exception as _e:
                _log_op(changed_by or 'plugin', 'delete_project_dir_failed', 'project', project_id, str(_e)[:150])

        _log_op(changed_by or 'plugin', 'delete_project', 'project', project_id, f'删除项目「{project_name}」（含 {len(task_ids)} 个任务）')
        return {'ok': True, 'deleted_tasks': len(task_ids)}
    except Exception as e:
        return {'ok': False, 'error': f'{type(e).__name__}: {e}'}


def _write_file_direct(path, content):
    """直接写文件（不经过 DB，用于 AGENTS.md 等非投影文件）。"""
    import tempfile
    dir_path = os.path.dirname(path)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.md', prefix='hpw_direct_')
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            f.write(content)
        import subprocess
        p = subprocess.run(
            ['osascript', '-e', f'do shell script "cp {tmp_path} \\"{path}\\" && rm {tmp_path}"'],
            capture_output=True, timeout=30
        )
        if p.returncode != 0:
            raise RuntimeError(f'osascript failed: {p.stderr.decode()[:200]}')
    except Exception as e:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise e


# ─── 统一入口（供 obsidian-task.py 调用）────────────────────────

def run_db_first(op, spec, if_version=None):
    """DB 先行的统一写入口。
    
    Args:
        op: 操作类型
        spec: 操作参数
        if_version: 乐观锁版本号
    
    Returns:
        dict: 操作结果
    """
    changed_by = spec.get('changed_by', '')
    
    if op == 'set_property':
        return set_property(spec['path'], spec['field'], spec['value'], if_version, changed_by)
    elif op == 'update_section':
        return update_section(spec['path'], spec['section'], spec['text'], if_version, changed_by)
    elif op == 'set_body':
        return set_body(spec['path'], spec['text'], if_version, changed_by)
    elif op == 'toggle_ac':
        return toggle_ac(spec['path'], int(spec['idx']), changed_by)
    elif op == 'add_log':
        return add_log(spec['path'], spec['text'], changed_by)
    elif op == 'edit_yaml_log':
        return edit_yaml_log(
            spec.get('path', ''),
            spec.get('entry_id', ''),
            spec.get('new_yaml_text', ''),
            changed_by
        )
    elif op == 'link_session':
        return link_session(
            task_path=spec.get('task_path'),
            project_path=spec.get('project_path'),
            sid=spec.get('sid', ''),
            source=spec.get('source', 'plugin'),
            changed_by=changed_by,
            skip_validation=spec.get('skip_validation', False)
        )
    elif op == 'create_project':
        return create_project(spec['dir'], spec.get('project_content', ''), spec.get('agents_content', ''), changed_by)
    elif op == 'create_task':
        return create_task(
            project_id=spec.get('project_id', ''),
            title=spec.get('title', ''),
            goal=spec.get('goal', ''),
            task_detail=spec.get('task_detail', ''),
            acceptance=spec.get('acceptance', ''),
            priority=spec.get('priority', 'p2'),
            status=spec.get('status', 'open'),
            start=spec.get('start', ''),
            due=spec.get('due', ''),
            handler=spec.get('handler', ''),
            repeat_cfg=spec.get('repeat_cfg'),
            changed_by=changed_by
        )
    elif op == 'delete_task':
        return delete_task(spec['path'], changed_by)
    elif op == 'rename_task':
        return rename_task(spec['path'], spec.get('new_title', ''), changed_by)
    elif op == 'repeat_next':
        return repeat_next(spec['path'], changed_by)
    else:
        return {'ok': False, 'error': f'unknown op for db_first: {op}'}


def edit_yaml_log(path, entry_id, new_yaml_text, changed_by=''):
    """编辑 YAML 日志条目（DB 先行）。
    
    Args:
        path: 任务路径
        entry_id: 日志条目 ID
        new_yaml_text: 新的 YAML 文本
        changed_by: 变更来源
    
    Returns:
        dict: {'ok': True, 'version': int} 或 {'ok': False, 'error': str}
    """
    try:
        entity_type, entity_id, project_id = _validate_path(path)
        if entity_type != 'task':
            return {'ok': False, 'error': 'edit_yaml_log requires task path'}
        
        # 解析新的 YAML 条目
        entry = _parse_yaml_entry(new_yaml_text)
        if not entry['date']:
            return {'ok': False, 'error': 'invalid log entry: missing date'}
        
        conn = _wb_conn()
        try:
            # 解析显示名为 UUID
            resolved_id = _resolve_entity_id(conn, 'task', entity_id, project_id)
            if not resolved_id:
                return {'ok': False, 'error': f'task not found: {entity_id}'}
            entity_id = resolved_id
            
            # 检查 entry_id 是否属于该任务
            row = conn.execute(
                'SELECT id FROM log_entries WHERE id=? AND task_id=?',
                (entry_id, entity_id)
            ).fetchone()
            if not row:
                return {'ok': False, 'error': f'log entry not found: {entry_id}'}
            
            # 更新 log_entries
            conn.execute(
                'UPDATE log_entries SET date=?, type=?, summary=?, window=?, updated_at=? WHERE id=?',
                (entry['date'], entry['type'], entry['summary'], entry.get('window', ''),
                 int(time.time()), entry_id)
            )
            
            # 删除旧的 detail 和 sessions
            conn.execute('DELETE FROM log_detail WHERE entry_id=?', (entry_id,))
            conn.execute('DELETE FROM log_sessions WHERE entry_id=?', (entry_id,))
            
            # 插入新的 sessions
            for s in entry['sessions']:
                conn.execute(
                    'INSERT INTO log_sessions(entry_id, sid, source) VALUES(?,?,?)',
                    (entry_id, s['sid'], s.get('source', ''))
                )
            
            # 插入新的 detail
            for kind in ('outputs', 'risks', 'pending'):
                for i, item in enumerate(entry[kind]):
                    conn.execute(
                        'INSERT INTO log_detail(entry_id, kind, seq, text) VALUES(?,?,?,?)',
                        (entry_id, kind, i, item)
                    )
            for i, d in enumerate(entry['decisions']):
                conn.execute(
                    'INSERT INTO log_detail(entry_id, kind, seq, text, by) VALUES(?,?,?,?,?)',
                    (entry_id, 'decisions', i, d.get('desc', ''), d.get('by', ''))
                )
            
            _log_change('task', entity_id, 'log_entries', entry_id, 'updated', changed_by)
            v = _bump_version(conn, 'task', entity_id, changed_by)
            conn.commit()
            
            render_result = _trigger_render('task', entity_id)
            return {'ok': True, 'version': v, 'db_first': True, **render_result}
        finally:
            conn.close()
    except ValidationError as e:
        return {'ok': False, 'error': str(e)}
    except Exception as e:
        return {'ok': False, 'error': f'{type(e).__name__}: {e}'}
