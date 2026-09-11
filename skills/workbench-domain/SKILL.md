# Workbench Domain Commands

Use `wbctl.py` for Work Station task and project operations. It calls the same
domain command layer as the Work Station UI.

Do not edit `workbench.db`, task Markdown files, project Markdown files, or
frontmatter directly.

## Commands

```bash
WB=/Users/ben/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/wbctl.py

python3 $WB describe
python3 $WB task get --task-id <task-id>
python3 $WB task list --project "<project>" --status In-Progress
python3 $WB task update-status --task-id <task-id> --status Done \
  --expected-status In-Progress --idempotency-key "<stable-key>" \
  --reason "task completed"
python3 $WB task finish --task-id <task-id> --expected-status In-Progress \
  --idempotency-key "<stable-key>" --reason "acceptance passed"
python3 $WB task add-log --task-id <task-id> --text "<progress>" \
  --idempotency-key "<stable-key>" --reason "task progress"
python3 $WB task update-field --task-id <task-id> --field priority --value p1 \
  --idempotency-key "<stable-key>" --reason "priority changed"
python3 $WB task toggle-acceptance --task-id <task-id> --index 0 \
  --idempotency-key "<stable-key>" --reason "acceptance checked"
python3 $WB task update-section --task-id <task-id> --section "任务详情" --text "<full text>" \
  --idempotency-key "<stable-key>" --reason "task detail updated"
python3 $WB project get --name "<project>"
python3 $WB project list
python3 $WB project update-field --name "<project>" --field status --value In-Progress \
  --idempotency-key "<stable-key>" --reason "project status changed"
python3 $WB draft list
python3 $WB session link --task-id <task-id> --sid "<session-id>" \
  --idempotency-key "<stable-key>" --reason "bind task session"
python3 $WB projection render --task-id <task-id> \
  --idempotency-key "<stable-key>" --reason "manual projection refresh"
```

## Rules

- Read the task before changing it.
- Use a stable idempotency key for retries.
- Pass `--expected-status` when changing status.
- Do not bypass a conflict by overwriting state.
- Agent writes are restricted to configured command permissions.
- Agent-safe field updates are limited to task status/priority/handler/start/due and project status/start/due/complete.
- Task detail, goal and acceptance updates are allowed through the domain layer; rename and delete remain user-only.
- Markdown is a projection. SQLite is the source of truth.
- UI-only or high-risk commands must be completed by the user.
