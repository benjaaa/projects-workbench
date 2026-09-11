#!/usr/bin/env python3
"""wbctl - Agent-facing adapter for Work Station domain commands."""
import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from domain.service import DomainService  # noqa: E402


def output(result):
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('ok') else 1


def add_actor_args(parser):
    parser.add_argument('--actor-id', default='codex')
    parser.add_argument('--session', default=os.environ.get('CODEX_THREAD_ID', ''))


def task_target(args):
    target = {}
    if getattr(args, 'task_id', ''):
        target['task_id'] = args.task_id
    else:
        target['title'] = getattr(args, 'title', '')
        target['project'] = getattr(args, 'project', '')
    return target


def build_execute(args, command, target=None, input_data=None, write=False):
    payload = {
        'command': command,
        'version': 1,
        'actor': {
            'type': 'agent',
            'id': args.actor_id,
            'session_id': args.session,
        },
        'target': target or {},
        'input': input_data or {},
        'expected': getattr(args, 'expected', {}) or {},
        'reason': getattr(args, 'reason', '') or '',
    }
    if write:
        payload['idempotency_key'] = args.idempotency_key
    return payload


def add_write_args(parser):
    parser.add_argument('--idempotency-key', required=True)
    parser.add_argument('--reason', required=True)


def add_task_locator(parser):
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--task-id')
    group.add_argument('--title')
    parser.add_argument('--project', default='')


def project_target(args):
    if getattr(args, 'project_id', ''):
        return {'project_id': args.project_id}
    return {'name': getattr(args, 'name', '')}


def add_project_locator(parser):
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--project-id')
    group.add_argument('--name')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_actor_args(parser)
    sub = parser.add_subparsers(dest='resource', required=True)
    sub.add_parser('describe')

    task = sub.add_parser('task')
    task_sub = task.add_subparsers(dest='action', required=True)

    p = task_sub.add_parser('get')
    add_task_locator(p)

    p = task_sub.add_parser('update-field')
    add_task_locator(p)
    p.add_argument('--field', required=True)
    p.add_argument('--value', required=True)
    add_write_args(p)

    p = task_sub.add_parser('toggle-acceptance')
    add_task_locator(p)
    p.add_argument('--index', type=int, required=True)
    add_write_args(p)

    p = task_sub.add_parser('update-section')
    add_task_locator(p)
    p.add_argument('--section', required=True)
    p.add_argument('--text', required=True)
    add_write_args(p)

    p = task_sub.add_parser('list')
    p.add_argument('--project', default='')
    p.add_argument('--status', default='')
    p.add_argument('--limit', type=int, default=200)

    p = task_sub.add_parser('update-status')
    add_task_locator(p)
    p.add_argument('--status', required=True)
    p.add_argument('--expected-status', dest='expected_status', default='')
    add_write_args(p)

    p = task_sub.add_parser('finish')
    add_task_locator(p)
    p.add_argument('--expected-status', dest='expected_status', default='In-Progress')
    add_write_args(p)

    p = task_sub.add_parser('add-log')
    add_task_locator(p)
    p.add_argument('--text', required=True)
    add_write_args(p)

    project = sub.add_parser('project')
    project_sub = project.add_subparsers(dest='action', required=True)
    p = project_sub.add_parser('get')
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--project-id')
    group.add_argument('--name')
    p = project_sub.add_parser('list')
    p.add_argument('--status', default='')
    p.add_argument('--limit', type=int, default=200)

    p = project_sub.add_parser('update-field')
    add_project_locator(p)
    p.add_argument('--field', required=True)
    p.add_argument('--value', required=True)
    add_write_args(p)

    p = project_sub.add_parser('update-section')
    add_project_locator(p)
    p.add_argument('--section', required=True)
    p.add_argument('--text', required=True)
    add_write_args(p)

    draft = sub.add_parser('draft')
    draft_sub = draft.add_subparsers(dest='action', required=True)
    p = draft_sub.add_parser('list')
    p.add_argument('--include-archived', action='store_true', default=True)

    projection = sub.add_parser('projection')
    projection_sub = projection.add_subparsers(dest='action', required=True)
    p = projection_sub.add_parser('render')
    locator = p.add_mutually_exclusive_group(required=True)
    locator.add_argument('--task-id')
    locator.add_argument('--project-id')
    locator.add_argument('--path')
    add_write_args(p)

    session = sub.add_parser('session')
    session_sub = session.add_subparsers(dest='action', required=True)
    p = session_sub.add_parser('link')
    add_task_locator(p)
    p.add_argument('--sid', required=True)
    p.add_argument('--source', default='codex')
    add_write_args(p)

    p = session_sub.add_parser('list-for-project')
    add_project_locator(p)

    p = session_sub.add_parser('counts')

    p = session_sub.add_parser('codex-titles')
    p.add_argument('--ids', required=True, help='comma-separated Codex thread ids')

    args = parser.parse_args()
    service = DomainService(os.path.join(SCRIPT_DIR, 'workbench.db'))

    if args.resource == 'describe':
        payload = {'command': 'system.describe', 'version': 1, 'actor': {'type': 'agent', 'id': args.actor_id, 'session_id': args.session}}
    elif args.resource == 'task' and args.action == 'get':
        payload = build_execute(args, 'task.get', task_target(args))
    elif args.resource == 'task' and args.action == 'update-field':
        payload = build_execute(args, 'task.update_field', task_target(args), {'field': args.field, 'value': args.value}, write=True)
    elif args.resource == 'task' and args.action == 'toggle-acceptance':
        payload = build_execute(args, 'task.toggle_acceptance', task_target(args), {'index': args.index}, write=True)
    elif args.resource == 'task' and args.action == 'update-section':
        payload = build_execute(args, 'task.update_section', task_target(args), {'section': args.section, 'text': args.text}, write=True)
    elif args.resource == 'task' and args.action == 'list':
        payload = build_execute(args, 'task.list', input_data={'project': args.project, 'status': args.status, 'limit': args.limit})
    elif args.resource == 'task' and args.action == 'update-status':
        expected = {'status': args.expected_status} if args.expected_status else {}
        args.expected = expected
        payload = build_execute(args, 'task.update_field', task_target(args), {'field': 'status', 'value': args.status}, write=True)
    elif args.resource == 'task' and args.action == 'finish':
        args.expected = {'status': args.expected_status} if args.expected_status else {}
        payload = build_execute(args, 'task.finish', task_target(args), write=True)
    elif args.resource == 'task' and args.action == 'add-log':
        payload = build_execute(args, 'task.add_log', task_target(args), {'text': args.text}, write=True)
    elif args.resource == 'project' and args.action == 'get':
        target = {'project_id': args.project_id} if args.project_id else {'name': args.name}
        payload = build_execute(args, 'project.get', target)
    elif args.resource == 'project' and args.action == 'update-field':
        payload = build_execute(args, 'project.update_field', project_target(args), {'field': args.field, 'value': args.value}, write=True)
    elif args.resource == 'project' and args.action == 'update-section':
        payload = build_execute(args, 'project.update_section', project_target(args), {'section': args.section, 'text': args.text}, write=True)
    elif args.resource == 'project' and args.action == 'list':
        payload = build_execute(args, 'project.list', input_data={'status': args.status, 'limit': args.limit})
    elif args.resource == 'draft' and args.action == 'list':
        payload = build_execute(args, 'draft.list', input_data={'include_archived': args.include_archived})
    elif args.resource == 'projection' and args.action == 'render':
        if args.task_id:
            target = {'task_id': args.task_id}
        elif args.project_id:
            target = {'project_id': args.project_id}
        else:
            target = {'path': args.path}
        payload = build_execute(args, 'projection.render', target, write=True)
    elif args.resource == 'session' and args.action == 'link':
        payload = build_execute(args, 'session.link', task_target(args), {'sid': args.sid, 'source': args.source}, write=True)
    elif args.resource == 'session' and args.action == 'list-for-project':
        payload = build_execute(args, 'session.list_for_project', project_target(args))
    elif args.resource == 'session' and args.action == 'counts':
        payload = build_execute(args, 'session.counts')
    elif args.resource == 'session' and args.action == 'codex-titles':
        ids = [value.strip() for value in args.ids.split(',') if value.strip()]
        payload = build_execute(args, 'session.codex_titles', input_data={'ids': ids})
    else:
        return output({'ok': False, 'error': {'code': 'INVALID_COMMAND', 'message': 'unsupported command'}})

    return output(service.execute(payload))


if __name__ == '__main__':
    raise SystemExit(main())
