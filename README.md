# projects-workbench

Work Station 的本地数据与领域命令服务。SQLite 是唯一真相源，Markdown 是只读投影。

## 架构

```text
UI / CLI / MCP / Codex Skill
  -> Domain Command Layer
     -> Handlers / Repositories / Audit
        -> SQLite
        -> Projection Renderer
           -> Markdown vault
```

- 领域命令入口：`workbench-domain-service.py`
- Agent CLI：`wbctl.py`
- MCP Adapter：`workbench-mcp.py`
- 唯一 Codex skill：`skills/project-workbench`
- 领域层测试：`python3 -m unittest discover -s tests -v`

写操作统一带有 Actor、`reason`、幂等键、并发校验和审计记录；业务写入与命令记录在同一 SQLite 事务提交。

## Codex Skill 安装

只维护 `skills/project-workbench` 这一份 skill，不要额外创建 `workbench-domain` 或其他重复入口。将该目录链接到 Codex skill 根目录即可：

```bash
ln -s \
  /Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/skills/project-workbench \
  /Users/ben/.codex/skills/project-workbench
```

skill 内的 `scripts/read-db.py` 通过 `wbctl.py` 读取任务和项目，不直接查询 SQLite。写入通过 `wbctl.py` 的领域命令完成。
