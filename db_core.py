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
import time
import json

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
VALID_PRIORITIES = {'p0', 'p1', 'p2'}


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
    """获取业务 DB 连接（读写模式）。"""
    conn = sqlite3.connect(WB_DB)
    conn.row_factory = sqlite3.Row
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
            
            # Done/Dropped 联动 complete
            if field == 'status' and value in ('Done', 'Dropped') and not row['complete']:
                today = time.strftime('%Y-%m-%d')
                conn.execute(f'UPDATE {table} SET complete=? WHERE id=?', (today, entity_id))
                _log_change(entity_type, entity_id, 'complete', row['complete'], today, changed_by)
            
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
            
            new_path = f'{PROOT}/{project_id}/tasks/任务-{new_title}.md'
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
            
            # 校验重复配置
            if row['repeat_mode'] != 'fixed' or not row['repeat_unit'] or not row['repeat_anchor']:
                return {'ok': False, 'error': 'NO_REPEAT'}
            
            # 计算下一个周期
            from datetime import datetime, timedelta
            anchor = datetime.fromtimestamp(row['repeat_anchor']) if isinstance(row['repeat_anchor'], int) else datetime.strptime(row['repeat_anchor'], '%Y-%m-%d')
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            every = row['repeat_every'] or 1
            unit = row['repeat_unit']
            day = row['repeat_day'] or 1
            
            def advance(d):
                x = d
                if unit == 'day':
                    x = d + timedelta(days=every)
                    while x <= today or x <= d:
                        x += timedelta(days=every)
                elif unit == 'week':
                    wd = day if 1 <= day <= 7 else 1
                    days_ahead = wd - x.weekday()
                    if days_ahead <= 0:
                        days_ahead += 7
                    x = x + timedelta(days=days_ahead)
                    while x <= today or x <= d:
                        x += timedelta(weeks=every)
                elif unit == 'month':
                    dd = day if 1 <= day <= 31 else 1
                    x = x.replace(day=dd)
                    while x <= today or x <= d or x.day != dd:
                        x = x + timedelta(days=32)
                        x = x.replace(day=dd)
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
            now = int(time.time())
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
            _log_change('task', new_task_id, 'created', None, new_title, changed_by)
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

    # 校验项目名称唯一性（按 name 查，id 是 UUID）
    conn = _wb_conn()
    try:
        existing = conn.execute('SELECT id FROM projects WHERE name=?', (folder_name,)).fetchone()
        if existing:
            return {'ok': False, 'error': f'项目已存在: {folder_name}'}

        # 从 project_content 解析字段（frontmatter）
        fields = _parse_frontmatter(project_content)

        # 生成 UUID 主键
        import uuid
        project_id = uuid.uuid4().hex[:12]

        # 插入 DB（id=UUID，name=显示名）
        now = int(time.time())
        conn.execute(
            'INSERT INTO projects(id, name, status, background, goal, created_at, updated_at, version) VALUES(?,?,?,?,?,?,?,?)',
            (project_id, fields.get('title', folder_name), fields.get('status', 'open'),
             fields.get('background', ''), fields.get('goal', ''),
             now, now, 1)
        )
        _log_change('project', project_id, 'created', None, folder_name, changed_by)
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
    """创建项目标准目录结构。"""
    full_path = os.path.join(VAULT, dir_path)
    for sub in ['raw', 'output', 'tmp', 'scripts', 'tasks']:
        os.makedirs(os.path.join(full_path, sub), exist_ok=True)
    # pipeline.md
    pipeline_path = os.path.join(full_path, 'pipeline.md')
    if not os.path.exists(pipeline_path):
        with open(pipeline_path, 'w', encoding='utf-8') as f:
            f.write('')


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
            conn.execute('DELETE FROM projects WHERE id=?', (project_id,))

            _log_change('project', project_id, 'deleted', project_name, None, changed_by)
            conn.commit()
        finally:
            conn.close()

        # 删除目录（含全部文件）——用名称定位
        proj_dir = os.path.join(VAULT, PROOT, project_name)
        if os.path.isdir(proj_dir):
            try:
                shutil.rmtree(proj_dir)
            except Exception:
                pass  # 文件删除失败不阻塞

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
