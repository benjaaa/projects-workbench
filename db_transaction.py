"""Shared SQLite transaction context for the Work Station domain layer."""
import contextvars
import sqlite3
from contextlib import contextmanager


_current_transaction = contextvars.ContextVar('workbench_transaction', default=None)


class TransactionConnection:
    """Connection facade used by existing db_core/db_read helpers.

    Legacy helpers still call commit() and close() internally. During a domain
    transaction those calls are neutralized so the domain service owns the real
    transaction boundary.
    """

    def __init__(self, connection):
        self._connection = connection

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None

    def execute(self, *args, **kwargs):
        return self._connection.execute(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        return self._connection.executemany(*args, **kwargs)

    def executescript(self, *args, **kwargs):
        return self._connection.executescript(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._connection, name)


class Transaction:
    def __init__(self, connection):
        self.connection = connection
        self.proxy = TransactionConnection(connection)
        self.deferred_renders = []

    def defer_render(self, entity_type, entity_id):
        item = (str(entity_type), str(entity_id))
        if item not in self.deferred_renders:
            self.deferred_renders.append(item)


@contextmanager
def transaction(db_path):
    connection = sqlite3.connect(db_path, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute('BEGIN IMMEDIATE')
    tx = Transaction(connection)
    token = _current_transaction.set(tx)
    try:
        yield tx
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        _current_transaction.reset(token)
        connection.close()


def current_transaction():
    return _current_transaction.get()
