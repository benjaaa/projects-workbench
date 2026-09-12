from dataclasses import dataclass

import db_core
import db_read

from db_transaction import transaction
from . import handlers  # noqa: F401 - registers command handlers
from . import repositories
from . import review  # noqa: F401 - registers review commands
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
        self.db_path = db_path
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
            if spec.write:
                return self._execute_write(envelope, spec)
            return self._execute_read(envelope, spec)
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

    def _execute_read(self, envelope, spec):
        output = spec.handler(envelope, self.context) or {}
        if not isinstance(output, dict):
            output = {'value': output}
        response = CommandResponse(
            ok=True,
            command=envelope.command,
            command_id=envelope.command_id,
            audit_id=new_id('audit'),
            result=output,
            projection={'status': 'not_required'},
        ).to_dict()
        self.store.save(envelope, response['audit_id'], response)
        return response

    def _execute_write(self, envelope, spec):
        response = None
        with transaction(self.db_path) as tx:
            replay = self.store.find_idempotent(envelope.idempotency_key, conn=tx.connection)
            if replay:
                if replay.get('command') != envelope.command:
                    raise invalid_argument('idempotency key was used for a different command')
                response = replay['result']
                response['replayed'] = True
            else:
                output = spec.handler(envelope, self.context) or {}
                if not isinstance(output, dict):
                    output = {'value': output}
                projection = output.pop('projection', {'status': 'pending'})
                if output.get('write', {}).get('rendered'):
                    projection = {'status': 'synced', 'path': output['write']['rendered']}
                response = CommandResponse(
                    ok=True,
                    command=envelope.command,
                    command_id=envelope.command_id,
                    audit_id=new_id('audit'),
                    result=output,
                    projection=projection,
                ).to_dict()
                self.store.save(envelope, response['audit_id'], response, conn=tx.connection)

        if response and tx.deferred_renders and hasattr(db_core, 'flush_deferred_renders'):
            render_results = db_core.flush_deferred_renders(tx.deferred_renders)
            rendered = [item.get('rendered') for item in render_results if item.get('rendered')]
            if rendered:
                response['projection'] = {'status': 'synced', 'paths': rendered}
        return response

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
