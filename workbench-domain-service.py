#!/usr/bin/env python3
"""Domain command service entrypoint.

This adapter only translates transport input into the domain command layer.
It must not contain business logic.
"""
import base64
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from domain.service import DomainService  # noqa: E402


def _payload_from_argv():
    if len(sys.argv) < 3:
        raise ValueError('command payload is required')
    raw = sys.argv[2]
    try:
        return json.loads(base64.b64decode(raw).decode('utf-8'))
    except Exception:
        return json.loads(raw)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'describe'
    db_path = os.path.join(SCRIPT_DIR, 'workbench.db')
    service = DomainService(db_path)
    if mode == 'describe':
        result = service.execute({
            'command': 'system.describe',
            'version': 1,
            'actor': {'type': 'system', 'id': 'workbench-domain-service'},
        })
    elif mode == 'command':
        result = service.execute(_payload_from_argv())
    else:
        result = {'ok': False, 'error': {'code': 'INVALID_COMMAND', 'message': f'unknown mode: {mode}'}}
    print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
    return 0 if result.get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
