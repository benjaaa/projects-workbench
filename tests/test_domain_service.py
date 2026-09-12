import os
import tempfile
import unittest
import sqlite3
import threading
import time

from domain.service import DomainService
from domain.mcp import MCPAdapter, tool_definitions
from db_transaction import current_transaction


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

    def update_section(self, path, section, text, changed_by=''):
        self.calls.append(('update_section', path, section, text, changed_by))
        return {'ok': True, 'version': 4}

    def toggle_ac(self, path, index, changed_by=''):
        self.calls.append(('toggle_ac', path, index, changed_by))
        return {'ok': True, 'version': 5}

    def _trigger_render(self, entity_type, entity_id):
        self.calls.append(('render', entity_type, entity_id))
        return {'ok': True, 'rendered': '/tmp/rendered.md'}

    def _log_change(self, entity_type, entity_id, field, old_value, new_value, changed_by=''):
        self.calls.append(('log_change', entity_type, entity_id, field, old_value, new_value, changed_by))

    def list_drafts(self, include_archived=True):
        return {'ok': True, 'items': []}

    def delete_draft(self, draft_id, changed_by=''):
        self.calls.append(('delete_draft', draft_id, changed_by))
        return {'ok': True, 'db_deleted': True, 'file_deleted': True}

    def _validate_sids(self, sids):
        return None


class SlowCore(FakeCore):
    def _validate_sids(self, sids):
        time.sleep(0.15)
        return None


class FailingCore(FakeCore):
    def set_property(self, path, field, value, changed_by=''):
        self.calls.append(('set_property', path, field, value, changed_by))
        tx = current_transaction()
        tx.connection.execute('CREATE TABLE IF NOT EXISTS effects (value TEXT)')
        tx.connection.execute('INSERT INTO effects(value) VALUES(?)', (field,))
        return {'ok': True, 'version': 2}

    def repeat_next(self, path, changed_by=''):
        self.calls.append(('repeat_next', path, changed_by))
        return {'ok': False, 'error': 'BOOM'}


class DomainServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp.close()
        conn = sqlite3.connect(self.temp.name)
        try:
            conn.execute('CREATE TABLE tasks (id TEXT PRIMARY KEY, version INTEGER, updated_at INTEGER)')
            conn.execute('CREATE TABLE log_entries (id TEXT PRIMARY KEY, task_id TEXT, date TEXT, type TEXT, summary TEXT, window TEXT, created_at INTEGER, updated_at INTEGER)')
            conn.execute('CREATE TABLE log_sessions (entry_id TEXT, sid TEXT, source TEXT)')
            conn.execute('CREATE TABLE log_detail (entry_id TEXT, kind TEXT, seq INTEGER, text TEXT, by TEXT)')
            conn.execute('INSERT INTO tasks(id, version, updated_at) VALUES(?,?,?)', ('task-1', 1, 0))
            conn.commit()
        finally:
            conn.close()
        self.core = FakeCore()
        self.service = DomainService(self.temp.name, core=self.core, reader=FakeReader())

    def tearDown(self):
        os.unlink(self.temp.name)


    def payload(self, command, input_data=None, expected=None, idem='', target=None):
        return {
            'command': command,
            'version': 1,
            'actor': {'type': 'agent', 'id': 'codex', 'session_id': 'thread-1'},
            'target': target or {'task_id': 'task-1'},
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
        self.assertIn('session.list_for_project', names)
        self.assertIn('session.counts', names)

    def test_agent_write_requires_idempotency_key(self):
        result = self.service.execute(self.payload('task.add_log', {'summary': 'test'}))
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'INVALID_ARGUMENT')
        self.assertEqual(self.core.calls, [])

    def test_agent_write_is_idempotent(self):
        payload = self.payload('task.add_log', {'summary': 'test'}, idem='task-1:test')
        first = self.service.execute(payload)
        second = self.service.execute(payload)
        self.assertTrue(first['ok'])
        self.assertTrue(second['ok'])
        self.assertTrue(second.get('replayed'))
        conn = sqlite3.connect(self.temp.name)
        try:
            count = conn.execute('SELECT COUNT(*) FROM log_entries').fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 1)

    def test_structured_log_details_are_written(self):
        payload = self.payload('task.add_log', {
            'summary': 'Structured progress',
            'sessions': [{'id': 'codex:t1', 'source': 'codex'}],
            'outputs': ['report.md'],
            'risks': ['risk one'],
            'pending': ['pending one'],
            'decisions': [{'desc': 'keep going', 'by': 'ben'}],
        }, idem='structured-log-1')
        result = self.service.execute(payload)
        self.assertTrue(result['ok'])
        conn = sqlite3.connect(self.temp.name)
        try:
            entry_id = conn.execute('SELECT id FROM log_entries').fetchone()[0]
            session_count = conn.execute('SELECT COUNT(*) FROM log_sessions WHERE entry_id=?', (entry_id,)).fetchone()[0]
            detail_count = conn.execute('SELECT COUNT(*) FROM log_detail WHERE entry_id=?', (entry_id,)).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(session_count, 1)
        self.assertEqual(detail_count, 4)

    def test_concurrent_same_idempotency_key_executes_once(self):
        core = SlowCore()
        payload = self.payload('task.add_log', {'summary': 'race', 'sessions': [{'id': 's1', 'source': 'codex'}]}, idem='race-key')
        barrier = threading.Barrier(2)
        results = []

        def invoke():
            service = DomainService(self.temp.name, core=core, reader=FakeReader())
            barrier.wait()
            results.append(service.execute(payload))

        threads = [threading.Thread(target=invoke) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)

        self.assertEqual(len(results), 2)
        self.assertTrue(all(result['ok'] for result in results))
        self.assertEqual(sum(1 for result in results if result.get('replayed')), 1)
        conn = sqlite3.connect(self.temp.name)
        try:
            count = conn.execute('SELECT COUNT(*) FROM log_entries').fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 1)

    def test_failed_write_rolls_back_business_effect_and_audit(self):
        TASK['repeat_mode'] = 'fixed'
        try:
            service = DomainService(self.temp.name, core=FailingCore(), reader=FakeReader())
            result = service.execute(self.payload('task.finish', idem='rollback-key'))
        finally:
            TASK['repeat_mode'] = ''

        self.assertFalse(result['ok'])
        conn = sqlite3.connect(self.temp.name)
        try:
            effects_table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='effects'").fetchone()
            command_count = conn.execute('SELECT COUNT(*) FROM domain_commands').fetchone()[0]
            audit_count = conn.execute('SELECT COUNT(*) FROM domain_audit').fetchone()[0]
        finally:
            conn.close()
        self.assertIsNone(effects_table)
        self.assertEqual(command_count, 0)
        self.assertEqual(audit_count, 0)

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

    def test_agent_can_update_task_content_and_acceptance(self):
        section = self.service.execute(self.payload('task.update_section', {'section': '任务详情', 'text': 'Body'}, idem='section-1'))
        acceptance = self.service.execute(self.payload('task.toggle_acceptance', {'index': 0}, idem='acceptance-1'))
        self.assertTrue(section['ok'])
        self.assertTrue(acceptance['ok'])
        self.assertEqual([call[0] for call in self.core.calls], ['update_section', 'toggle_ac'])

    def test_agent_cannot_rename_project_through_update_field(self):
        result = self.service.execute(self.payload(
            'project.update_field',
            {'field': 'name', 'value': 'Renamed'},
            idem='project-name-1',
            target={'project_id': 'project-1'},
        ))
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'FORBIDDEN')
        self.assertEqual(self.core.calls, [])

    def test_agent_can_request_projection_render(self):
        result = self.service.execute(self.payload('projection.render', idem='render-1'))
        self.assertTrue(result['ok'])
        self.assertEqual(self.core.calls[0][0], 'render')

    def test_project_session_reads_use_domain_commands(self):
        conn = sqlite3.connect(self.temp.name)
        try:
            conn.execute('CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT)')
            conn.execute('CREATE TABLE project_sessions (project_id TEXT, sid TEXT, linked_at INTEGER, source TEXT)')
            conn.execute('INSERT INTO projects(id, name) VALUES(?, ?)', ('project-1', 'Test Project'))
            conn.commit()
        finally:
            conn.close()

        sessions = self.service.execute(self.payload('session.list_for_project', target={'project_id': 'project-1'}))
        counts = self.service.execute(self.payload('session.counts'))
        self.assertTrue(sessions['ok'])
        self.assertEqual(sessions['result']['sessions'], [])
        self.assertTrue(counts['ok'])
        self.assertEqual(counts['result']['counts']['Test Project'], 0)

    def test_user_can_delete_draft_through_domain_command(self):
        payload = self.payload('draft.delete', {'draft_id': 'draft-1'}, idem='draft-delete-1')
        payload['actor'] = {'type': 'user', 'id': 'work-station'}
        result = self.service.execute(payload)
        self.assertTrue(result['ok'])
        self.assertEqual(self.core.calls[0], ('delete_draft', 'draft-1', 'user:work-station'))

    def test_user_can_update_draft_body_through_domain_command(self):
        conn = sqlite3.connect(self.temp.name)
        try:
            conn.execute('''CREATE TABLE drafts (
                id TEXT PRIMARY KEY, title TEXT, body TEXT, ts INTEGER, status TEXT,
                converted_task_id TEXT, created_at INTEGER, updated_at INTEGER, version INTEGER)
            ''')
            conn.execute('INSERT INTO drafts(id, title, body, status, version) VALUES(?,?,?,?,?)', ('draft-1', 'Draft one', 'Old body', 'open', 1))
            conn.commit()
        finally:
            conn.close()

        payload = self.payload('draft.update', {'draft_id': 'draft-1', 'body': 'New body'}, idem='draft-update-1')
        payload['actor'] = {'type': 'user', 'id': 'work-station'}
        result = self.service.execute(payload)
        self.assertTrue(result['ok'])
        self.assertEqual(result['result']['version'], 2)
        conn = sqlite3.connect(self.temp.name)
        try:
            body = conn.execute('SELECT body FROM drafts WHERE id=?', ('draft-1',)).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(body, 'New body')
        self.assertIn(('render', 'draft', 'draft-1'), self.core.calls)


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
