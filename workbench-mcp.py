#!/usr/bin/env python3
"""Minimal MCP stdio adapter for Work Station domain commands."""
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from domain.mcp import MCPAdapter, tool_definitions  # noqa: E402
from domain.service import DomainService  # noqa: E402

PROTOCOL_VERSION = '2024-11-05'


def write_message(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n')
    sys.stdout.flush()


def response(message_id, result):
    write_message({'jsonrpc': '2.0', 'id': message_id, 'result': result})


def error(message_id, code, message):
    write_message({'jsonrpc': '2.0', 'id': message_id, 'error': {'code': code, 'message': message}})


def main():
    service = DomainService(os.path.join(SCRIPT_DIR, 'workbench.db'))
    adapter = MCPAdapter(service)
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            message = json.loads(raw)
        except Exception as exc:
            error(None, -32700, f'parse error: {exc}')
            continue
        method = message.get('method', '')
        message_id = message.get('id')
        if method == 'initialize':
            response(message_id, {
                'protocolVersion': PROTOCOL_VERSION,
                'capabilities': {'tools': {}},
                'serverInfo': {'name': 'workbench-domain', 'version': '1.0.0'},
            })
        elif method == 'notifications/initialized':
            continue
        elif method == 'tools/list':
            response(message_id, {'tools': tool_definitions()})
        elif method == 'tools/call':
            params = message.get('params') or {}
            result = adapter.call_tool(params.get('name', ''), params.get('arguments') or {})
            response(message_id, adapter.mcp_result(result))
        elif method == 'ping':
            response(message_id, {})
        elif message_id is not None:
            error(message_id, -32601, f'unknown method: {method}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
