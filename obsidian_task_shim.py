"""Shim: import load_tasks/load_projects from obsidian-task.py (file has dash, not importable normally)."""
import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    'obsidian_task_mod',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'obsidian-task.py'))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
load_tasks = _mod.load_tasks
load_projects = _mod.load_projects
