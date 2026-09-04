#!/usr/bin/env python3
"""投影生成器：DB 行 → md 文档文本（纯函数，无 IO）。

render_task_doc / render_project_doc 产出完整 md 文本；
生成顺序 = 创建时序原则的落地：调用方先写 DB，再取本文本写文件。
"""
import json


def _fm_str(v):
    return '' if v is None else str(v)


def _fm_version(v):
    return 'version: "%d"' % v if v else 'version: ""'


def _repeat_lines(t):
    lines = []
    if t['repeat_mode']:
        lines += [
            'repeat_mode: %s' % t['repeat_mode'],
            'repeat_unit: %s' % (t['repeat_unit'] or 'week'),
            'repeat_every: %s' % (t['repeat_every'] if t['repeat_every'] is not None else 1),
        ]
        if t['repeat_day'] is not None:
            lines.append('repeat_day: %s' % t['repeat_day'])
        if t['repeat_anchor']:
            lines.append('repeat_anchor: %s' % t['repeat_anchor'])
    return lines


def _tags_line(tags_json):
    tags = json.loads(tags_json or '[]')
    return 'tags:' if not tags else 'tags:\n' + '\n'.join('  - %s' % t for t in tags)


def _session_line(sids):
    return 'session_ids: ' + ','.join(sids)


def _sections(parts):
    """过滤空段并拼接。"""
    return '\n'.join(p for p in parts if p and p.strip())


def render_task_doc(t, sids, log_yaml, sections=None):
    """t: tasks 行(dict)；sids: 有序 sid 列表；log_yaml: 推进记录 yaml 围栏内容(可为 '')。

    sections: 可选的区段级更新（增量投影），形如 {'frontmatter':True,'body':False,'log':True}
    —— 默认 None = 全量。body 原文来自 tasks.body，frontmatter 由字段拼装。

    区段间保留原文件的双换行风格；frontmatter 行间单换行。"""
    sections = sections or {'frontmatter': True, 'body': True, 'log': True}
    fm = _sections([
        '---',
        _sections([
            'title: %s' % t['title'],
            'status: %s' % t['status'],
            'priority: %s' % (t['priority'] or 'p2'),
            'project: %s' % t['project_id'],
            _sections(filter(None, [
                'start: %s' % _fm_str(t['start']) if t['start'] else '',
                'due: %s' % _fm_str(t['due']) if t['due'] else '',
                'complete: %s' % _fm_str(t['complete']) if t['complete'] else '',
            ])),
            ('handler: %s' % t['handler']) if t['handler'] else None,
            '\n'.join(_repeat_lines(t)),
            _tags_line(t['tags_json']),
            _fm_version(t['version']),
            ('session_ids: ' + ','.join(sids)) if sids else None,
        ]),
        _sections(filter(None, [
            'kanban_task_id: %s' % t['kanban_task_id'] if t['kanban_task_id'] else '',
        ])),
        '---',
    ]) if sections.get('frontmatter') else None

    parts = []
    # 正文重组：H1(标题) + 目标 + 任务详情(body=任务详情区段内容) + 验收标准
    title_text = t.get('title') if isinstance(t, dict) else t['title']
    body_parts_full = ['# ' + title_text]
    goal_text = (t.get('goal') if isinstance(t, dict) else t['goal']) or ''
    if goal_text.strip():
        body_parts_full.append('## 目标\n\n' + goal_text.strip())
    body_text = (t.get('body') if isinstance(t, dict) else t['body']) or ''
    if body_text.strip():
        body_parts_full.append('## 任务详情\n\n' + body_text.strip())
    acc_text = (t.get('acceptance') if isinstance(t, dict) else t['acceptance']) or ''
    if acc_text.strip():
        body_parts_full.append('## 验收标准\n\n' + acc_text.strip())
    if sections.get('body'):
        parts.append('\n\n'.join(body_parts_full))
    if sections.get('log'):
        log_block = '\n```yaml\n' + log_yaml.strip('\n') + '\n```' if log_yaml.strip() else '\n'
        parts.append('## 推进记录\n' + log_block)
    body = _sections(filter(None, parts)) if (sections.get('body') or sections.get('log')) else None

    if sections.get('frontmatter') and sections.get('log') and fm is not None and body is not None:
        return fm + '\n\n' + body + '\n'
    return {'frontmatter': fm, 'body': body}  # 增量模式返回分区


def render_project_doc(p, sids):
    fm = _sections([
        '---',
        _sections([
            'title: %s' % p['name'],
            'status: %s' % p['status'],
            _sections(filter(None, [
                'start: %s' % _fm_str(p['start']) if p['start'] else '',
                'due: %s' % _fm_str(p['due']) if p['due'] else '',
            ])),
            _fm_version(p['version']),
            _tags_line(p['tags_json']),
            _session_line(sids) if sids else 'session_ids:',
        ]),
        _sections(filter(None, [
            'complete: %s' % _fm_str(p['complete']) if p['complete'] else '',
        ])),
        '---',
    ])
    body = _sections(filter(None, [
        '# %s' % p['name'],
        p['background'] and p['background'].strip(),
        p['goal'] and '## 目标\n\n' + p['goal'].strip(),
    ]))
    return fm + '\n\n' + body + '\n'
