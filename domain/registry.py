from dataclasses import dataclass


@dataclass(frozen=True)
class CommandSpec:
    name: str
    version: int
    handler: object
    write: bool = False
    allowed_actors: tuple = ('user', 'agent', 'system', 'integration')
    required_fields: tuple = ()
    reason_required: bool = False


class CommandRegistry:
    def __init__(self):
        self._commands = {}

    def register(self, spec):
        key = (spec.name, int(spec.version))
        if key in self._commands:
            raise ValueError(f'duplicate command: {spec.name}@{spec.version}')
        self._commands[key] = spec

    def resolve(self, name, version=1):
        return self._commands.get((str(name), int(version or 1)))

    def list(self):
        return [
            {
                'command': spec.name,
                'version': spec.version,
                'write': spec.write,
                'allowed_actors': list(spec.allowed_actors),
                'required_fields': list(spec.required_fields),
                'reason_required': spec.reason_required,
            }
            for spec in sorted(self._commands.values(), key=lambda item: (item.name, item.version))
        ]


registry = CommandRegistry()


def command(name, version=1, write=False, allowed_actors=None, required_fields=None, reason_required=False):
    def decorate(handler):
        registry.register(CommandSpec(
            name=name,
            version=version,
            handler=handler,
            write=write,
            allowed_actors=tuple(allowed_actors or ('user', 'agent', 'system', 'integration')),
            required_fields=tuple(required_fields or ()),
            reason_required=reason_required,
        ))
        return handler
    return decorate
