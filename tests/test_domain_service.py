import os
import tempfile
import unittest

from domain.service import DomainService
from domain.mcp import MCPAdapter, tool_definitions


TASK = {
    'id': 'task-1',
    'title': 'Domain command test',
    'project': 'Test Project',
    'dir': 'Test Project',
    'path': '2. Project/2.1 Project/Test Project/tasks/任务-Domain command test.md',
    'status': 'In-Progress',
    'priority': 'p1',
    'repeat_mode': '',
}


class FakeReader:
    def get_task(self, task_id):
        return dict(TASK) if task_id == TASK['id'] else None

    def load_tasks(self):
        return {'tasks': [dict(TASK)]}

    def get_project(self, project_id):
        return {'id': 'project-1', 'name': 'Test Project'} if project_id == 'project-1' else None

    def load_projects(self):
        return {'projects': [{'id': 'project-1', 'name': 'Test Project'}]}


class FakeCore:
    def __init__(self):
        self.calls = []

    def set_property(self, path, field, value, changed_by=''):
        self.calls.append(('set_property', path, field, value, changed_by))
        return {'ok': True, 'version': 2, 'rendered': '/tmp/task.md'}

    def add_log(self, path, text, changed_by=''):
        self.calls.append(('add_log', path, text, changed_by))
        return {'ok': True, 'version': 3, 'rendered': '/tmp/task.md'}

    def repeat_next(self, path, changed_by=''):
        self.calls.append(('repeat_next', path, changed_by))
        return {'ok': True, 'title': 'Next task', 'due': '2026-09-30'}

    def link_session(self, **kwargs):
        self.calls.append(('link_session', kwargs))
        return {'ok': True}

    def list_drafts(self, include_archived=True):
        return {'ok': True, 'items': []}


class DomainServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp.close()
        self.core = FakeCore()
        self.service = DomainService(self.temp.name, core=self.core, reader=FakeReader())

    def tearDown(self):
        os.unlink(self.temp.name)

    def payload(self, command, input_data=None, expected=None, idem=''):
        return {
            'command': command,
            'version': 1,
            'actor': {'type': 'agent', 'id': 'codex', 'session_id': 'thread-1'},
            'target': {'task_id': 'task-1'},
            'input': input_data or {},
            'expected': expected or {},
            'idempotency_key': idem,
            'reason': 'unit test',
        }

    def test_describe_returns_registered_commands(self):
        result = self.service.execute({'command': 'system.describe', 'version': 1, 'actor': {'type': 'system', 'id': 'test'}})
        self.assertTrue(result['ok'])
        names = {item['command'] for item in result['result']['commands']}
        self.assertIn('task.get', names)
        self.assertIn('task.finish', names)
        self.assertIn('session.link', names)

    def test_agent_write_requires_idempotency_key(self):
        result = self.service.execute(self.payload('task.add_log', {'text': 'test'}))
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'INVALID_ARGUMENT')
        self.assertEqual(self.core.calls, [])

    def test_agent_write_is_idempotent(self):
        payload = self.payload('task.add_log', {'text': 'test'}, idem='task-1:test')
        first = self.service.execute(payload)
        second = self.service.execute(payload)
        self.assertTrue(first['ok'])
        self.assertTrue(second['ok'])
        self.assertTrue(second.get('replayed'))
        self.assertEqual(len([call for call in self.core.calls if call[0] == 'add_log']), 1)

    def test_finish_rejects_expected_status_conflict(self):
        result = self.service.execute(self.payload('task.finish', expected={'status': 'open'}, idem='finish-1'))
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'CONFLICT')
        self.assertEqual(self.core.calls, [])

    def test_finish_updates_status_and_repeat(self):
        TASK['repeat_mode'] = 'fixed'
        try:
            result = self.service.execute(self.payload('task.finish', expected={'status': 'In-Progress'}, idem='finish-2'))
        finally:
            TASK['repeat_mode'] = ''
        self.assertTrue(result['ok'])
        self.assertEqual(result['result']['next_task'], 'Next task')
        self.assertEqual(self.core.calls[0][0], 'set_property')
        self.assertEqual(self.core.calls[0][3], 'Done')
        self.assertEqual(self.core.calls[1][0], 'repeat_next')

    def test_agent_cannot_update_title(self):
        result = self.service.execute(self.payload('task.update_field', {'field': 'title', 'value': 'Nope'}, idem='title-1'))
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'FORBIDDEN')
        self.assertEqual(self.core.calls, [])


class MCPAdapterTest(unittest.TestCase):
    class FakeService:
        def __init__(self):
            self.payload = None

        def execute(self, payload):
            self.payload = payload
            return {'ok': True}

    def test_mcp_tools_expose_safe_agent_commands(self):
        names = {tool['name'] for tool in tool_definitions()}
        self.assertIn('workbench_task_get', names)
        self.assertIn('workbench_task_add_log', names)
        self.assertNotIn('workbench_task_delete', names)
        self.assertNotIn('workbench_project_delete', names)

    def test_mcp_update_status_builds_domain_envelope(self):
        service = self.FakeService()
        adapter = MCPAdapter(service, actor_id='claude', session_id='thread-9')
        adapter.call_tool('workbench_task_update_status', {
            'task_id': 'task-1',
            'status': 'Done',
            'expected_status': 'In-Progress',
            'idempotency_key': 't1:done',
            'reason': 'acceptance passed',
        })
        self.assertEqual(service.payload['command'], 'task.update_field')
        self.assertEqual(service.payload['actor']['id'], 'claude')
        self.assertEqual(service.payload['input'], {'field': 'status', 'value': 'Done'})
        self.assertEqual(service.payload['expected'], {'status': 'In-Progress'})


if __name__ == '__main__':
    unittest.main()
