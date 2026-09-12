"""Codex rollout reader used by the review workflow.

This module owns every Codex-specific session detail. The review domain only
consumes normalized session packets.
"""
import json
import os
import sqlite3
from collections import OrderedDict
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - Python without zoneinfo
    ZoneInfo = None


DEFAULT_CODEX_DB = os.path.expanduser('~/.codex/state_5.sqlite')
LOCAL_TZ = ZoneInfo('Asia/Shanghai') if ZoneInfo else None
INJECTED_PREFIXES = (
    '# AGENTS.md instructions',
    '<environment_context>',
    '<skill>',
    '<skills_instructions>',
    '<permissions instructions>',
    '<collaboration_mode>',
)


def parse_epoch(value, default=None):
    """Parse a rollout timestamp into integer Unix seconds."""
    if value is None or value == '':
        return default
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return default
    try:
        return int(float(text))
    except ValueError:
        pass
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return default
    if parsed.tzinfo is None and LOCAL_TZ:
        parsed = parsed.replace(tzinfo=LOCAL_TZ)
    return int(parsed.timestamp())


def codex_thread_id(sid):
    value = str(sid or '').strip()
    if value.startswith('codex:'):
        return value[len('codex:'):]
    return value


def canonical_session_id(thread_id):
    value = str(thread_id or '').strip()
    if not value:
        return ''
    return value if value.startswith('codex:') else 'codex:' + value


def state_db_path(explicit=None):
    return explicit or os.environ.get('CODEX_STATE_DB') or DEFAULT_CODEX_DB


def _in_window(epoch, window_start, window_end):
    if epoch is None:
        return True
    return int(window_start) <= int(epoch) < int(window_end)


def _event_epoch(raw, payload):
    for key in ('timestamp',):
        parsed = parse_epoch(raw.get(key))
        if parsed is not None:
            return parsed
    for key in ('completed_at_ms', 'started_at_ms', 'updated_at_ms', 'created_at_ms'):
        parsed = parse_epoch(payload.get(key))
        if parsed is not None:
            return parsed // 1000 if parsed > 10_000_000_000 else parsed
    for key in ('completed_at', 'started_at', 'updated_at', 'created_at'):
        parsed = parse_epoch(payload.get(key))
        if parsed is not None:
            return parsed
    return None


def _payload_metadata(payload):
    return payload.get('internal_chat_message_metadata_passthrough') or {}


def _content_text(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ''
    parts = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            text = item.get('text') or item.get('input_text') or item.get('output_text')
            if text:
                parts.append(str(text))
    return '\n'.join(part for part in parts if part).strip()


def _summary_texts(payload):
    texts = []
    for item in payload.get('summary') or []:
        if isinstance(item, str):
            texts.append(item)
        elif isinstance(item, dict) and item.get('text'):
            texts.append(str(item['text']))
    content = payload.get('content')
    if isinstance(content, str) and content:
        texts.append(content)
    elif isinstance(content, list):
        text = _content_text(content)
        if text:
            texts.append(text)
    return [text.strip() for text in texts if text and text.strip()]


def _looks_injected(text):
    stripped = str(text or '').lstrip()
    return any(stripped.startswith(prefix) for prefix in INJECTED_PREFIXES)


def _is_real_user_message(payload):
    if str(payload.get('role') or '') != 'user':
        return False
    kinds = _payload_metadata(payload).get('content_item_kinds') or []
    if kinds:
        return any(str(kind).startswith('user.') for kind in kinds)
    return not _looks_injected(_content_text(payload.get('content')))


def _limit_text(text, max_chars):
    text = str(text or '')
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    head = max_chars // 2
    tail = max_chars - head
    omitted = len(text) - max_chars
    return (
        text[:head].rstrip()
        + f'\n\n...[truncated {omitted} characters]...\n\n'
        + text[-tail:].lstrip(),
        True,
    )


def _new_turn(turn_id, started_at=None):
    return {
        'turn_id': turn_id,
        'status': 'active',
        'started_at': started_at,
        'completed_at': None,
        'user': [],
        'assistant_final': '',
        'reasoning_summary': [],
        'artifacts': [],
    }


def _turn(turns, turn_id, started_at=None):
    key = str(turn_id or 'unknown')
    if key not in turns:
        turns[key] = _new_turn(key, started_at=started_at)
    elif started_at and not turns[key].get('started_at'):
        turns[key]['started_at'] = started_at
    return turns[key]


def read_rollout(path, window_start, window_end, max_text_chars=40000):
    """Read one Codex rollout and return normalized turn data."""
    turns = OrderedDict()
    counts = {
        'events_seen': 0,
        'candidate_messages': 0,
        'included_messages': 0,
        'truncated_messages': 0,
        'timestamp_missing': 0,
        'excluded_events': {},
    }
    errors = []
    if not path or not os.path.exists(path):
        return {
            'turns': [],
            'coverage': {
                **counts,
                'included_turns': 0,
                'omitted_messages': 0,
                'errors': ['rollout_path not found: ' + str(path)],
            },
        }

    try:
        with open(path, 'r', encoding='utf-8') as handle:
            for raw_line in handle:
                if not raw_line.strip():
                    continue
                try:
                    raw = json.loads(raw_line)
                except Exception as error:
                    errors.append(f'invalid json line: {type(error).__name__}')
                    continue
                counts['events_seen'] += 1
                payload = raw.get('payload') or {}
                top_type = str(raw.get('type') or '')
                payload_type = str(payload.get('type') or '')
                epoch = _event_epoch(raw, payload)
                if epoch is None:
                    counts['timestamp_missing'] += 1

                if top_type == 'response_item' and payload_type == 'message':
                    role = str(payload.get('role') or '')
                    if role not in ('user', 'assistant'):
                        continue
                    counts['candidate_messages'] += 1
                    if not _in_window(epoch, window_start, window_end):
                        continue
                    if role == 'user':
                        if not _is_real_user_message(payload):
                            continue
                        text, truncated = _limit_text(_content_text(payload.get('content')), max_text_chars)
                        if not text:
                            continue
                        meta = _payload_metadata(payload)
                        turn = _turn(turns, meta.get('turn_id'), started_at=epoch)
                        turn['user'].append({'text': text, 'timestamp': epoch})
                        counts['included_messages'] += 1
                        counts['truncated_messages'] += int(truncated)
                    continue

                if top_type == 'response_item' and payload_type == 'reasoning':
                    counts['candidate_messages'] += 1
                    if not _in_window(epoch, window_start, window_end):
                        continue
                    meta = _payload_metadata(payload)
                    turn = _turn(turns, meta.get('turn_id'), started_at=epoch)
                    summaries = _summary_texts(payload)
                    for summary in summaries:
                        text, truncated = _limit_text(summary, max(1000, max_text_chars // 2))
                        if not text:
                            continue
                        turn['reasoning_summary'].append({'text': text, 'timestamp': epoch})
                        counts['included_messages'] += 1
                        counts['truncated_messages'] += int(truncated)
                    continue

                if top_type != 'event_msg':
                    continue

                turn_id = payload.get('turn_id')
                if payload_type == 'task_started':
                    turn = _turn(turns, turn_id, started_at=epoch)
                    if turn['status'] == 'active':
                        turn['started_at'] = turn.get('started_at') or epoch
                    continue

                if payload_type == 'task_complete' and _in_window(epoch, window_start, window_end):
                    turn = _turn(turns, turn_id, started_at=epoch)
                    turn['status'] = 'completed'
                    turn['completed_at'] = epoch
                    final_text, truncated = _limit_text(payload.get('last_agent_message'), max_text_chars)
                    if final_text:
                        turn['assistant_final'] = final_text
                        counts['included_messages'] += 1
                        counts['truncated_messages'] += int(truncated)
                    continue

                if payload_type == 'turn_aborted' and _in_window(epoch, window_start, window_end):
                    turn = _turn(turns, turn_id, started_at=epoch)
                    turn['status'] = 'interrupted'
                    turn['completed_at'] = epoch
                    continue

                if payload_type == 'item_completed' and _in_window(epoch, window_start, window_end):
                    item = payload.get('item') or {}
                    if str(item.get('type') or '') == 'FileChange':
                        turn = _turn(turns, turn_id, started_at=epoch)
                        for changed_path, change in (item.get('changes') or {}).items():
                            turn['artifacts'].append({
                                'path': changed_path,
                                'type': (change or {}).get('type') or 'change',
                                'status': item.get('status') or '',
                                'timestamp': epoch,
                            })
                    continue

                key = payload_type or top_type or 'unknown'
                excluded = counts['excluded_events']
                excluded[key] = excluded.get(key, 0) + 1
    except Exception as error:
        errors.append(f'{type(error).__name__}: {error}')

    normalized_turns = []
    for turn in turns.values():
        if not (turn['user'] or turn['assistant_final'] or turn['reasoning_summary'] or turn['artifacts']):
            continue
        normalized_turns.append(turn)
    normalized_turns.sort(key=lambda item: item.get('started_at') or item.get('completed_at') or 0)

    included_messages = counts['included_messages']
    omitted_messages = max(0, counts['candidate_messages'] - included_messages)
    return {
        'turns': normalized_turns,
        'coverage': {
            **counts,
            'included_turns': len(normalized_turns),
            'omitted_messages': omitted_messages,
            'errors': errors,
        },
    }


def filter_updated_sessions(links, window_start, window_end, state_db=None):
    """Return Codex threads updated in the half-open review window."""
    candidates = []
    skipped = []
    thread_to_link = {}
    for link in links or []:
        sid = str(link.get('sid') or '').strip()
        thread_id = codex_thread_id(sid)
        if not sid or not thread_id:
            continue
        thread_to_link.setdefault(thread_id, dict(link, sid=canonical_session_id(thread_id)))

    if not thread_to_link:
        return candidates, skipped

    resolved_state_db = state_db_path(state_db)
    if not os.path.exists(resolved_state_db):
        for thread_id, link in thread_to_link.items():
            skipped.append({
                'session_id': canonical_session_id(thread_id),
                'reason': 'state_db_missing',
                'source': link.get('source') or '',
            })
        return candidates, skipped

    conn = sqlite3.connect(state_db_path(state_db), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ','.join('?' for _ in thread_to_link)
        rows = conn.execute(
            f'''SELECT id, rollout_path, archived, created_at, updated_at,
                       COALESCE(NULLIF(name, ''), title) AS title
                FROM threads WHERE id IN ({placeholders})''',
            list(thread_to_link),
        ).fetchall()
        by_id = {row['id']: row for row in rows}
    finally:
        conn.close()

    for thread_id, link in thread_to_link.items():
        row = by_id.get(thread_id)
        if not row:
            skipped.append({
                'session_id': canonical_session_id(thread_id),
                'reason': 'missing_thread',
                'source': link.get('source') or '',
            })
            continue
        updated_at = int(row['updated_at'] or 0)
        candidate = {
            'session_id': canonical_session_id(thread_id),
            'thread_id': thread_id,
            'title': row['title'] or '(untitled)',
            'archived': bool(row['archived']),
            'created_at': row['created_at'] or 0,
            'updated_at': updated_at,
            'rollout_path': row['rollout_path'] or '',
            'source': link.get('source') or 'codex',
        }
        if not _in_window(updated_at, window_start, window_end):
            skipped.append({**candidate, 'reason': 'not_updated_in_window'})
            continue
        candidates.append(candidate)
    return candidates, skipped


def collect_codex_sessions(links, window_start, window_end, state_db=None, max_text_chars=40000):
    """Read all Codex sessions linked to a task and updated in the window."""
    candidates, skipped = filter_updated_sessions(links, window_start, window_end, state_db=state_db)
    sessions = []
    total_events = 0
    included_turns = 0
    included_messages = 0
    omitted_messages = 0
    truncated_messages = 0
    failed_sessions = 0

    for candidate in candidates:
        packet = dict(candidate)
        try:
            result = read_rollout(
                candidate.get('rollout_path'),
                window_start,
                window_end,
                max_text_chars=max_text_chars,
            )
            packet['status'] = 'completed'
            packet['turns'] = result['turns']
            packet['coverage'] = result['coverage']
            if result['coverage'].get('errors'):
                packet['status'] = 'partial'
                failed_sessions += 1
        except Exception as error:
            packet['status'] = 'unreadable'
            packet['turns'] = []
            packet['coverage'] = {
                'events_seen': 0,
                'included_turns': 0,
                'included_messages': 0,
                'omitted_messages': 0,
                'truncated_messages': 0,
                'errors': [f'{type(error).__name__}: {error}'],
            }
            failed_sessions += 1
        coverage = packet['coverage']
        total_events += int(coverage.get('events_seen') or 0)
        included_turns += int(coverage.get('included_turns') or 0)
        included_messages += int(coverage.get('included_messages') or 0)
        omitted_messages += int(coverage.get('omitted_messages') or 0)
        truncated_messages += int(coverage.get('truncated_messages') or 0)
        sessions.append(packet)

    coverage = {
        'candidate_sessions': len(candidates),
        'included_sessions': len(sessions),
        'skipped_sessions': len(skipped),
        'failed_sessions': failed_sessions,
        'total_events': total_events,
        'included_turns': included_turns,
        'included_messages': included_messages,
        'omitted_messages': omitted_messages,
        'truncated_messages': truncated_messages,
    }
    return sessions, skipped, coverage
