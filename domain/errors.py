class DomainError(Exception):
    """Business error returned through the public command contract."""

    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self):
        payload = {'code': self.code, 'message': self.message}
        if self.details:
            payload['details'] = self.details
        return payload


def invalid_command(message='invalid command'):
    return DomainError('INVALID_COMMAND', message)


def invalid_argument(message, details=None):
    return DomainError('INVALID_ARGUMENT', message, details)


def not_found(message, details=None):
    return DomainError('NOT_FOUND', message, details)


def forbidden(message, details=None):
    return DomainError('FORBIDDEN', message, details)


def conflict(message, details=None):
    return DomainError('CONFLICT', message, details)


def invalid_transition(message, details=None):
    return DomainError('INVALID_TRANSITION', message, details)


def internal_error(message, details=None):
    return DomainError('INTERNAL_ERROR', message, details)
