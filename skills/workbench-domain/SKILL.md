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
python3 $WB project get --name "<project>"
python3 $WB project list
python3 $WB draft list
python3 $WB session link --task-id <task-id> --sid "<session-id>" \
  --idempotency-key "<stable-key>" --reason "bind task session"
```

## Rules

- Read the task before changing it.
- Use a stable idempotency key for retries.
- Pass `--expected-status` when changing status.
- Do not bypass a conflict by overwriting state.
- Agent writes are restricted to configured command permissions.
- Markdown is a projection. SQLite is the source of truth.
- UI-only or high-risk commands must be completed by the user.
