# projects-workbench 版本记录

## 2026-08-31 Issues 页 List 视图 + 统一过滤模型

### 变更（plugin.js）

- **Issues 双视图**：`BoardView` 重构为「过滤模型 + 双视图容器」，看板（原渲染逻辑不变）与新增 List 视图并行；右侧 `RoundBtn` 圆按钮切换，图标显示当前视图、点击切换，选择仅 session 内有效
- **List 视图**（参考 beUI Async Table 交互骨架，去虚拟化）：平铺无框体表格、sticky 表头、6 列可排序（状态/优先级按固定序，文本按 zh 字典序）、checkbox 行选择（单行/全选，选中行浅蓝底）、行点击开任务抽屉；列：Issue/优先级/状态/处理人/项目/截止日期
- **统一过滤模型**（两视图共用）：状态/优先级/处理人/项目/截止日期五字段多选；默认过滤 = 截止日期近7天 + 状态非已完成/取消（用户确认）。筛选入口为圆按钮弹层：一级字段 hover 出二级可选值，多选勾选即时生效；已选项聚合在白底描边大胶囊内（含单项 ✕ 移除、胶囊内 + 追加）；Clear 一键清空（无过滤时置灰）
- **原语层**：新增 `RoundBtn`（圆形、灰外框、透明底、hover 浅灰）与 `addDaysLocal` 日期助手；Issues 页头右上角固定 `+ New Issue`（从过滤栏迁出）
- **移除**：旧过滤栏（日期 input + 快捷 chips + Projects 下拉 + 处理人多选）

### 回滚

```bash
cd ~/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench
cp backups/plugin.js.bak-20260831-145226 plugin.js
# 在 Hermes 中 Reload 插件
```

---

## 当前版本：v2（2026-08-12 重写）

### 备份文件

| 文件 | 说明 |
|------|------|
| `obsidian-task.py.bak-20260812` | 重写前的 Python 后端（v1，38KB） |
| `plugin.js.bak-20260812` | 重写前的 JS 前端（v1，105KB） |

### 回滚方法

```bash
cd /Users/ben/.hermes/desktop-plugins/projects-workbench
cp obsidian-task.py.bak-20260812 obsidian-task.py
cp plugin.js.bak-20260812 plugin.js
# 在 Hermes 中 Reload 插件
```

---

### v2 变更清单

#### obsidian-task.py

| 修复 | 旧代码问题 | 新代码 |
|------|-----------|--------|
| P0: `query_log_op` 时间单位 | `created_at` 存毫秒，查询用秒 → 日期过滤永远不过滤 | 统一毫秒：`int(time.time()*1000) - int(days)*86400*1000` |
| P0: `set_property` 正则替换 | 正则替换破坏多行值和数组值 | 使用 `processFrontMatter` API |
| P1: 输入校验 | 无校验，任意值直接写入 | `validate_spec()` 校验 status/priority 枚举、必填字段、if_version 类型 |
| P1: 乐观锁 | 无并发保护 | `version` 字段 + `if_version` 校验 + 写入后自动递增 |
| P2: 代码去重 | `sessions`/`save_sessions` 各 ~30 行重复 | `_query_sessions()` 统一复用 |
| P2: 临时文件清理 | `/tmp/hpw_*` 永不清理 | `read` 读完时主动删除；`save` 分片文件不加入 atexit |
| P2: 大数据 stdin | `runSpec` 大 spec 通过命令行参数（ARG_MAX 限制） | `arg='-'` 走 stdin 模式 |

#### plugin.js

| 修复 | 旧代码问题 | 新代码 |
|------|-----------|--------|
| P0: `doSetField` 状态突变 | `t_.kanban_task_id = ''` 直接修改 React state 引用 | `Object.assign({}, t_, { kanban_task_id: '' })` 创建新对象 |
| P0: `createKanbanTask` 传旧引用 | `createKanbanTask(t_)` 传旧对象 | `createKanbanTask(updated)` 传更新后对象 |
| P1: 回滚日志 | `doSetField` 失败只 toast 无日志 | 加 `console.error('[pw] ...')` |
| P1: 20+ 静默吞错 | `.catch(function() {})` | 全部改为 `.catch(function(e) { console.error('[pw] ...', e) })` |
| P2: `runSpec` 大数据 | 所有 spec 走命令行参数 | >8KB 自动走 stdin（`sh` 支持 `stdin` 参数） |
| P2: Drawer 直接修改 | `t.task_detail = v` / `t.logs[i].text = v` / `t.acceptance_criteria[i] = na` / `task.session_ids = ...` | 移除直接修改，改用 `setForce`/`setDw(Object.assign({}, t, ...))` |

### v2 修复的已知 bug

1. **atexit 清理竞态**（重写引入，已修复）：`atexit` 在 `save` 进程退出时删除临时文件，但 `read` 是另一个进程需要读 → `Unexpected end of JSON input`。修复：`save`/`save_sessions` 分片文件不加入 `_tmp_files`，由 `read` 自行清理。

2. **read 分片并发删除竞态**（已修复）：`read` 模式最后一个分片读完时删除文件，但 `Promise.all` 并发读取时其他分片可能还没打开 → `FileNotFoundError` → 数据不完整。修复：`read`/`read_sessions` 不再删除文件，改为 `save` 时清理超过 5 分钟的旧文件。

3. **obsidian eval 超时未处理**（已修复）：`run()` 函数未捕获 `subprocess.TimeoutExpired`，导致 `save` 模式崩溃 → `ld()` 重试耗尽 → 报错。修复：`run()` 捕获超时返回 `-1` 退出码。

4. **create_project 输入校验误拦**（已修复）：`validate_spec` 把 `create_project` 归入 `path_ops` 要求 `path` 字段，但 `create_project` 用 `dir`。修复：从 `path_ops` 中移除，单独校验 `dir`。

5. **runSpec stdin 模式无效**（已修复）：`host.request('shell.exec')` 不支持 `stdin` 参数，但大数据走 stdin 模式时传入 `json` 参数被忽略 → Python 收到空 stdin → `atob` 解码失败。修复：回退到纯 base64 命令行参数。

6. **首页看板已完成任务受截止日期过滤**（已修复）：`Done`/`Dropped` 状态的任务也受 `cutoffDate` 过滤，导致已完成的近期任务不显示。修复：已完成任务跳过截止日期过滤。

7. **pts 匹配不完整**（已修复）：`pts(proj)` 仅匹配 `project`/`dir` 等于 `proj`，但 `project` 可能用项目的 title 而 `dir` 用目录名（如 `短任务` vs `临时任务`），导致部分任务不显示。修复：4 路交叉匹配（project/dir × title/dir）。
