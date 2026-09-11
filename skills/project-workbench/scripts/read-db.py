#!/usr/bin/env python3
"""Read Work Station task/project data through the shared domain command CLI."""
import json
import os
import subprocess
import sys

WBCTL = os.environ.get(
    'WORKBENCH_WBCTL',
    os.path.expanduser('~/.hermes/profiles/business_analysis/desktop-plugins/projects-workbench/wbctl.py'),
)


def usage():
    print(__doc__, file=sys.stderr)


def parse_args(args):
    if not args or args[0] not in ('task', 'project', 'tasks'):
        return None
    kind = args[0]
    command = []
    i = 1
    if kind == 'task':
        command = ['task', 'get']
        while i < len(args):
            if args[i] == '--title' and i + 1 < len(args):
                command.extend(['--title', args[i + 1]])
                i += 2
            elif args[i] == '--project' and i + 1 < len(args):
                command.extend(['--project', args[i + 1]])
                i += 2
            else:
                command.extend(['--task-id', args[i]])
                i += 1
    elif kind == 'project':
        command = ['project', 'get']
        while i < len(args):
            if args[i] == '--name' and i + 1 < len(args):
                command.extend(['--name', args[i + 1]])
                i += 2
            else:
                command.extend(['--project-id', args[i]])
                i += 1
    else:
        command = ['task', 'list']
        while i < len(args):
            if args[i] == '--project' and i + 1 < len(args):
                command.extend(['--project', args[i + 1]])
                i += 2
            else:
                return None
    return command


def main():
    command = parse_args(sys.argv[1:])
    if not command:
        usage()
        return 2
    if not os.path.exists(WBCTL):
        print('read-db: wbctl.py not found: ' + WBCTL, file=sys.stderr)
        return 3
    proc = subprocess.run(
        [sys.executable, WBCTL, '--actor-id', 'codex-skill', *command],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    try:
        payload = json.loads(proc.stdout or '{}')
    except Exception:
        print('read-db: invalid domain response: ' + (proc.stdout or proc.stderr or '')[:300], file=sys.stderr)
        return 4
    if proc.returncode != 0 or not payload.get('ok'):
        error = payload.get('error') or {}
        print('read-db: ' + str(error.get('message') or error or proc.stderr or 'domain command failed'), file=sys.stderr)
        return 5
    result = {'ok': True}
    result.update(payload.get('result') or {})
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
