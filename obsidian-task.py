#!/usr/bin/env python3
"""obsidian-task.py — 入口分发层（重构后）

职责：
- 接收 shell 命令，路由到读/写核心
- 只保留 main() 分发，无业务逻辑
- 兼容现有 plugin.js 调用接口

设计原则：
- 瘦入口：所有业务逻辑在 db_core.py / db_read.py / renderer.py
- 接口不变：plugin.js 无需修改
- 错误友好：统一错误格式返回
"""
import base64
import json
import os
import re
import sys
import time

# 路径常量
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT = '/Users/ben/Documents/Second Brain/Second Brain'
PROOT = '2. Project/2.1 Project'

# 添加脚本目录到 Python 路径
sys.path.insert(0, SCRIPT_DIR)


def _b64e(s):
    """Base64 编码（供 shell 输出）。"""
    return base64.b64encode(s.encode('utf-8')).decode('ascii')


def _b64d(s):
    """Base64 解码（供 shell 输入）。"""
    return base64.b64decode(s).decode('utf-8')


def _json_out(data):
    """输出 JSON（base64 编码，避免 shell 特殊字符问题）。"""
    print(_b64e(json.dumps(data, ensure_ascii=False)))


def _json_err(msg):
    """输出错误 JSON。"""
    _json_out({'ok': False, 'error': str(msg)[:300]})


def _chunked_out(data, pid=None):
    """大输出分片：写临时文件，返回分片元信息（与 plugin.js ld() 兼容）。"""
    b64 = _b64e(json.dumps(data, ensure_ascii=False))
    if pid is None:
        pid = os.getpid()
    tmp = f'/tmp/hpw_data_{pid}.b64'
    with open(tmp, 'w') as f:
        f.write(b64)
    # 输出分片元信息（plugin.js ld() 期望的格式）
    print(json.dumps({'len': len(b64), 'pid': pid}))


def _read_chunk(off, lim, pid):
    """读取分片数据。"""
    tmp = f'/tmp/hpw_data_{pid}.b64'
    try:
        with open(tmp, 'r') as f:
            data = f.read()
        print(data[off:off + lim])
    except FileNotFoundError:
        print('')


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
    
    # ─── run 模式：JSON spec 驱动 ─────────────────────────
    if mode == 'run' and len(sys.argv) >= 3:
        try:
            arg = sys.argv[2]
            if arg == '-':
                spec = json.loads(sys.stdin.read())
            else:
                spec = json.loads(_b64d(arg))
        except Exception as e:
            _json_err(f'bad spec: {e}')
            return
        
        op = spec.get('op', '')
        if not op:
            _json_err('op is required')
            return
        
        # 乐观锁参数
        if_version = spec.get('if_version')
        
        # 路由到写核心
        if op in ('set_property', 'update_section', 'set_body', 'toggle_ac', 'add_log',
                  'link_session', 'create_project'):
            try:
                from db_core import run_db_first
                result = run_db_first(op, spec, if_version=if_version)
                _json_out(result)
            except Exception as e:
                _json_err(f'db_core: {type(e).__name__}: {e}')
            return
        
        # 读操作
        elif op == 'read':
            path = spec.get('path', '')
            try:
                with open(os.path.join(VAULT, path), 'r', encoding='utf-8') as f:
                    content = f.read()
                _json_out({'ok': True, 'content': content})
            except Exception as e:
                _json_err(f'read failed: {e}')
            return
        
        elif op == 'recent_sessions':
            # 从 state.db 读最近会话
            import sqlite3
            state_db = os.path.join(os.path.expanduser('~'), '.hermes/profiles/business_analysis/state.db')
            limit = min(int(spec.get('limit', 10)), 50)
            sessions = []
            try:
                conn = sqlite3.connect(state_db)
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    '''SELECT id, title, cwd, last_activity_at, message_count, source
                       FROM sessions WHERE COALESCE(archived, 0) = 0
                       ORDER BY COALESCE(last_activity_at, started_at) DESC LIMIT ?''',
                    (limit,)
                ).fetchall()
                
                # 从 workbench.db 补关联
                sid_to_link = {}
                try:
                    wb = sqlite3.connect(os.path.join(SCRIPT_DIR, 'workbench.db'))
                    wb.row_factory = sqlite3.Row
                    for r2 in wb.execute(
                        '''SELECT ts.sid AS sid, t.id AS tid, t.title AS ttitle, p.id AS pid, p.name AS pname
                           FROM task_sessions ts JOIN tasks t ON t.id = ts.task_id
                           JOIN projects p ON p.id = t.project_id'''):
                        sid_to_link[r2['sid']] = {
                            'project': r2['pname'],
                            'issue_title': r2['ttitle'] or '',
                            'issue_path': os.path.join(PROOT, r2['pid'], 'tasks', '任务-' + r2['tid'] + '.md'),
                        }
                    for r2 in wb.execute(
                        '''SELECT ps.sid AS sid, p.name AS pname
                           FROM project_sessions ps JOIN projects p ON p.id = ps.project_id'''):
                        if r2['sid'] not in sid_to_link:
                            sid_to_link[r2['sid']] = {'project': r2['pname'], 'issue_title': '', 'issue_path': ''}
                    wb.close()
                except Exception:
                    pass
                
                for r in rows:
                    s = {
                        'id': r['id'],
                        'title': (r['title'] or '(无标题)')[:60],
                        'last_activity_at': r['last_activity_at'] or 0,
                    }
                    cwd = r['cwd'] or ''
                    base_prefix = os.path.join(VAULT, PROOT) + '/'
                    proj = cwd[len(base_prefix):].split('/')[0] if cwd.startswith(base_prefix) else ''
                    s['project'] = proj
                    link = sid_to_link.get(r['id'])
                    if link:
                        s['link'] = link
                    elif proj:
                        s['link'] = {'project': proj, 'issue_title': '', 'issue_path': ''}
                    sessions.append(s)
                conn.close()
            except Exception:
                sessions = []
            _chunked_out({'ok': True, 'sessions': sessions})
            return
        
        elif op == 'cmd_list':
            # 列出快捷指令
            cmds_dir = os.path.join(VAULT, PROOT, 'commands')
            cmds = []
            if os.path.exists(cmds_dir):
                for f in os.listdir(cmds_dir):
                    if f.endswith('.md'):
                        name = f[:-3]
                        path = os.path.join(cmds_dir, f)
                        try:
                            with open(path, 'r', encoding='utf-8') as fp:
                                content = fp.read()
                            # 解析 frontmatter
                            title = name
                            desc = ''
                            m = re.match(r'^---\n([\s\S]*?)\n---', content)
                            if m:
                                for line in m.group(1).split('\n'):
                                    if line.startswith('title:'):
                                        title = line[6:].strip()
                                    elif line.startswith('desc:'):
                                        desc = line[5:].strip()
                            cmds.append({'name': name, 'title': title, 'desc': desc, 'path': path})
                        except Exception:
                            pass
            _json_out({'ok': True, 'cmds': cmds})
            return
        
        elif op == 'inbox_list':
            # 列出 Inbox 收集
            inbox_dir = os.path.join(VAULT, PROOT, 'Inbox')
            items = []
            if os.path.exists(inbox_dir):
                for f in os.listdir(inbox_dir):
                    if f.endswith('.md'):
                        path = os.path.join(inbox_dir, f)
                        try:
                            with open(path, 'r', encoding='utf-8') as fp:
                                content = fp.read()
                            # 解析 frontmatter
                            title = f[:-3]
                            ts = ''
                            first = ''
                            m = re.match(r'^---\n([\s\S]*?)\n---\n?([\s\S]*)$', content)
                            if m:
                                fm_raw, body = m.group(1), m.group(2)
                                for line in fm_raw.split('\n'):
                                    if line.startswith('title:'):
                                        title = line[6:].strip()
                                    elif line.startswith('ts:'):
                                        ts = line[3:].strip()
                                first = body.strip().split('\n')[0] if body.strip() else ''
                            items.append({
                                'name': f[:-3], 'path': os.path.join(PROOT, 'Inbox', f),
                                'title': title, 'ts': ts, 'first': first, 'content': content
                            })
                        except Exception:
                            pass
                # 按 ts 倒序
                items.sort(key=lambda x: x.get('ts', ''), reverse=True)
            _json_out({'ok': True, 'items': items})
            return
        
        elif op == 'ops_log':
            # 写操作日志（独立日志库）
            try:
                from db_core import _log_op
                _log_op(
                    spec.get('source', 'plugin'),
                    spec.get('action', ''),
                    spec.get('entity_type', ''),
                    spec.get('entity_id', ''),
                    spec.get('detail', '')
                )
                _json_out({'ok': True})
            except Exception as e:
                _json_err(f'ops_log: {e}')
            return
        
        elif op == 'ops_query':
            # 查询操作日志
            try:
                import sqlite3
                log_db = os.path.join(SCRIPT_DIR, 'workbench-log.db')
                if not os.path.exists(log_db):
                    _json_out({'ok': True, 'logs': []})
                    return
                conn = sqlite3.connect(log_db)
                conn.row_factory = sqlite3.Row
                where = []
                args = []
                if spec.get('project'):
                    where.append('entity_id = ?')
                    args.append(spec['project'])
                if spec.get('action'):
                    where.append('action = ?')
                    args.append(spec['action'])
                if spec.get('days'):
                    where.append('created_at >= ?')
                    args.append(int(time.time() * 1000) - int(spec['days']) * 86400 * 1000)
                sql = 'SELECT source, action, entity_type, entity_id, detail, created_at FROM ops_log'
                if where:
                    sql += ' WHERE ' + ' AND '.join(where)
                sql += ' ORDER BY id DESC LIMIT ' + str(int(spec.get('limit', 500)))
                rows = conn.execute(sql, args).fetchall()
                logs = [dict(r) for r in rows]
                conn.close()
                _json_out({'ok': True, 'logs': logs})
            except Exception as e:
                _json_err(f'ops_query: {e}')
            return
        
        elif op == 'kanban_create':
            # 转发到 kanban DB（保留现有逻辑）
            _json_err('kanban_create: not implemented in refactor yet')
            return
        
        else:
            _json_err(f'unknown op: {op}')
            return
    
    # ─── save 模式：加载所有数据（DB 优先）────────────────
    if mode == 'save':
        # 清理旧临时文件
        import glob
        now = time.time()
        for f in glob.glob('/tmp/hpw_*.b64'):
            try:
                if now - os.path.getmtime(f) > 300:
                    os.unlink(f)
            except Exception:
                pass
        
        try:
            from db_read import load_projects, load_tasks
            result = {}
            result['projects'] = load_projects().get('projects', [])
            result['tasks'] = load_tasks().get('tasks', [])
            _chunked_out(result)
        except Exception as e:
            # DB 异常时降级到空列表
            _chunked_out({'projects': [], 'tasks': [], 'error': str(e)})
        return
    
    # ─── read 模式：读取分片数据 ─────────────────────────
    if mode == 'read':
        off = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        lim = int(sys.argv[3]) if len(sys.argv) > 3 else 3900
        pid = sys.argv[4] if len(sys.argv) > 4 else ''
        _read_chunk(off, lim, pid)
        return
    
    # ─── session_counts 模式 ─────────────────────────────
    if mode == 'session_counts':
        import sqlite3
        state_db = os.path.join(os.path.expanduser('~'), '.hermes/profiles/business_analysis/state.db')
        counts = {}
        try:
            conn = sqlite3.connect(state_db)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                'SELECT cwd, COUNT(*) as cnt FROM sessions WHERE cwd LIKE ? GROUP BY cwd',
                ('%' + os.path.join(VAULT, PROOT) + '%',)
            ).fetchall()
            base_prefix = os.path.join(VAULT, PROOT) + '/'
            for r in rows:
                cwd = r['cwd'] or ''
                if cwd.startswith(base_prefix):
                    proj_dir = cwd[len(base_prefix):]
                    counts[proj_dir] = r['cnt']
            conn.close()
        except Exception:
            pass
        _json_out(counts)
        return
    
    # ─── sessions / save_sessions / read_sessions ─────────
    if mode in ('sessions', 'save_sessions', 'read_sessions'):
        import sqlite3
        proj_dir = sys.argv[2] if len(sys.argv) > 2 else ''
        sid_list = sys.argv[3] if len(sys.argv) > 3 else ''
        
        # 从 state.db 查询
        state_db = os.path.join(os.path.expanduser('~'), '.hermes/profiles/business_analysis/state.db')
        full_cwd = os.path.join(VAULT, PROOT, proj_dir)
        session_ids = [s.strip() for s in sid_list.split(',') if s.strip()]
        seen = set()
        sessions = []
        
        try:
            conn = sqlite3.connect(state_db)
            conn.row_factory = sqlite3.Row
            
            # 0) DB 关联优先
            try:
                wb = sqlite3.connect(os.path.join(SCRIPT_DIR, 'workbench.db'))
                db_sids = [r[0] for r in wb.execute('SELECT sid FROM project_sessions WHERE project_id=?', (proj_dir,)).fetchall()]
                wb.close()
            except Exception:
                db_sids = []
            for sid in db_sids:
                if sid in seen or not sid:
                    continue
                try:
                    r = conn.execute(
                        'SELECT id, title, cwd, last_activity_at, message_count, input_tokens, output_tokens, started_at, source FROM sessions WHERE id = ?',
                        (sid,)
                    ).fetchone()
                    if r:
                        seen.add(sid)
                        sessions.append(_session_from_row(r))
                except Exception:
                    pass
            
            # 1) cwd 匹配
            rows = conn.execute(
                'SELECT id, title, cwd, last_activity_at, message_count, input_tokens, output_tokens, started_at, source FROM sessions WHERE cwd = ? OR cwd LIKE ? ORDER BY last_activity_at DESC LIMIT 50',
                (full_cwd, full_cwd + '/%')
            ).fetchall()
            for r in rows:
                sid = r['id']
                if sid not in seen:
                    seen.add(sid)
                    sessions.append(_session_from_row(r))
            
            # 2) 指定 sid
            for sid in session_ids:
                if sid in seen or not sid:
                    continue
                try:
                    r = conn.execute(
                        'SELECT id, title, cwd, last_activity_at, message_count, input_tokens, output_tokens, started_at, source FROM sessions WHERE id = ?',
                        (sid,)
                    ).fetchone()
                    if r:
                        seen.add(sid)
                        sessions.append(_session_from_row(r))
                except Exception:
                    pass
            
            sessions.sort(key=lambda x: -(x.get('last_activity_at') or x.get('started_at') or 0))
            conn.close()
        except Exception:
            sessions = []
        
        if mode == 'sessions':
            _json_out({'sessions': sessions})
        elif mode == 'save_sessions':
            _chunked_out({'sessions': sessions}, pid=os.getpid())
        elif mode == 'read_sessions':
            off = int(sys.argv[2]) if len(sys.argv) > 2 else 0
            lim = int(sys.argv[3]) if len(sys.argv) > 3 else 3900
            pid = sys.argv[4] if len(sys.argv) > 4 else ''
            _read_chunk(off, lim, pid)
        return
    
    # ─── 默认模式：兼容旧调用 ─────────────────────────────
    result = {}
    if mode in ('all', 'projects'):
        try:
            from db_read import load_projects
            result['projects'] = load_projects().get('projects', [])
        except Exception:
            result['projects'] = []
    if mode in ('all', 'tasks'):
        try:
            from db_read import load_tasks
            result['tasks'] = load_tasks().get('tasks', [])
        except Exception:
            result['tasks'] = []
    _json_out(result)


def _session_from_row(r):
    """从 DB 行构建 session 字典。"""
    return {
        'id': r['id'],
        'title': r['title'] or '(无标题)',
        'message_count': r['message_count'] or 0,
        'last_activity_at': r['last_activity_at'] or 0,
        'input_tokens': r['input_tokens'] or 0,
        'output_tokens': r['output_tokens'] or 0,
        'source': r['source'] or '',
        'started_at': r['started_at'] or 0,
        'first_user': '',
        'last_assistant': '',
    }


if __name__ == '__main__':
    main()
