import time
from .errors import conflict, forbidden, invalid_argument, invalid_transition, not_found
from .registry import command


TASK_AGENT_FIELDS = {'status', 'priority', 'handler', 'due', 'start'}
TASK_USER_FIELDS = TASK_AGENT_FIELDS | {'complete', 'title', 'repeat_anchor', 'repeat_mode', 'repeat_unit', 'repeat_every', 'repeat_day'}
PROJECT_FIELDS = {'status', 'start', 'due', 'complete', 'name'}
PROJECT_AGENT_FIELDS = {'status', 'start', 'due', 'complete'}


def _require_value(value, name):
    if value is None or str(value).strip() == '':
        raise invalid_argument(f'{name} is required')
    return value


def _normalize_log_entry(data):
    data = data or {}
    summary = _require_value(data.get('summary'), 'input.summary')
    sessions = []
    for item in data.get('sessions') or []:
        if isinstance(item, str):
            sessions.append({'id': item.strip(), 'source': ''})
        elif isinstance(item, dict):
            sid = str(item.get('id') or item.get('sid') or '').strip()
            if sid:
                sessions.append({'id': sid, 'source': str(item.get('source') or '')})
    decisions = []
    for item in data.get('decisions') or []:
        if isinstance(item, str):
            decisions.append({'desc': item, 'by': ''})
        elif isinstance(item, dict):
            decisions.append({'desc': str(item.get('desc') or item.get('text') or ''), 'by': str(item.get('by') or '')})
    return {
        'id': str(data.get('id') or ''),
        'date': str(data.get('date') or time.strftime('%m-%d %H:%M:%S')),
        'type': str(data.get('type') or 'manual'),
        'summary': str(summary),
        'window': str(data.get('window') or ''),
        'sessions': sessions,
        'outputs': [str(value) for value in (data.get('outputs') or [])],
        'risks': [str(value) for value in (data.get('risks') or [])],
        'pending': [str(value) for value in (data.get('pending') or [])],
        'decisions': decisions,
    }


def _resolve_task(context, target):
    path = str((target or {}).get('path') or '').strip()
    if path:
        tasks = context.db_read.load_tasks().get('tasks', [])
        candidates = [task for task in tasks if task.get('path') == path]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise conflict('task path is ambiguous', {'matches': [task.get('id') for task in candidates[:10]]})
    task_id = str((target or {}).get('task_id') or '').strip()
    if task_id:
        task = context.db_read.get_task(task_id)
        if task:
            return task

    title = str((target or {}).get('title') or '').strip()
    project = str((target or {}).get('project') or '').strip()
    if not title:
        raise invalid_argument('target.task_id or target.title is required')

    tasks = context.db_read.load_tasks().get('tasks', [])
    candidates = [task for task in tasks if task.get('title') == title]
    if project:
        candidates = [task for task in candidates if (task.get('dir') or task.get('project') or '') == project]
    if not candidates and title:
        candidates = [task for task in tasks if title in (task.get('title') or '')]
        if project:
            candidates = [task for task in candidates if (task.get('dir') or task.get('project') or '') == project]
    if not candidates:
        raise not_found(f'task not found: {project + "/" if project else ""}{title}')
    if len(candidates) > 1:
        raise conflict('task reference is ambiguous', {'matches': [task.get('id') for task in candidates[:10]]})
    return candidates[0]


def _resolve_project(context, target):
    path = str((target or {}).get('path') or '').strip()
    if path:
        projects = context.db_read.load_projects().get('projects', [])
        candidates = [project for project in projects if project.get('path') == path]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise conflict('project path is ambiguous', {'matches': [project.get('id') for project in candidates[:10]]})
    project_id = str((target or {}).get('project_id') or '').strip()
    if project_id:
        project = context.db_read.get_project(project_id)
        if project:
            return project

    name = str((target or {}).get('name') or '').strip()
    if not name:
        raise invalid_argument('target.project_id or target.name is required')
    projects = context.db_read.load_projects().get('projects', [])
    candidates = [project for project in projects if project.get('name') == name]
    if not candidates:
        candidates = [project for project in projects if name in (project.get('name') or '')]
    if not candidates:
        raise not_found(f'project not found: {name}')
    if len(candidates) > 1:
        raise conflict('project reference is ambiguous', {'matches': [project.get('id') for project in candidates[:10]]})
    return candidates[0]


def _check_expected(task, expected):
    for field, expected_value in (expected or {}).items():
        if str(task.get(field) or '') != str(expected_value or ''):
            raise conflict(
                f'{field} mismatch',
                {'field': field, 'expected': expected_value, 'actual': task.get(field)},
            )


@command('system.describe', version=1)
def describe(envelope, context):
    return {'commands': context.registry.list()}


@command('workbench.snapshot', version=1)
def workbench_snapshot(envelope, context):
    return {
        'projects': context.db_read.load_projects().get('projects', []),
        'tasks': context.db_read.load_tasks().get('tasks', []),
    }


@command('task.get', version=1)
def task_get(envelope, context):
    return {'task': _resolve_task(context, envelope.target)}


@command('task.list', version=1)
def task_list(envelope, context):
    filters = envelope.input or {}
    project = str(filters.get('project') or '').strip()
    status = str(filters.get('status') or '').strip()
    limit = int(filters.get('limit') or 200)
    tasks = context.db_read.load_tasks().get('tasks', [])
    if project:
        tasks = [task for task in tasks if (task.get('dir') or task.get('project') or '') == project]
    if status:
        tasks = [task for task in tasks if task.get('status') == status]
    return {'tasks': tasks[:max(1, min(limit, 1000))], 'total': len(tasks)}


@command('project.get', version=1)
def project_get(envelope, context):
    return {'project': _resolve_project(context, envelope.target)}


@command('project.list', version=1)
def project_list(envelope, context):
    filters = envelope.input or {}
    status = str(filters.get('status') or '').strip()
    limit = int(filters.get('limit') or 200)
    projects = context.db_read.load_projects().get('projects', [])
    if status:
        projects = [project for project in projects if project.get('status') == status]
    return {'projects': projects[:max(1, min(limit, 1000))], 'total': len(projects)}


@command('draft.list', version=1)
def draft_list(envelope, context):
    result = context.db_core.list_drafts(include_archived=bool((envelope.input or {}).get('include_archived', True)))
    if not result.get('ok'):
        raise invalid_argument(result.get('error') or 'draft.list failed')
    return {'drafts': result.get('items', [])}


@command('draft.get', version=1)
def draft_get(envelope, context):
    reference = str((envelope.input or {}).get('draft_id') or (envelope.target or {}).get('draft_id') or '').strip()
    title = str((envelope.input or {}).get('title') or (envelope.target or {}).get('title') or '').strip()
    if not reference and not title:
        raise invalid_argument('draft_id or title is required')
    result = context.db_core.list_drafts(include_archived=True)
    if not result.get('ok'):
        raise invalid_argument(result.get('error') or 'draft.get failed')
    for item in result.get('items', []):
        if reference and item.get('draft_id') == reference:
            return {'draft': item}
        if title and item.get('title') == title:
            return {'draft': item}
    raise not_found(f'draft not found: {reference or title}')


@command('draft.delete', version=1, write=True, allowed_actors=('user', 'system'), required_fields=('draft_id',), reason_required=True)
def draft_delete(envelope, context):
    result = context.db_core.delete_draft(
        envelope.input.get('draft_id', ''),
        changed_by=f'{envelope.actor.type}:{envelope.actor.id or "unknown"}',
    )
    if not result.get('ok'):
        raise conflict(result.get('error') or 'draft.delete failed')
    return result


@command('draft.update', version=1, write=True, allowed_actors=('user', 'system'), required_fields=('draft_id', 'body'), reason_required=True)
def draft_update(envelope, context):
    changed_by = f'{envelope.actor.type}:{envelope.actor.id or "unknown"}'
    result = context.repositories.update_draft_body(
        envelope.input.get('draft_id', ''),
        envelope.input.get('body', ''),
        changed_by=changed_by,
    )
    if not result.get('ok'):
        raise conflict(result.get('error') or 'draft.update failed')
    context.db_core._log_change('draft', result['draft_id'], 'body', result.get('old_body', ''), envelope.input.get('body', ''), changed_by)
    render_result = context.db_core._trigger_render('draft', result['draft_id'])
    return {'draft_id': result['draft_id'], 'version': result.get('version'), 'write': render_result}


@command('projection.render', version=1, write=True, allowed_actors=('agent', 'user', 'system'), reason_required=True)
def projection_render(envelope, context):
    target = envelope.target or {}
    path = str(target.get('path') or '').strip()
    if path and '/tasks/' not in path:
        project = _resolve_project(context, target)
        result = context.db_core._trigger_render('project', project['id'])
    else:
        task = _resolve_task(context, target)
        result = context.db_core._trigger_render('task', task['id'])
    return {'render': result}


@command(
    'task.update_field',
    version=1,
    write=True,
    allowed_actors=('user', 'agent', 'system', 'integration'),
    required_fields=('field', 'value'),
    reason_required=True,
)
def task_update_field(envelope, context):
    task = _resolve_task(context, envelope.target)
    field = str(envelope.input.get('field') or '').strip()
    if field not in TASK_USER_FIELDS:
        raise invalid_argument(f'field is not writable: {field}')
    if envelope.actor.type == 'agent' and field not in TASK_AGENT_FIELDS:
        raise forbidden(f'agent cannot update field: {field}')
    expected = envelope.expected or {}
    _check_expected(task, expected)
    result = context.db_core.set_property(
        task['path'],
        field,
        envelope.input.get('value'),
        changed_by=f'{envelope.actor.type}:{envelope.actor.id or "unknown"}',
    )
    if not result.get('ok'):
        raise conflict(result.get('error') or 'task.update_field failed')
    return {'task': context.db_read.get_task(task['id']), 'write': result}


@command('task.finish', version=1, write=True, allowed_actors=('agent', 'user', 'system'), reason_required=True)
def task_finish(envelope, context):
    task = _resolve_task(context, envelope.target)
    _check_expected(task, envelope.expected or {})
    if task.get('status') in ('Done', 'Dropped'):
        return {'task': task, 'unchanged': True}
    result = context.db_core.set_property(
        task['path'],
        'status',
        'Done',
        changed_by=f'{envelope.actor.type}:{envelope.actor.id or "unknown"}',
    )
    if not result.get('ok'):
        raise conflict(result.get('error') or 'task.finish failed')
    next_task = ''
    if task.get('repeat_mode'):
        repeat = context.db_core.repeat_next(
            task['path'],
            changed_by=f'{envelope.actor.type}:{envelope.actor.id or "unknown"}',
        )
        if repeat.get('ok'):
            next_task = repeat.get('title') or repeat.get('due') or ''
        elif repeat.get('error') not in ('EXISTS', 'NO_REPEAT'):
            raise invalid_transition('task finished but next repeat failed', {'error': repeat.get('error')})
    return {'task': context.db_read.get_task(task['id']), 'next_task': next_task, 'write': result}


@command('task.add_log', version=1, write=True, allowed_actors=('agent', 'user', 'system'), required_fields=('summary',), reason_required=True)
def task_add_log(envelope, context):
    task = _resolve_task(context, envelope.target)
    changed_by = f'{envelope.actor.type}:{envelope.actor.id or "unknown"}'
    entry = _normalize_log_entry(envelope.input)
    sids = [item['id'] for item in entry['sessions'] if item.get('id')]
    dead = context.db_core._validate_sids(sids) if sids else None
    if dead:
        raise invalid_argument(f'INVALID_SESSION_IDS: {dead}')
    result = context.repositories.create_task_log(task['id'], entry)
    if not result.get('ok'):
        raise conflict(result.get('error') or 'task.add_log failed')
    context.db_core._log_change('task', task['id'], 'log_entries', None, result['entry_id'], changed_by)
    render_result = context.db_core._trigger_render('task', task['id'])
    return {'task': context.db_read.get_task(task['id']), 'entry_id': result['entry_id'], 'write': {**result, **render_result}}


@command('session.link', version=1, write=True, allowed_actors=('agent', 'user', 'system'), required_fields=('sid',), reason_required=True)
def session_link(envelope, context):
    sid = str(envelope.input.get('sid') or '').strip()
    source = str(envelope.input.get('source') or 'codex').strip()
    target = envelope.target or {}
    kwargs = {
        'sid': sid,
        'source': source,
        'changed_by': f'{envelope.actor.type}:{envelope.actor.id or "unknown"}',
        'skip_validation': bool(envelope.input.get('skip_validation', False)),
    }
    target_path = str(target.get('path') or '')
    if target.get('task_id') or target.get('title') or '/tasks/' in target_path:
        kwargs['task_path'] = _resolve_task(context, target)['path']
    elif target.get('project_id') or target.get('name') or target_path:
        kwargs['project_path'] = _resolve_project(context, target)['path']
    else:
        raise invalid_argument('session.link requires task or project target')
    result = context.db_core.link_session(**kwargs)
    if not result.get('ok'):
        raise conflict(result.get('error') or 'session.link failed')
    return {'link': result}


@command('project.update_field', version=1, write=True, allowed_actors=('user', 'agent', 'system', 'integration'), required_fields=('field', 'value'), reason_required=True)
def project_update_field(envelope, context):
    project = _resolve_project(context, envelope.target)
    field = str(envelope.input.get('field') or '').strip()
    if field not in PROJECT_FIELDS:
        raise invalid_argument(f'field is not writable: {field}')
    if envelope.actor.type == 'agent' and field not in PROJECT_AGENT_FIELDS:
        raise forbidden(f'agent cannot update field: {field}')
    _check_expected(project, envelope.expected or {})
    result = context.db_core.set_property(project['path'], field, envelope.input.get('value'), changed_by=f'{envelope.actor.type}:{envelope.actor.id or "unknown"}')
    if not result.get('ok'):
        raise conflict(result.get('error') or 'project.update_field failed')
    return {'project': context.db_read.get_project(project['id']), 'write': result}


@command('task.update_section', version=1, write=True, allowed_actors=('user', 'agent', 'system', 'integration'), required_fields=('section', 'text'), reason_required=True)
def task_update_section(envelope, context):
    task = _resolve_task(context, envelope.target)
    result = context.db_core.update_section(task['path'], envelope.input['section'], envelope.input['text'], changed_by=f'{envelope.actor.type}:{envelope.actor.id or "unknown"}')
    if not result.get('ok'):
        raise conflict(result.get('error') or 'task.update_section failed')
    return {'task': context.db_read.get_task(task['id']), 'write': result}


@command('project.update_section', version=1, write=True, allowed_actors=('user', 'agent', 'system', 'integration'), required_fields=('section', 'text'), reason_required=True)
def project_update_section(envelope, context):
    project = _resolve_project(context, envelope.target)
    result = context.db_core.update_section(project['path'], envelope.input['section'], envelope.input['text'], changed_by=f'{envelope.actor.type}:{envelope.actor.id or "unknown"}')
    if not result.get('ok'):
        raise conflict(result.get('error') or 'project.update_section failed')
    return {'project': context.db_read.get_project(project['id']), 'write': result}


@command('task.toggle_acceptance', version=1, write=True, allowed_actors=('user', 'agent', 'system', 'integration'), required_fields=('index',), reason_required=True)
def task_toggle_acceptance(envelope, context):
    task = _resolve_task(context, envelope.target)
    result = context.db_core.toggle_ac(task['path'], int(envelope.input['index']), changed_by=f'{envelope.actor.type}:{envelope.actor.id or "unknown"}')
    if not result.get('ok'):
        raise conflict(result.get('error') or 'task.toggle_acceptance failed')
    return {'task': context.db_read.get_task(task['id']), 'write': result}


@command('task.rename', version=1, write=True, allowed_actors=('user', 'system', 'integration'), required_fields=('new_title',), reason_required=True)
def task_rename(envelope, context):
    task = _resolve_task(context, envelope.target)
    result = context.db_core.rename_task(task['path'], envelope.input['new_title'], changed_by=f'{envelope.actor.type}:{envelope.actor.id or "unknown"}')
    if not result.get('ok'):
        raise conflict(result.get('error') or 'task.rename failed')
    return result


@command('project.rename', version=1, write=True, allowed_actors=('user', 'system', 'integration'), required_fields=('new_name',), reason_required=True)
def project_rename(envelope, context):
    project = _resolve_project(context, envelope.target)
    result = context.db_core.rename_project(project['path'], envelope.input['new_name'], changed_by=f'{envelope.actor.type}:{envelope.actor.id or "unknown"}')
    if not result.get('ok'):
        raise conflict(result.get('error') or 'project.rename failed')
    return result


@command('task.delete', version=1, write=True, allowed_actors=('user', 'system'), reason_required=True)
def task_delete(envelope, context):
    task = _resolve_task(context, envelope.target)
    result = context.db_core.delete_task(task['path'], changed_by=f'{envelope.actor.type}:{envelope.actor.id or "unknown"}')
    if not result.get('ok'):
        raise conflict(result.get('error') or 'task.delete failed')
    return result


@command('project.delete', version=1, write=True, allowed_actors=('user', 'system'), reason_required=True)
def project_delete(envelope, context):
    project = _resolve_project(context, envelope.target)
    result = context.db_core.delete_project(project['path'], changed_by=f'{envelope.actor.type}:{envelope.actor.id or "unknown"}')
    if not result.get('ok'):
        raise conflict(result.get('error') or 'project.delete failed')
    return result


@command('task.create', version=1, write=True, allowed_actors=('user', 'system', 'integration'), required_fields=('project_id', 'title'), reason_required=True)
def task_create(envelope, context):
    data = dict(envelope.input or {})
    result = context.db_core.create_task(
        project_id=data.get('project_id', ''),
        title=data.get('title', ''),
        goal=data.get('goal', ''),
        task_detail=data.get('task_detail', ''),
        acceptance=data.get('acceptance', ''),
        priority=data.get('priority', 'p2'),
        status=data.get('status', 'open'),
        start=data.get('start', ''),
        due=data.get('due', ''),
        handler=data.get('handler', ''),
        repeat_cfg=data.get('repeat_cfg'),
        changed_by=f'{envelope.actor.type}:{envelope.actor.id or "unknown"}',
    )
    if not result.get('ok'):
        raise conflict(result.get('error') or 'task.create failed')
    return result


@command('project.create', version=1, write=True, allowed_actors=('user', 'system', 'integration'), required_fields=('dir',), reason_required=True)
def project_create(envelope, context):
    data = dict(envelope.input or {})
    result = context.db_core.create_project(
        data.get('dir', ''),
        data.get('project_content', ''),
        data.get('agents_content', ''),
        changed_by=f'{envelope.actor.type}:{envelope.actor.id or "unknown"}',
    )
    if not result.get('ok'):
        raise conflict(result.get('error') or 'project.create failed')
    return result


@command('draft.create', version=1, write=True, allowed_actors=('agent', 'user', 'system', 'integration'), required_fields=('title',), reason_required=True)
def draft_create(envelope, context):
    result = context.db_core.create_draft(
        envelope.input.get('title', ''),
        envelope.input.get('body', ''),
        changed_by=f'{envelope.actor.type}:{envelope.actor.id or "unknown"}',
    )
    if not result.get('ok'):
        raise conflict(result.get('error') or 'draft.create failed')
    return result


@command('draft.convert', version=1, write=True, allowed_actors=('user', 'system', 'integration'), required_fields=('draft_id', 'project_id'), reason_required=True)
def draft_convert(envelope, context):
    result = context.db_core.convert_draft(
        envelope.input.get('draft_id', ''),
        envelope.input.get('project_id', ''),
        changed_by=f'{envelope.actor.type}:{envelope.actor.id or "unknown"}',
    )
    if not result.get('ok'):
        raise conflict(result.get('error') or 'draft.convert failed')
    return result


@command('task.repeat_next', version=1, write=True, allowed_actors=('user', 'system', 'integration'), reason_required=True)
def task_repeat_next(envelope, context):
    task = _resolve_task(context, envelope.target)
    result = context.db_core.repeat_next(task['path'], changed_by=f'{envelope.actor.type}:{envelope.actor.id or "unknown"}')
    if not result.get('ok') and result.get('error') not in ('EXISTS', 'NO_REPEAT'):
        raise conflict(result.get('error') or 'task.repeat_next failed')
    return result


@command('log.edit_entry', version=1, write=True, allowed_actors=('user', 'system', 'integration'), required_fields=('entry_id', 'summary'), reason_required=True)
def log_edit_entry(envelope, context):
    task = _resolve_task(context, envelope.target)
    changed_by = f'{envelope.actor.type}:{envelope.actor.id or "unknown"}'
    entry = _normalize_log_entry(envelope.input)
    sids = [item['id'] for item in entry['sessions'] if item.get('id')]
    dead = context.db_core._validate_sids(sids) if sids else None
    if dead:
        raise invalid_argument(f'INVALID_SESSION_IDS: {dead}')
    result = context.repositories.update_task_log(task['id'], envelope.input['entry_id'], entry)
    if not result.get('ok'):
        raise conflict(result.get('error') or 'log.edit_entry failed')
    context.db_core._log_change('task', task['id'], 'log_entries', envelope.input['entry_id'], 'updated', changed_by)
    render_result = context.db_core._trigger_render('task', task['id'])
    return {'task': context.db_read.get_task(task['id']), 'entry_id': result['entry_id'], 'write': {**result, **render_result}}


@command('ops.log', version=1, write=True, allowed_actors=('user', 'system', 'integration'), required_fields=('action',), reason_required=True)
def ops_log(envelope, context):
    context.db_core._log_op(
        f'{envelope.actor.type}:{envelope.actor.id or "unknown"}',
        envelope.input.get('action', ''),
        envelope.input.get('entity_type', ''),
        envelope.input.get('entity_id', ''),
        envelope.input.get('detail', ''),
    )
    return {'logged': True}


@command('project.path', version=1)
def project_path(envelope, context):
    return context.repositories.resolve_project_path(
        context.db_core.WB_DB,
        context.db_core.VAULT,
        context.db_core.PROOT,
        project_id=envelope.target.get('project_id', ''),
        name=envelope.target.get('name', ''),
    )


@command('session.unlink', version=1, write=True, allowed_actors=('agent', 'user', 'system'), required_fields=('sid',), reason_required=True)
def session_unlink(envelope, context):
    return context.repositories.unlink_session(
        context.db_core.WB_DB,
        path=envelope.target.get('path', ''),
        sid=envelope.input.get('sid', ''),
    )


@command('session.list_by_ids', version=1)
def session_list_by_ids(envelope, context):
    ids = envelope.input.get('ids', [])
    if isinstance(ids, str):
        ids = [value.strip() for value in ids.split(',') if value.strip()]
    return context.repositories.list_sessions(ids)


@command('session.list_for_project', version=1)
def session_list_for_project(envelope, context):
    project = _resolve_project(context, envelope.target)
    return context.repositories.list_project_sessions(context.store.db_path, project_id=project['id'])


@command('session.counts', version=1)
def session_counts(envelope, context):
    return context.repositories.session_counts(context.store.db_path)


@command('session.codex_titles', version=1)
def session_codex_titles(envelope, context):
    ids = envelope.input.get('ids', [])
    if isinstance(ids, str):
        ids = [value.strip() for value in ids.split(',') if value.strip()]
    return context.repositories.list_codex_thread_titles(ids)


def _kanban_command(name, agent_allowed=False):
    actors = ('agent', 'user', 'system', 'integration') if agent_allowed else ('user', 'system', 'integration')
    @command(name, version=1, write=True, allowed_actors=actors, reason_required=True)
    def handler(envelope, context):
        data = dict(envelope.input or {})
        data['changed_by'] = f'{envelope.actor.type}:{envelope.actor.id or "unknown"}'
        result = context.db_core.kanban_bridge(name.replace('kanban.', 'kanban_'), data)
        if isinstance(result, dict) and result.get('ok') is False:
            raise conflict(result.get('error') or f'{name} failed')
        return result if isinstance(result, dict) else {'result': result}
    return handler


kanban_status = _kanban_command('kanban.status')
kanban_worker_session = _kanban_command('kanban.worker_session')
kanban_link_session = _kanban_command('kanban.link_session')
kanban_dispatch = _kanban_command('kanban.dispatch')
kanban_create = _kanban_command('kanban.create')
kanban_complete = _kanban_command('kanban.complete')
