# projects-workbench

Work Station 的本地数据与领域命令服务。SQLite 是唯一真相源，Markdown/vault 是只读投影；UI、Agent CLI、MCP 和 Codex skill 通过同一套领域命令读写业务数据。

## 架构

```text
Work Station UI ─┐
Codex CLI ───────┼─> Domain Command Layer
MCP Adapter ─────┤      ├─ Registry / Permissions
Codex Skill ─────┘      ├─ Handlers / State Validation
                        ├─ Idempotency / Audit
                        └─ Transaction Boundary
                                │
                                ▼
                           SQLite workbench.db
                                │
                                ▼
                       Projection Renderer
                                │
                                ▼
                          Markdown vault
```

核心原则：

1. 领域命令是唯一业务写入口。
2. Repository 是唯一数据库访问层。
3. Markdown 只由投影渲染器生成。
4. Agent 写操作必须带 `reason` 和 `idempotency_key`。
5. 状态更新使用 `expected_status` 做并发校验。
6. 业务写入、幂等记录和审计记录在同一 SQLite 事务提交。

## 主要入口

| 入口 | 作用 |
|---|---|
| `workbench-domain-service.py` | 领域命令进程入口，供本地 server 调用 |
| `wbctl.py` | Agent/脚本使用的领域 CLI |
| `workbench-mcp.py` | MCP stdio Adapter，当前保留，暂未在 Codex 注册 |
| `skills/project-workbench` | 唯一 Codex skill 源 |
| `tests/test_domain_service.py` | 权限、幂等、事务、Session 读命令测试 |

命令字典和权限矩阵：

```bash
python3 wbctl.py describe
```

## 命令模型

统一命令信封：

```json
{
  "command": "task.update_field",
  "version": 1,
  "actor": { "type": "agent", "id": "codex", "session_id": "..." },
  "target": { "task_id": "..." },
  "input": { "field": "status", "value": "Done" },
  "expected": { "status": "In-Progress" },
  "idempotency_key": "codex:thread:task:done",
  "reason": "acceptance passed"
}
```

常用命令：

```text
task.get / task.list / task.update_field / task.add_log / task.finish
project.get / project.list / project.update_field
draft.list / draft.create / draft.convert / draft.delete
session.link / session.unlink / session.list_for_project / session.counts
kanban.status / kanban.create / kanban.complete / kanban.dispatch
workbench.snapshot / system.describe
```

Agent 不暴露删除、创建项目和重命名等高风险命令。

## Agent CLI

```bash
python3 wbctl.py describe
python3 wbctl.py task get --task-id <task-id>
python3 wbctl.py task add-log --task-id <task-id> --text "<progress>" \
  --idempotency-key "<stable-key>" --reason "task progress"
python3 wbctl.py task finish --task-id <task-id> --expected-status In-Progress \
  --idempotency-key "<stable-key>" --reason "acceptance passed"
python3 wbctl.py session list-for-project --name "<project>"
```

读写链路：

```text
read-db.py -> wbctl.py -> DomainService -> SQLite
```

skill 内脚本不直接执行 SQL，也不直接读取 Markdown 投影。

## Codex Skill

仓库只维护一个 skill：

```text
skills/project-workbench/
  SKILL.md
  scripts/read-db.py
```

安装到 Codex：

```bash
ln -s \
  /Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/skills/project-workbench \
  /Users/ben/.codex/skills/project-workbench
```

不要创建第二个 `workbench-domain` 或 `workbench-ops` skill，避免方法目录和场景链漂移。

处理任务前必须读取：

- `goal`：任务目标
- `acceptance_criteria`：验收标准
- `task_detail`：任务详情
- `logs_yaml`：任务跟进记录

四项上下文全部读取后才允许开始执行。

## 数据与事务

- 写命令使用 `BEGIN IMMEDIATE`。
- 业务写入、`domain_commands`、`domain_audit` 在同一事务中提交。
- 投影渲染在事务提交后执行；失败进入重试队列。
- 相同幂等键并发请求只执行一次，重复请求返回首次结果。
- 业务失败会回滚业务写入和审计记录。

## 测试

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile wbctl.py skills/project-workbench/scripts/read-db.py
```

GitHub Actions 使用同一套领域层单测，不依赖 Codex 桌面环境。

## 兼容边界

- `workbench-service.py` 暂时保留给旧 Hermes 宿主兼容。
- Codex Work Station 不再调用 `/api/exec` 或旧 `run` 协议。
- `workbench-mcp.py` 已实现协议和工具定义，但暂未注册到 Codex；后续计划在 Hermes 内接入验证。
- 历史 Hermes `plugin.js` 不在当前 Codex-only 目标范围内。
