#!/usr/bin/env python3
"""修复 frontmatter 值卫生：_parse_task_doc 对 handler/tags 等文本字段，
若值里含 ': '（说明捕获了相邻字段，YAML 坏行产物）→ 置空。防止脏值再回流。"""
path = '/Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/write_bridge.py'
src = open(path, encoding='utf-8').read()

anchor = "        'session_ids': [s.strip() for s in"
assert anchor in src
hygiene = """        # frontmatter 值卫生：坏行（如 'handler: project: x'）解析会把下一字段名吸进值里
        for _k in ('handler',):
            if ': ' in (new.get(_k) or ''):
                new[_k] = ''
"""
if 'frontmatter 值卫生' not in src:
    src = src.replace(anchor, hygiene + anchor, 1)
    open(path, 'w', encoding='utf-8').write(src)
    print('hygiene added')
else:
    print('already present')
