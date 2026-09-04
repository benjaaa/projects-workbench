#!/usr/bin/env python3
"""documents 映射重做（语义修正版，2026-09-04 Ben 拍板）。

映射 = 实体↔文档骨架关系，非磁盘镜像：
- folder：仅项目标准结构 8 项（项目说明.md 所在根 + AGENTS.md/pipeline.md 附属
  + raw/output/tmp/tasks/scripts），名称+路径
- file：仅任务文档（tasks/任务-*.md）+ output 内交付物，名称+路径
- project/task 主文档行保持不变
- 项目创建时序（后续生成器实现）：先写 DB 行，再创建文件系统

幂等：清空 file/folder 行后按上述规则重建；重复执行结果一致。
"""
import os
import sqlite3
import time

DB = '/Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/workbench.db'
VAULT = '/Users/ben/Documents/Second Brain/Second Brain'
PROOT = os.path.join(VAULT, '2. Project', '2.1 Project')

STD_DIRS = ['raw', 'output', 'tmp', 'tasks', 'scripts']


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    now = int(time.time())

    conn.execute("DELETE FROM documents WHERE entity_type IN ('file','folder')")

    stats = {'folder': 0, 'file_task': 0, 'file_output': 0}
    for r in conn.execute("SELECT id FROM projects"):
        pname = r['id']
        pdir = os.path.join(PROOT, pname)
        if not os.path.isdir(pdir):
            continue
        # 标准结构 folder 行（存在的才映射；缺失目录由生成器补建）
        for d in STD_DIRS:
            if os.path.isdir(os.path.join(pdir, d)):
                rel = f'2. Project/2.1 Project/{pname}/{d}'
                conn.execute(
                    'INSERT OR REPLACE INTO documents(entity_type,entity_id,path,filename,content_version,generated_at) VALUES(?,?,?,?,0,?)',
                    ('folder', rel, rel, d, now))
                stats['folder'] += 1
        # file：任务文档
        tdir = os.path.join(pdir, 'tasks')
        if os.path.isdir(tdir):
            for f in sorted(os.listdir(tdir)):
                if f.startswith('任务-') and f.endswith('.md'):
                    rel = f'2. Project/2.1 Project/{pname}/tasks/{f}'
                    conn.execute(
                        'INSERT OR REPLACE INTO documents(entity_type,entity_id,path,filename,content_version,generated_at) VALUES(?,?,?,?,0,?)',
                        ('file', f, rel, f, now))
                    stats['file_task'] += 1
        # file：output 交付物
        odir = os.path.join(pdir, 'output')
        if os.path.isdir(odir):
            for root, dirs, files in os.walk(odir):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for f in files:
                    if f.startswith('.'):
                        continue
                    rel = os.path.relpath(os.path.join(root, f), VAULT)
                    conn.execute(
                        'INSERT OR REPLACE INTO documents(entity_type,entity_id,path,filename,content_version,generated_at) VALUES(?,?,?,?,0,?)',
                        ('file', f, rel, f, now))
                    stats['file_output'] += 1

    conn.commit()
    dist = conn.execute("SELECT entity_type, count(*) FROM documents GROUP BY entity_type").fetchall()
    conn.close()
    print('rebuilt:', stats)
    for row in dist:
        print(f'  {row[0]}: {row[1]}')


if __name__ == '__main__':
    main()
