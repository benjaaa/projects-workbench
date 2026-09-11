---
name: project-workbench
description: Process Work Station (projects-workbench) tasks through the shared domain command layer. Use for Work Station task references, task/project IDs or names, 处理任务, 处理项目, /project-workbench, and project-workbench skill prompts. Read through the domain CLI, execute the task, and register progress or completion only when the user asks or the task workflow requires it.
---

# Project Workbench

Work Station 的任务工作台。SQLite 是唯一真相源，Markdown 是只读投影。所有读取、写入都经过领域命令层，禁止直接访问数据库、frontmatter 或投影文件。

## 原则

1. **先读后动**：先读取任务完整信息，包括目标、任务详情、验收标准、最近推进记录和已绑定会话。
2. **使用领域命令**：读取使用 `scripts/read-db.py`，写入使用 `wbctl.py task ...`。不要直接执行 SQL、修改 `workbench.db` 或编辑 `任务-*.md` / `项目说明-*.md`。
3. **不臆造 ID**：任务 ID、项目 ID 使用 Work Station 预填或用户给出的值。
4. **尊重状态**：如果推进记录表示等待、暂停或不要开始，停止并报告。
5. **有明确意图才写**：只有用户明确要求记录、推进或完成任务，或者任务流程明确要求闭环时，才执行写命令。
6. **汇报可追溯**：说明结果、验证方式、遗留风险和使用的命令；重试时复用同一个幂等键。
7. **高风险操作留给用户**：Agent 不重命名、删除任务或项目，不创建项目。

## Pipeline

### 1. 识别触发

任务引用示例：

```text
处理任务 -- 任务名称：<任务标题>（任务ID：<id>）
```

兼容 `/project-workbench 处理任务 -- ...`、`请使用 project-workbench skill 处理任务 -- ...`。

项目引用示例：

```text
处理项目 -- 项目名称：<项目名>（项目ID：<id>）
```

### 2. 读取任务或项目

脚本路径：

```text
~/.codex/skills/project-workbench/scripts/read-db.py
```

**任务详细信息的读取规则：**

1. `tasks --project` 只用于发现任务，返回的是任务列表，不是完整详情。
2. 开始执行前，必须根据任务 ID 再调用 `task <任务ID>` 读取完整详情。
3. 读取结果在 JSON 的 `task` 字段中。必须至少解析以下字段：

| 字段 | 用途 |
|---|---|
| `title` / `status` / `priority` / `handler` | 任务身份和执行状态 |
| `start` / `due` / `complete` | 任务时间约束 |
| `goal` | 任务目标 |
| `task_detail` | 任务详情正文，执行前必须完整阅读 |
| `acceptance_criteria` | 验收标准数组，包含文本、完成态和失败态 |
| `logs_yaml` / `logs` | 推进记录，必须检查最新一条及等待/暂停标记 |
| `session_ids` | 已绑定会话，用于恢复上下文 |
| `project_id` / `path` / `dir` | 所属项目与工作目录定位 |
| `repeat_mode` / `repeat_unit` / `repeat_every` / `repeat_day` | 周期任务闭环配置 |

如果 `task_detail`、`acceptance_criteria` 或 `logs_yaml` 读取为空，报告任务信息不足或字段缺失；不要转而读取 Markdown 文件补全。

常用读取命令：

```bash
python3 ~/.codex/skills/project-workbench/scripts/read-db.py task <任务ID>
python3 ~/.codex/skills/project-workbench/scripts/read-db.py task --title "<任务标题>" --project "<项目名>"
python3 ~/.codex/skills/project-workbench/scripts/read-db.py project <项目ID>
python3 ~/.codex/skills/project-workbench/scripts/read-db.py project --name "<项目名>"
python3 ~/.codex/skills/project-workbench/scripts/read-db.py tasks --project "<项目名>"
```

输出为标准 JSON。读取失败时停止并报告，不要根据 Markdown 推断任务内容。

### 3. 执行任务

在任务详情给出的工作区和上下文中执行；只做任务目标、任务详情和验收标准要求的事情。

任务状态变化、推进记录和验收勾选必须通过领域命令完成。示例：

```bash
WB=~/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/wbctl.py

python3 $WB task add-log --task-id <任务ID> --text "<推进记录>" \
  --idempotency-key "<stable-key>" --reason "task progress"

python3 $WB task finish --task-id <任务ID> --expected-status In-Progress \
  --idempotency-key "<stable-key>" --reason "acceptance passed"
```

`task.finish` 会在需要时自动生成下一周期任务。不要手工创建下一周期任务，也不要直接改状态绕过状态机。

### 4. 汇报

回复包含：

- 任务 ID / 项目 ID
- 结果摘要
- 验证方式和证据
- 遗留风险或待人工确认事项
- 如果调用了写命令，列出命令、幂等键和返回的 `command_id` / `audit_id`

可粘贴的推进记录 YAML：

```yaml
- date: MM-DD HH:mm:ss
  id: YYYYMMDD_HHmmss
  type: codex
  summary: 完成<任务标题>：<结果摘要>
  sessions:
    - id: <当前会话id>
      source: codex
  pending:
    - <待人工确认事项>
```

## 命令参考

命令、权限和错误码的权威来源：

```bash
python3 ~/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/wbctl.py describe
```

如果当前环境提供 Workbench MCP 工具，优先使用只读的 `workbench_task_get`、`workbench_task_list`、`workbench_project_get`；写入前确认工具要求 `reason` 和 `idempotency_key`。
