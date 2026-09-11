from dataclasses import dataclass

import db_core
import db_read

from . import handlers  # noqa: F401 - registers command handlers
from . import repositories
from .errors import DomainError, forbidden, invalid_argument
from .models import Actor, CommandEnvelope, CommandResponse, new_id
from .registry import registry
from .store import CommandStore


VALID_ACTOR_TYPES = {'user', 'agent', 'system', 'integration'}


@dataclass
class DomainContext:
    db_core: object
    db_read: object
    registry: object
    store: object
    repositories: object


class DomainService:
    def __init__(self, db_path, command_registry=None, store=None, core=None, reader=None):
        self.registry = command_registry or registry
        self.store = store or CommandStore(db_path)
        self.context = DomainContext(
            db_core=core or db_core,
            db_read=reader or db_read,
            registry=self.registry,
            store=self.store,
            repositories=repositories,
        )

    def execute(self, payload):
        try:
            envelope = CommandEnvelope.from_dict(payload)
            self._validate_envelope(envelope)
            spec = self.registry.resolve(envelope.command, envelope.version)
            if spec is None:
                raise invalid_argument(f'unknown command: {envelope.command}@{envelope.version}')
            if envelope.actor.type not in spec.allowed_actors:
                raise forbidden(f'{envelope.actor.type} cannot execute {envelope.command}')
            self._validate_input(envelope, spec)

            replay = self.store.find_idempotent(envelope.idempotency_key)
            if replay:
                if replay.get('command') != envelope.command:
                    raise invalid_argument('idempotency key was used for a different command')
                response = replay['result']
                response['replayed'] = True
                return response

            output = spec.handler(envelope, self.context) or {}
            if not isinstance(output, dict):
                output = {'value': output}
            projection = output.pop('projection', {'status': 'pending' if spec.write else 'not_required'})
            if spec.write and output.get('write', {}).get('rendered'):
                projection = {'status': 'synced', 'path': output['write']['rendered']}
            audit_id = new_id('audit')
            response = CommandResponse(
                ok=True,
                command=envelope.command,
                command_id=envelope.command_id,
                audit_id=audit_id,
                result=output,
                projection=projection,
            ).to_dict()
            self.store.save(envelope, audit_id, response)
            return response
        except DomainError as error:
            envelope = self._safe_envelope(payload)
            return CommandResponse(
                ok=False,
                command=(envelope.command if envelope else ''),
                command_id=(envelope.command_id if envelope else new_id('cmd')),
                error=error.to_dict(),
            ).to_dict()
        except ValueError as error:
            envelope = self._safe_envelope(payload)
            return CommandResponse(
                ok=False,
                command=(envelope.command if envelope else ''),
                command_id=(envelope.command_id if envelope else new_id('cmd')),
                error={'code': 'INVALID_ARGUMENT', 'message': str(error)},
            ).to_dict()
        except Exception as error:
            envelope = self._safe_envelope(payload)
            return CommandResponse(
                ok=False,
                command=(envelope.command if envelope else ''),
                command_id=(envelope.command_id if envelope else new_id('cmd')),
                error={'code': 'INTERNAL_ERROR', 'message': f'{type(error).__name__}: {error}'},
            ).to_dict()

    @staticmethod
    def _safe_envelope(payload):
        try:
            return CommandEnvelope.from_dict(payload)
        except Exception:
            return None

    @staticmethod
    def _validate_envelope(envelope):
        if not envelope.command:
            raise invalid_argument('command is required')
        if envelope.actor.type not in VALID_ACTOR_TYPES:
            raise invalid_argument(f'invalid actor.type: {envelope.actor.type}')
        if envelope.actor.type == 'agent' and not envelope.actor.id:
            raise invalid_argument('actor.id is required for agent commands')

    @staticmethod
    def _validate_input(envelope, spec):
        for field in spec.required_fields:
            if field not in envelope.input or envelope.input.get(field) in (None, ''):
                raise invalid_argument(f'input.{field} is required')
        if spec.write and envelope.actor.type == 'agent' and not envelope.idempotency_key:
            raise invalid_argument('idempotency_key is required for agent writes')
        if spec.reason_required and not envelope.reason:
            raise invalid_argument('reason is required for write commands')


def execute(payload, db_path):
    return DomainService(db_path).execute(payload)
