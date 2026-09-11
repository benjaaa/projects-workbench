import json
import sqlite3
import time


class CommandStore:
    """Persistence for command audit and idempotency records."""

    def __init__(self, db_path):
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _finish(conn, owned):
        if owned:
            conn.close()

    def _ensure_schema(self):
        conn = self._connect()
        try:
            conn.execute('''CREATE TABLE IF NOT EXISTS domain_commands (
                command_id TEXT PRIMARY KEY,
                idempotency_key TEXT UNIQUE,
                actor_type TEXT NOT NULL,
                actor_id TEXT DEFAULT '',
                session_id TEXT DEFAULT '',
                command TEXT NOT NULL,
                command_version INTEGER NOT NULL,
                target_json TEXT NOT NULL,
                input_json TEXT NOT NULL,
                reason TEXT DEFAULT '',
                result_json TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )''')
            conn.execute('''CREATE TABLE IF NOT EXISTS domain_audit (
                audit_id TEXT PRIMARY KEY,
                command_id TEXT NOT NULL,
                actor_type TEXT NOT NULL,
                actor_id TEXT DEFAULT '',
                session_id TEXT DEFAULT '',
                command TEXT NOT NULL,
                command_version INTEGER NOT NULL,
                target_json TEXT NOT NULL,
                input_json TEXT NOT NULL,
                expected_json TEXT NOT NULL,
                reason TEXT DEFAULT '',
                result_json TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )''')
            conn.commit()
        finally:
            conn.close()

    def find_idempotent(self, key, conn=None):
        if not key:
            return None
        owned = conn is None
        conn = conn or self._connect()
        try:
            row = conn.execute(
                'SELECT command, result_json FROM domain_commands WHERE idempotency_key=?',
                (key,),
            ).fetchone()
            if not row:
                return None
            return {'command': row['command'], 'result': json.loads(row['result_json'])}
        finally:
            self._finish(conn, owned)

    def save(self, envelope, audit_id, result, conn=None):
        payload = json.dumps(result, ensure_ascii=False, separators=(',', ':'))
        now = int(time.time())
        owned = conn is None
        conn = conn or self._connect()
        try:
            conn.execute(
                '''INSERT INTO domain_commands(
                    command_id, idempotency_key, actor_type, actor_id, session_id,
                    command, command_version, target_json, input_json, reason,
                    result_json, created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                (
                    envelope.command_id,
                    envelope.idempotency_key or None,
                    envelope.actor.type,
                    envelope.actor.id,
                    envelope.actor.session_id,
                    envelope.command,
                    envelope.version,
                    json.dumps(envelope.target, ensure_ascii=False, separators=(',', ':')),
                    json.dumps(envelope.input, ensure_ascii=False, separators=(',', ':')),
                    envelope.reason,
                    payload,
                    now,
                ),
            )
            conn.execute(
                '''INSERT INTO domain_audit(
                    audit_id, command_id, actor_type, actor_id, session_id,
                    command, command_version, target_json, input_json, expected_json,
                    reason, result_json, created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (
                    audit_id,
                    envelope.command_id,
                    envelope.actor.type,
                    envelope.actor.id,
                    envelope.actor.session_id,
                    envelope.command,
                    envelope.version,
                    json.dumps(envelope.target, ensure_ascii=False, separators=(',', ':')),
                    json.dumps(envelope.input, ensure_ascii=False, separators=(',', ':')),
                    json.dumps(envelope.expected, ensure_ascii=False, separators=(',', ':')),
                    envelope.reason,
                    payload,
                    now,
                ),
            )
            if owned:
                conn.commit()
        finally:
            self._finish(conn, owned)
