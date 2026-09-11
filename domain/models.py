import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


def new_id(prefix):
    return f'{prefix}_{uuid.uuid4().hex}'


@dataclass(frozen=True)
class Actor:
    type: str
    id: str = ''
    session_id: str = ''

    @classmethod
    def from_dict(cls, value):
        value = value or {}
        return cls(
            type=str(value.get('type') or '').strip(),
            id=str(value.get('id') or '').strip(),
            session_id=str(value.get('session_id') or '').strip(),
        )

    def to_dict(self):
        return {'type': self.type, 'id': self.id, 'session_id': self.session_id}


@dataclass
class CommandEnvelope:
    command: str
    version: int
    actor: Actor
    target: dict = field(default_factory=dict)
    input: dict = field(default_factory=dict)
    expected: dict = field(default_factory=dict)
    idempotency_key: str = ''
    reason: str = ''
    command_id: str = field(default_factory=lambda: new_id('cmd'))

    @classmethod
    def from_dict(cls, value, now=None):
        if not isinstance(value, dict):
            raise ValueError('command envelope must be an object')
        return cls(
            command=str(value.get('command') or '').strip(),
            version=int(value.get('version') or 1),
            actor=Actor.from_dict(value.get('actor')),
            target=dict(value.get('target') or {}),
            input=dict(value.get('input') or {}),
            expected=dict(value.get('expected') or {}),
            idempotency_key=str(value.get('idempotency_key') or '').strip(),
            reason=str(value.get('reason') or '').strip(),
            command_id=str(value.get('command_id') or new_id('cmd')),
        )

    def to_dict(self):
        return {
            'command': self.command,
            'version': self.version,
            'actor': self.actor.to_dict(),
            'target': self.target,
            'input': self.input,
            'expected': self.expected,
            'idempotency_key': self.idempotency_key,
            'reason': self.reason,
            'command_id': self.command_id,
        }


@dataclass
class CommandResponse:
    ok: bool
    command: str
    command_id: str
    audit_id: str = ''
    result: dict = field(default_factory=dict)
    projection: dict = field(default_factory=lambda: {'status': 'not_required'})
    error: Optional[dict] = None
    replayed: bool = False

    def to_dict(self):
        payload = {
            'ok': self.ok,
            'command': self.command,
            'command_id': self.command_id,
            'audit_id': self.audit_id,
            'result': self.result,
            'projection': self.projection,
        }
        if self.error:
            payload['error'] = self.error
        if self.replayed:
            payload['replayed'] = True
        return payload


def now_epoch():
    return int(time.time())
