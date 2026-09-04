#!/usr/bin/env python3
"""Workbench DB — projects-workbench 真相源库。

架构决定（2026-09-04 Ben 拍板）：
- 结构化字段（状态/日期/关系/session关联/推进记录）真相在 DB
- md 文档是程序生成的投影：frontmatter + 推进记录 YAML 块由 DB 渲染
- body 长文本（任务详情/验收标准/项目背景等）真相仍在文档（方案 B）
- documents 表 = 实体↔文档显式映射
"""
import json
import os
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workbench.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,               -- = 项目名（与人读目录一致）
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    start TEXT,
    due TEXT,
    complete TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    tags_json TEXT DEFAULT '[]',
    background TEXT DEFAULT '',        -- ## 项目背景（body 区段，方案B终版：入库）
    goal TEXT DEFAULT '',              -- ## 目标
    created_at INTEGER,
    updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,               -- = 文件名去 任务- 前缀/.md（锚定文件名）
    project_id TEXT NOT NULL REFERENCES projects(id),
    title TEXT NOT NULL,               -- frontmatter title，显示名
    status TEXT NOT NULL DEFAULT 'open',
    priority TEXT DEFAULT '',
    start TEXT,
    due TEXT,
    complete TEXT,
    handler TEXT DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,   -- 乐观锁，延续现有语义
    tags_json TEXT DEFAULT '[]',
    kanban_task_id TEXT DEFAULT '',
    goal TEXT DEFAULT '',              -- ## 目标
    body TEXT DEFAULT '',              -- ## 任务详情
    acceptance TEXT DEFAULT '',        -- ## 验收标准（checkbox 原文）
    repeat_mode TEXT DEFAULT '',       -- 重复任务字段（方案B：实例平铺）
    repeat_unit TEXT DEFAULT '',
    repeat_every INTEGER,
    repeat_day INTEGER,
    repeat_anchor TEXT,
    created_at INTEGER,
    updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS project_sessions (
    project_id TEXT NOT NULL REFERENCES projects(id),
    sid TEXT NOT NULL,
    linked_at INTEGER NOT NULL,
    source TEXT DEFAULT '',
    PRIMARY KEY (project_id, sid)
);

CREATE TABLE IF NOT EXISTS task_sessions (
    task_id TEXT NOT NULL REFERENCES tasks(id),
    sid TEXT NOT NULL,
    linked_at INTEGER NOT NULL,
    source TEXT DEFAULT '',
    PRIMARY KEY (task_id, sid)
);

CREATE TABLE IF NOT EXISTS log_entries (
    id TEXT PRIMARY KEY,               -- entry id, e.g. 20260902_182932
    task_id TEXT NOT NULL REFERENCES tasks(id),
    date TEXT NOT NULL,                -- MM-DD HH:mm:ss（原样）
    type TEXT NOT NULL,                -- review | manual | kanban
    summary TEXT DEFAULT '',
    window TEXT DEFAULT '',
    created_at INTEGER,
    updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS log_detail (
    entry_id TEXT NOT NULL REFERENCES log_entries(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,                -- outputs | decisions | risks | pending
    seq INTEGER NOT NULL,
    text TEXT DEFAULT '',
    by TEXT DEFAULT '',                -- decisions 专用
    PRIMARY KEY (entry_id, kind, seq)
);

CREATE TABLE IF NOT EXISTS log_sessions (
    entry_id TEXT NOT NULL REFERENCES log_entries(id) ON DELETE CASCADE,
    sid TEXT NOT NULL,
    source TEXT DEFAULT '',
    PRIMARY KEY (entry_id, sid)
);

-- 文档映射表（Ben 2026-09-04 拍板：全量映射）
-- entity_type: project|task = 实体主文档（生成器管理版本）
--              file   = 项目目录内其他文件（name+path 映射）
--              folder = 项目目录内子文件夹（仅 path 映射，entity_id=path）
CREATE TABLE IF NOT EXISTS change_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_at INTEGER NOT NULL,
    changed_by TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_change_entity ON change_log(entity_type, entity_id, changed_at);

CREATE TABLE IF NOT EXISTS documents (
    entity_type TEXT NOT NULL,         -- project | task | file | folder
    entity_id TEXT NOT NULL,           -- 实体id；file=文件名；folder=path
    path TEXT NOT NULL,                -- vault 相对路径
    filename TEXT NOT NULL,
    content_version INTEGER NOT NULL DEFAULT 0,  -- 投影重生成次数（仅 project/task）
    generated_at INTEGER,
    PRIMARY KEY (entity_type, entity_id, path)
);

CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_task_sessions_task ON task_sessions(task_id);
CREATE INDEX IF NOT EXISTS idx_log_entries_task ON log_entries(task_id);
CREATE INDEX IF NOT EXISTS idx_documents_path ON documents(path);
"""


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', '1')")
    conn.commit()
    conn.close()


if __name__ == '__main__':
    init_db()
    print('initialized:', DB_PATH)
