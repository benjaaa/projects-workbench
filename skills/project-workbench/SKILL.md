---
name: project-workbench
description: Process Work Station (projects-workbench) tasks through the shared domain command layer. Use for Work Station task references, task/project IDs or names, 处理任务, 处理项目, /project-workbench, and project-workbench skill prompts. This skill declares the callable methods and the ordered method chains required for common scenarios.
---

# Project Workbench

Work Station 的任务工作台。SQLite 是唯一真相源，Markdown 是只读投影。读取和写入都必须经过领域命令层，禁止直接访问数据库、frontmatter 或投影文件。

## 基本原则

1. **先读后动**：执行任务前必须读取完整任务详情，不能只依赖任务列表或对话摘要。
2. **按场景调用方法链**：一个场景通常需要多个方法，顺序是“读取 → 检查状态 → 执行 → 写入 → 再次读取验证”。
3. **写入带审计信息**：写方法必须提供 `--reason` 和稳定的 `--idempotency-key`。
4. **尊重状态和下一步**：推进记录明确说等待、暂停或不要开始，停止并报告。
5. **不臆造 ID**：任务 ID、项目 ID、会话 ID 使用 Work Station 预填或用户给出的值。
6. **禁止高风险绕过**：Agent 不创建、重命名或删除任务/项目，不直接改 SQLite 或 Markdown；这些操作留给 UI 用户。

## 任务执行前置门禁

处理任何任务前，必须先调用 `read-db.py task <任务ID>`，并完整读取以下四项作为执行上下文：

| 必需上下文 | 字段 | 要求 |
|---|---|---|
| 任务目标 | `goal` | 必须读取；不能只看任务标题或摘要 |
| 验收标准 | `acceptance_criteria` | 必须读取全部条目、完成态和失败态 |
| 任务详情 | `task_detail` | 必须完整读取，作为实际执行要求的主要依据 |
| 任务跟进记录 | `logs` | 必须读取；为空时明确记录为“无跟进记录”，不能跳过 |

只有以上四项都完成读取后，才能开始执行。读取失败或字段缺失时停止并报告，不得依据 Markdown 投影自行补全上下文。

## 可调用方法目录

### 读取方法

脚本：`~/.codex/skills/project-workbench/scripts/read-db.py`

| 方法 | 作用 | 返回值 |
|---|---|---|
| `tasks --project "<项目名>"` | 发现项目下的任务 | `tasks` 列表，只含摘要，不是完整详情 |
| `task <任务ID>` | 读取单个任务完整详情 | `task` 对象，含目标、详情、验收、日志、会话、周期配置 |
| `task --title "<标题>" --project "<项目名>"` | 按标题读取完整详情 | 同上 |
| `draft <DraftID>` | 读取单个 Draft 详情 | `draft` 对象，含标题、正文、状态和时间 |
| `drafts` | 列出全部 Draft | `drafts` 列表 |
| `project <项目ID>` | 读取项目详情 | `project` 对象 |
| `project --name "<项目名>"` | 按名称读取项目详情 | 同上 |
| `sessions --project "<项目名>"` | 读取项目关联会话 | `sessions` 列表，含 Codex/Hermes 来源、标题和活动时间 |

读取任务详情后必须检查：`goal`、`task_detail`、`acceptance_criteria`、`logs`、`session_ids`、`project_id`、`path`、`repeat_*`。任务详情为空时报告信息不足，禁止读取 Markdown 补全。

### 写入方法

脚本：`~/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/wbctl.py`

所有写方法都要传 `--idempotency-key` 和 `--reason`。

| 方法 | 作用 | 关键参数 |
|---|---|---|
| `task update-field` | 更新任务字段 | `--task-id`、`--field`、`--value` |
| `task update-status` | 更新任务状态 | `--task-id`、`--status`、`--expected-status` |
| `task toggle-acceptance` | 切换验收项状态 | `--task-id`、`--index` |
| `task update-section` | 更新目标或任务详情等区段 | `--task-id`、`--section`、`--text` |
| `task add-log` | 追加结构化推进记录 | `--task-id`、`--summary` |
| `task finish` | 完成任务并处理周期任务 | `--task-id`、`--expected-status` |
| `project update-field` | 更新项目安全字段 | `--project-id` 或 `--name`、`--field`、`--value` |
| `project update-section` | 更新项目背景或目标 | `--project-id` 或 `--name`、`--section`、`--text` |
| `session link` | 绑定任务与会话 | `--task-id`、`--sid`、`--source` |
| `projection render` | 手动刷新投影 | `--task-id` 或 `--project-id` 或 `--path` |

命令目录和权限矩阵的权威来源：

```bash
python3 ~/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/wbctl.py describe
```

### 禁止 Agent 调用的方法

`task create`、`task rename`、`task delete`、`project create`、`project rename`、`project delete` 和直接 SQL/文件写入。收到这类请求时，说明需要用户在 Work Station UI 中完成。

## 场景到方法链

### 场景 A：处理任务

1. `read-db.py task <任务ID>` 读取完整详情，并确认 `goal`、`acceptance_criteria`、`task_detail`、`logs` 四项上下文都已读取。
2. 检查 `logs`，如果存在等待/暂停要求，停止并报告。
3. 必要时调用 `read-db.py project --name <项目名>` 和 `read-db.py sessions --project <项目名>` 补充项目上下文。
4. 执行任务。
5. 如用户要求记录推进：`wbctl task add-log`。
6. 如满足完成条件：逐项 `wbctl task toggle-acceptance`，然后 `wbctl task finish --expected-status <当前状态>`。
7. 再次调用 `read-db.py task <任务ID>` 验证状态、验收和日志已经生效。
8. 汇报任务 ID、执行结果、验证证据、日志命令和 `command_id` / `audit_id`。

### 场景 B：只写推进记录

1. `read-db.py task <任务ID>`。
2. `wbctl task add-log --task-id <ID> --summary <记录> --idempotency-key <键> --reason <原因>`。
3. `read-db.py task <任务ID>`，确认 `logs` 出现新记录。
4. 不要顺手修改状态或验收。

### 场景 C：完成任务

1. `read-db.py task <任务ID>`，确认当前状态和验收标准。
2. 对已完成验收项调用 `wbctl task toggle-acceptance --index <索引>`。
3. 调用 `wbctl task finish --task-id <ID> --expected-status <当前状态>`。
4. `read-db.py task <任务ID>` 验证 `status=Done`。
5. 如果返回 `next_task` 或周期任务信息，汇报下一周期结果。

### 场景 D：修改任务目标或详情

1. `read-db.py task <任务ID>`。
2. `wbctl task update-section --task-id <ID> --section "目标|任务详情" --text <全文>`。
3. `read-db.py task <任务ID>` 验证对应字段。
4. 更新详情不等于完成任务，不要自动调用 `task.finish`。

### 场景 E：更新任务字段

1. `read-db.py task <任务ID>`。
2. `wbctl task update-field` 或 `wbctl task update-status`。
3. `read-db.py task <任务ID>` 验证新值。
4. 涉及状态流转时使用 `--expected-status`，遇到冲突停止，不强制覆盖。

### 场景 F：处理项目

1. `read-db.py project --name <项目名>` 读取项目详情。
2. `read-db.py tasks --project <项目名>` 读取任务列表。
3. 对需要处理的任务逐个执行场景 A；不要只看任务列表直接批量写入。
4. 项目级结果需要记录时，使用 `wbctl project update-section` 或 `wbctl task add-log`，然后重新读取验证。

### 场景 G：修改项目字段或背景

1. `read-db.py project --name <项目名>`。
2. 字段使用 `wbctl project update-field`，背景/目标使用 `wbctl project update-section`。
3. `read-db.py project --name <项目名>` 验证。
4. 项目改名留给 UI 用户，不要调用 `project rename`。

### 场景 H：关联会话

1. `read-db.py task <任务ID>` 或 `read-db.py project --name <项目名>`。
2. `wbctl session link --task-id <ID> --sid <会话ID> --source codex`。
3. 再次读取任务或项目，确认 `session_ids` 包含新会话。
4. 重试时复用原幂等键。


### 场景 I：处理 Draft

Draft 预填格式：`处理 Draft -- Draft 名称：<标题>（Draft ID：<id>）`。

1. 从 Draft 预填消息中读取 `Draft ID`。
2. 调用 `read-db.py draft <DraftID>` 读取 Draft 正文、状态和时间。
3. 不要把 Inbox Markdown 路径当作数据源，也不要直接编辑投影文件。
4. 按 Draft 正文处理；处理完成后由用户在 Work Station 中决定是否转为任务。
5. 后续如需再次读取，继续使用 `draft <DraftID>`，不要依赖文档内容。

### 场景 J：重试一次写操作

1. 不要重新生成幂等键。
2. 使用第一次调用相同的 `--idempotency-key` 重试。
3. 读取目标实体验证最终状态；如果返回 `replayed=true`，说明没有重复写入。

## 汇报格式

- 任务 ID / 项目 ID
- 执行结果摘要
- 使用的读取方法链
- 使用的写入方法、幂等键、`command_id`、`audit_id`
- 验证方式和证据
- 遗留风险或待人工确认事项
