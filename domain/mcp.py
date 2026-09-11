import json
import os

from .models import CommandEnvelope


TOOL_SPECS = [
    {
        'name': 'workbench_describe',
        'description': 'List available Work Station domain commands and permissions.',
        'command': 'system.describe',
        'write': False,
        'properties': {},
        'required': [],
    },
    {
        'name': 'workbench_task_get',
        'description': 'Get one Work Station task.',
        'command': 'task.get',
        'write': False,
        'properties': {
            'task_id': {'type': 'string'},
            'title': {'type': 'string'},
            'project': {'type': 'string'},
            'path': {'type': 'string'},
        },
        'required': [],
    },
    {
        'name': 'workbench_task_list',
        'description': 'List Work Station tasks.',
        'command': 'task.list',
        'write': False,
        'properties': {
            'project': {'type': 'string'},
            'status': {'type': 'string'},
            'limit': {'type': 'integer'},
        },
        'required': [],
    },
    {
        'name': 'workbench_task_update_status',
        'description': 'Update a task status with expected-status conflict protection.',
        'command': 'task.update_field',
        'write': True,
        'properties': {
            'task_id': {'type': 'string'},
            'title': {'type': 'string'},
            'project': {'type': 'string'},
            'path': {'type': 'string'},
            'status': {'type': 'string'},
            'expected_status': {'type': 'string'},
            'idempotency_key': {'type': 'string'},
            'reason': {'type': 'string'},
        },
        'required': ['status', 'idempotency_key', 'reason'],
    },
    {
        'name': 'workbench_task_finish',
        'description': 'Mark a task done and generate the next repeat task when applicable.',
        'command': 'task.finish',
        'write': True,
        'properties': {
            'task_id': {'type': 'string'},
            'title': {'type': 'string'},
            'project': {'type': 'string'},
            'path': {'type': 'string'},
            'expected_status': {'type': 'string'},
            'idempotency_key': {'type': 'string'},
            'reason': {'type': 'string'},
        },
        'required': ['idempotency_key', 'reason'],
    },
    {
        'name': 'workbench_task_add_log',
        'description': 'Append a task progress log.',
        'command': 'task.add_log',
        'write': True,
        'properties': {
            'task_id': {'type': 'string'},
            'title': {'type': 'string'},
            'project': {'type': 'string'},
            'path': {'type': 'string'},
            'text': {'type': 'string'},
            'idempotency_key': {'type': 'string'},
            'reason': {'type': 'string'},
        },
        'required': ['text', 'idempotency_key', 'reason'],
    },
    {
        'name': 'workbench_project_get',
        'description': 'Get one Work Station project.',
        'command': 'project.get',
        'write': False,
        'properties': {
            'project_id': {'type': 'string'},
            'name': {'type': 'string'},
            'path': {'type': 'string'},
        },
        'required': [],
    },
    {
        'name': 'workbench_project_list',
        'description': 'List Work Station projects.',
        'command': 'project.list',
        'write': False,
        'properties': {
            'status': {'type': 'string'},
            'limit': {'type': 'integer'},
        },
        'required': [],
    },
    {
        'name': 'workbench_draft_list',
        'description': 'List Work Station Drafts.',
        'command': 'draft.list',
        'write': False,
        'properties': {
            'include_archived': {'type': 'boolean'},
        },
        'required': [],
    },
    {
        'name': 'workbench_session_link',
        'description': 'Link a session to a task through the domain command layer.',
        'command': 'session.link',
        'write': True,
        'properties': {
            'task_id': {'type': 'string'},
            'title': {'type': 'string'},
            'project': {'type': 'string'},
            'path': {'type': 'string'},
            'sid': {'type': 'string'},
            'source': {'type': 'string'},
            'idempotency_key': {'type': 'string'},
            'reason': {'type': 'string'},
        },
        'required': ['sid', 'idempotency_key', 'reason'],
    },
]

TOOL_BY_NAME = {item['name']: item for item in TOOL_SPECS}


def tool_definitions():
    tools = []
    for spec in TOOL_SPECS:
        tools.append({
            'name': spec['name'],
            'description': spec['description'],
            'inputSchema': {
                'type': 'object',
                'properties': spec['properties'],
                'required': spec['required'],
                'additionalProperties': True,
            },
        })
    return tools


class MCPAdapter:
    def __init__(self, service, actor_id=None, session_id=None):
        self.service = service
        self.actor_id = actor_id or os.environ.get('WORKBENCH_AGENT_ID', 'codex')
        self.session_id = session_id if session_id is not None else os.environ.get('CODEX_THREAD_ID', '')

    def call_tool(self, name, arguments=None):
        spec = TOOL_BY_NAME.get(name)
        if not spec:
            return {'ok': False, 'error': {'code': 'INVALID_COMMAND', 'message': f'unknown tool: {name}'}}
        args = dict(arguments or {})
        target_keys = {'task_id', 'title', 'project', 'project_id', 'name', 'path'}
        target = {key: args.pop(key) for key in list(args.keys()) if key in target_keys and args.get(key) not in (None, '')}
        expected = {}
        if args.get('expected_status'):
            expected['status'] = args.pop('expected_status')
        idempotency_key = args.pop('idempotency_key', '')
        reason = args.pop('reason', '')
        input_data = args
        if spec['command'] == 'task.update_field':
            input_data = {'field': 'status', 'value': input_data.get('status')}
        payload = {
            'command': spec['command'],
            'version': 1,
            'actor': {'type': 'agent', 'id': self.actor_id, 'session_id': self.session_id},
            'target': target,
            'input': input_data,
            'expected': expected,
            'idempotency_key': idempotency_key if spec['write'] else '',
            'reason': reason,
        }
        return self.service.execute(payload)

    @staticmethod
    def mcp_result(response):
        text = json.dumps(response, ensure_ascii=False, indent=2)
        return {
            'content': [{'type': 'text', 'text': text}],
            'isError': not bool(response.get('ok')),
        }
