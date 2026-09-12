import json
import os
import sqlite3
import tempfile
import unittest

from domain import codex_session, repositories
from domain.service import DomainService


TASK = {
    'id': 'task-1',
    'title': 'Review test task',
    'project': 'Test',
    'dir': 'Test',
    'status': 'In-Progress',
    'priority': 'p1',
    'created_at': 900,
    'created': 900,
    'path': '2. Project/2.1 Project/Test/tasks/任务-Review test task.md',
}


class FakeReader:
    def get_task(self, task_id):
        return dict(TASK) if task_id == TASK['id'] else None

    def load_tasks(self):
        return {'tasks': [dict(TASK)]}

    def get_project(self, project_id):
        return None

    def load_projects(self):
        return {'projects': []}


class FakeCore:
    def _trigger_render(self, entity_type, entity_id):
        return {'ok': True, 'rendered': '/tmp/review-task.md'}

    def _log_change(self, *args, **kwargs):
        return None


class ReviewWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.wb_path = os.path.join(self.tempdir.name, 'workbench.db')
        self.codex_path = os.path.join(self.tempdir.name, 'state_5.sqlite')
        self.rollout_path = os.path.join(self.tempdir.name, 'rollout.jsonl')
        self._create_workbench_db()
        self._create_codex_db()
        self.old_codex_db = repositories.CODEX_DB
        repositories.CODEX_DB = self.codex_path
        self.service = DomainService(self.wb_path, core=FakeCore(), reader=FakeReader())

    def tearDown(self):
        repositories.CODEX_DB = self.old_codex_db
        self.tempdir.cleanup()

    def _create_workbench_db(self):
        conn = sqlite3.connect(self.wb_path)
        try:
            conn.executescript('''
                CREATE TABLE tasks (
                    id TEXT PRIMARY KEY, project_id TEXT, title TEXT, status TEXT,
                    priority TEXT, version INTEGER, goal TEXT, body TEXT,
                    acceptance TEXT, created_at INTEGER, updated_at INTEGER
                );
                CREATE TABLE task_sessions (
                    task_id TEXT, sid TEXT, linked_at INTEGER, source TEXT,
                    PRIMARY KEY (task_id, sid)
                );
                CREATE TABLE log_entries (
                    id TEXT PRIMARY KEY, task_id TEXT, date TEXT, type TEXT,
                    summary TEXT, window TEXT, created_at INTEGER, updated_at INTEGER
                );
                CREATE TABLE log_detail (
                    entry_id TEXT, kind TEXT, seq INTEGER, text TEXT, by TEXT,
                    PRIMARY KEY (entry_id, kind, seq)
                );
                CREATE TABLE log_sessions (
                    entry_id TEXT, sid TEXT, source TEXT,
                    PRIMARY KEY (entry_id, sid)
                );
                INSERT INTO tasks(id, project_id, title, status, priority, version, created_at, updated_at)
                VALUES('task-1', 'project-1', 'Review test task', 'In-Progress', 'p1', 1, 900, 900);
                INSERT INTO task_sessions(task_id, sid, linked_at, source)
                VALUES('task-1', 'codex:thread-1', 950, 'codex');
            ''')
            conn.commit()
        finally:
            conn.close()

    def _create_codex_db(self, updated_at=1500):
        conn = sqlite3.connect(self.codex_path)
        try:
            conn.execute('DROP TABLE IF EXISTS threads')
            conn.execute('''CREATE TABLE threads (
                id TEXT PRIMARY KEY, rollout_path TEXT, archived INTEGER,
                created_at INTEGER, updated_at INTEGER, title TEXT, name TEXT
            )''')
            conn.execute(
                'INSERT INTO threads(id, rollout_path, archived, created_at, updated_at, title, name) VALUES(?,?,?,?,?,?,?)',
                ('thread-1', self.rollout_path, 1, 1000, updated_at, 'Archived review thread', ''),
            )
            conn.commit()
        finally:
            conn.close()

    def _write_rollout(self):
        rows = [
            {'timestamp': 1100, 'type': 'event_msg', 'payload': {'type': 'task_started', 'turn_id': 'turn-1', 'started_at': 1100}},
            {
                'timestamp': 1101,
                'type': 'response_item',
                'payload': {
                    'type': 'message', 'role': 'developer',
                    'content': [{'type': 'input_text', 'text': 'system instructions'}],
                },
            },
            {
                'timestamp': 1102,
                'type': 'response_item',
                'payload': {
                    'type': 'message', 'role': 'user',
                    'content': [{'type': 'input_text', 'text': '# AGENTS.md instructions'}],
                    'internal_chat_message_metadata_passthrough': {'content_item_kinds': ['agents_md.instructions']},
                },
            },
            {
                'timestamp': 1103,
                'type': 'response_item',
                'payload': {
                    'type': 'message', 'role': 'user',
                    'content': [{'type': 'input_text', 'text': 'Do the task'}],
                    'internal_chat_message_metadata_passthrough': {'turn_id': 'turn-1', 'content_item_kinds': ['user.text']},
                },
            },
            {
                'timestamp': 1104,
                'type': 'response_item',
                'payload': {
                    'type': 'reasoning', 'summary': [{'type': 'summary_text', 'text': 'Use the domain command layer.'}],
                    'internal_chat_message_metadata_passthrough': {'turn_id': 'turn-1'},
                },
            },
            {'timestamp': 1105, 'type': 'response_item', 'payload': {'type': 'function_call', 'name': 'exec_command'}},
            {'timestamp': 1106, 'type': 'response_item', 'payload': {'type': 'function_call_output', 'output': 'raw output'}},
            {
                'timestamp': 1107,
                'type': 'event_msg',
                'payload': {
                    'type': 'item_completed', 'turn_id': 'turn-1',
                    'item': {
                        'type': 'FileChange', 'status': 'completed',
                        'changes': {'/tmp/result.md': {'type': 'add'}},
                    },
                },
            },
            {
                'timestamp': 1108,
                'type': 'event_msg',
                'payload': {
                    'type': 'task_complete', 'turn_id': 'turn-1',
                    'last_agent_message': 'Final answer', 'completed_at': 1108,
                },
            },
        ]
        with open(self.rollout_path, 'w', encoding='utf-8') as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + '\n')

    def payload(self, command, input_data=None, idem='', target=None):
        return {
            'command': command,
            'version': 1,
            'actor': {'type': 'agent', 'id': 'codex', 'session_id': 'review-thread'},
            'target': target or {'task_id': 'task-1'},
            'input': input_data or {},
            'expected': {},
            'idempotency_key': idem,
            'reason': 'review test',
        }

    def test_reader_keeps_final_user_and_reasoning_summary_only(self):
        self._write_rollout()
        result = codex_session.read_rollout(self.rollout_path, 1000, 2000)
        self.assertEqual(len(result['turns']), 1)
        turn = result['turns'][0]
        self.assertEqual([item['text'] for item in turn['user']], ['Do the task'])
        self.assertEqual(turn['assistant_final'], 'Final answer')
        self.assertEqual([item['text'] for item in turn['reasoning_summary']], ['Use the domain command layer.'])
        self.assertEqual(turn['artifacts'][0]['path'], '/tmp/result.md')
        self.assertNotIn('system instructions', json.dumps(result, ensure_ascii=False))

    def test_prepare_and_commit_create_one_task_level_review(self):
        self._write_rollout()
        prepared = self.service.execute(self.payload('review.prepare', {
            'window_start': 1000,
            'window_end': 2000,
        }))
        self.assertTrue(prepared['ok'])
        result = prepared['result']
        self.assertEqual(result['coverage']['candidate_sessions'], 1)
        self.assertTrue(result['sessions'][0]['archived'])
        sid = result['sessions'][0]['session_id']

        commit = self.payload('review.commit', {
            'run_id': result['run_id'],
            'window_start': 1000,
            'window_end': 2000,
            'summary': 'Merged task review',
            'outputs': ['result.md'],
            'pending': ['Confirm result'],
            'method': ['Used the domain command layer'],
            'sessions': [{'id': sid, 'source': 'codex'}],
            'session_digests': [{
                'session_id': sid,
                'status': 'completed',
                'archived': True,
                'updated_at': 1500,
                'summary': 'Session summary',
                'coverage': result['coverage'],
            }],
            'coverage': result['coverage'],
        }, idem='review-commit-1')
        first = self.service.execute(commit)
        second = self.service.execute(commit)
        self.assertTrue(first['ok'])
        self.assertTrue(second.get('replayed'))

        conn = sqlite3.connect(self.wb_path)
        try:
            entry_count = conn.execute('SELECT COUNT(*) FROM log_entries').fetchone()[0]
            method_count = conn.execute("SELECT COUNT(*) FROM log_detail WHERE kind='method'").fetchone()[0]
            run_status = conn.execute('SELECT status FROM review_runs').fetchone()[0]
            digest_count = conn.execute('SELECT COUNT(*) FROM review_session_results').fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(entry_count, 1)
        self.assertEqual(method_count, 1)
        self.assertEqual(run_status, 'completed')
        self.assertEqual(digest_count, 1)

        cursor = repositories.latest_completed_review(self.wb_path, 'task-1')
        self.assertEqual(cursor['window_end'], 2000)

    def test_sessions_without_updates_are_not_read(self):
        self._create_codex_db(updated_at=500)
        prepared = self.service.execute(self.payload('review.prepare', {
            'window_start': 1000,
            'window_end': 2000,
        }))
        self.assertTrue(prepared['ok'])
        self.assertEqual(prepared['result']['sessions'], [])
        self.assertEqual(prepared['result']['coverage']['candidate_sessions'], 0)
        self.assertEqual(prepared['result']['skipped_sessions'][0]['reason'], 'not_updated_in_window')

    def test_partial_commit_does_not_advance_review_cursor(self):
        self._write_rollout()
        prepared = self.service.execute(self.payload('review.prepare', {
            'window_start': 1000,
            'window_end': 2000,
        })).get('result') or {}
        sid = prepared['sessions'][0]['session_id']
        payload = self.payload('review.commit', {
            'run_id': prepared['run_id'],
            'window_start': 1000,
            'window_end': 2000,
            'summary': 'Partial review',
            'sessions': [{'id': sid}],
            'session_digests': [{
                'session_id': sid,
                'status': 'completed',
                'coverage': prepared['coverage'],
            }],
            'coverage': {**prepared['coverage'], 'failed_sessions': 1},
        }, idem='review-partial-1')
        result = self.service.execute(payload)
        self.assertTrue(result['ok'])
        self.assertEqual(result['result']['status'], 'partial')
        self.assertIsNone(repositories.latest_completed_review(self.wb_path, 'task-1'))


if __name__ == '__main__':
    unittest.main()
