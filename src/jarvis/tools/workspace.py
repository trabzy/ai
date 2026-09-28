"""Persistent workspace: projects, businesses and ideas with tasks, decisions and briefs.

Everything lives in a single JSON file under the Jarvis data directory, so it
survives restarts and is easy to back up or inspect by hand.
"""

from __future__ import annotations

import datetime
import json
import threading
from pathlib import Path

from . import builtin
from .builtin import registry

KINDS = ["project", "business", "idea"]
STATUSES = ["active", "idea", "paused", "done", "archived"]
PRIORITIES = ["high", "medium", "low"]

_lock = threading.RLock()


def _workspace_file() -> Path:
    # Resolved on each call so the data dir can be redirected (e.g. in tests).
    return builtin.DATA_DIR / "workspace.json"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _load() -> dict:
    path = _workspace_file()
    if not path.exists():
        return {"projects": [], "next_id": 1}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"projects": [], "next_id": 1}
    data.setdefault("projects", [])
    data.setdefault("next_id", len(data["projects"]) + 1)
    return data


def _save(data: dict) -> None:
    path = _workspace_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def _find(data: dict, ref: str) -> dict:
    ref_norm = ref.strip().lower()
    projects = data["projects"]
    for p in projects:
        if p["id"].lower() == ref_norm or p["name"].lower() == ref_norm:
            return p
    matches = [p for p in projects if ref_norm in p["name"].lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"No project matches '{ref}'. Use list_projects to see what exists.")
    names = ", ".join(f"{p['id']} {p['name']}" for p in matches)
    raise ValueError(f"'{ref}' is ambiguous: {names}. Use the project id.")


def _touch(project: dict) -> None:
    project["updated"] = _now()


def _progress(project: dict) -> tuple[int, int]:
    tasks = project.get("tasks", [])
    return sum(1 for t in tasks if t["done"]), len(tasks)


# ---------------------------------------------------------------------------
# Read-only snapshot for the HUD
# ---------------------------------------------------------------------------


def snapshot() -> dict:
    """The whole workspace plus computed progress, for the dashboard."""
    with _lock:
        data = _load()
    projects = []
    for p in data["projects"]:
        done, total = _progress(p)
        projects.append({**p, "tasks_done": done, "tasks_total": total})
    order = {s: i for i, s in enumerate(STATUSES)}
    projects.sort(key=lambda p: p.get("updated", ""), reverse=True)
    projects.sort(key=lambda p: order.get(p["status"], 99))
    return {"projects": projects}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@registry.register(
    name="create_project",
    description=(
        "Start tracking a new project, business or idea in the persistent workspace. "
        "Use kind='idea' for early, unvalidated ideas."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Short name, e.g. 'Mobile car detailing'."},
            "kind": {"type": "string", "enum": KINDS},
            "summary": {"type": "string", "description": "One or two sentences on what it is and why."},
            "status": {"type": "string", "enum": STATUSES, "description": "Defaults to 'idea' for ideas, else 'active'."},
            "goals": {"type": "array", "items": {"type": "string"}, "description": "Measurable goals, if known."},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["name", "kind", "summary"],
    },
)
def create_project(
    name: str,
    kind: str,
    summary: str,
    status: str | None = None,
    goals: list[str] | None = None,
    tags: list[str] | None = None,
) -> str:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    status = status or ("idea" if kind == "idea" else "active")
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    with _lock:
        data = _load()
        if any(p["name"].lower() == name.strip().lower() for p in data["projects"]):
            raise ValueError(f"A project named '{name}' already exists.")
        project_id = f"P{data['next_id']:03d}"
        data["next_id"] += 1
        data["projects"].append(
            {
                "id": project_id,
                "name": name.strip(),
                "kind": kind,
                "status": status,
                "summary": summary.strip(),
                "goals": goals or [],
                "tags": tags or [],
                "tasks": [],
                "decisions": [],
                "notes": [],
                "briefs": [],
                "next_task": 1,
                "created": _now(),
                "updated": _now(),
            }
        )
        _save(data)
    return f"Created {kind} {project_id} '{name}' ({status})."


@registry.register(
    name="list_projects",
    description="List tracked projects, businesses and ideas with status and task progress.",
    input_schema={
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": STATUSES, "description": "Only this status."},
            "kind": {"type": "string", "enum": KINDS, "description": "Only this kind."},
        },
    },
)
def list_projects(status: str | None = None, kind: str | None = None) -> str:
    projects = snapshot()["projects"]
    if status:
        projects = [p for p in projects if p["status"] == status]
    if kind:
        projects = [p for p in projects if p["kind"] == kind]
    if not projects:
        return "The workspace has no matching projects yet."
    lines = []
    for p in projects:
        open_high = sum(1 for t in p["tasks"] if not t["done"] and t["priority"] == "high")
        lines.append(
            f"{p['id']} | {p['name']} | {p['kind']} | {p['status']} | "
            f"tasks {p['tasks_done']}/{p['tasks_total']} done, {open_high} open high-priority | "
            f"{p['summary']}"
        )
    return "\n".join(lines)


@registry.register(
    name="get_project",
    description="Get everything recorded about one project: goals, tasks, decisions, notes and brief titles.",
    input_schema={
        "type": "object",
        "properties": {"project": {"type": "string", "description": "Project id (e.g. P001) or name."}},
        "required": ["project"],
    },
)
def get_project(project: str) -> str:
    with _lock:
        p = _find(_load(), project)
    done, total = _progress(p)
    out = [
        f"{p['id']} {p['name']} [{p['kind']}, {p['status']}]",
        f"Summary: {p['summary']}",
    ]
    if p.get("tags"):
        out.append("Tags: " + ", ".join(p["tags"]))
    if p.get("goals"):
        out.append("Goals:\n" + "\n".join(f"- {g}" for g in p["goals"]))
    out.append(f"Tasks ({done}/{total} done):")
    for t in p["tasks"]:
        box = "x" if t["done"] else " "
        due = f" (due {t['due']})" if t.get("due") else ""
        out.append(f"- [{box}] {t['id']} [{t['priority']}] {t['text']}{due}")
    if p["decisions"]:
        out.append("Decisions:")
        out += [f"- {d['date'][:10]}: {d['decision']} — {d['rationale']}" for d in p["decisions"]]
    if p["notes"]:
        out.append("Recent notes:")
        out += [f"- {n['date'][:10]}: {n['text']}" for n in p["notes"][-10:]]
    if p["briefs"]:
        out.append("Briefs: " + "; ".join(f"{b['title']} ({b['date'][:10]})" for b in p["briefs"]))
    return "\n".join(out)


@registry.register(
    name="update_project",
    description="Change a project's status, summary or name, or add goals.",
    input_schema={
        "type": "object",
        "properties": {
            "project": {"type": "string", "description": "Project id or name."},
            "status": {"type": "string", "enum": STATUSES},
            "summary": {"type": "string"},
            "name": {"type": "string"},
            "kind": {"type": "string", "enum": KINDS, "description": "e.g. promote an idea to a business."},
            "add_goals": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["project"],
    },
)
def update_project(
    project: str,
    status: str | None = None,
    summary: str | None = None,
    name: str | None = None,
    kind: str | None = None,
    add_goals: list[str] | None = None,
) -> str:
    if status and status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    if kind and kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    with _lock:
        data = _load()
        p = _find(data, project)
        changes = []
        for field, value in (("status", status), ("summary", summary), ("name", name), ("kind", kind)):
            if value:
                p[field] = value.strip()
                changes.append(field)
        if add_goals:
            p["goals"].extend(add_goals)
            changes.append(f"{len(add_goals)} goal(s)")
        _touch(p)
        _save(data)
    return f"Updated {p['id']} {p['name']}: {', '.join(changes) or 'no changes'}."


@registry.register(
    name="add_tasks",
    description="Add one or more tasks (next actions) to a project.",
    input_schema={
        "type": "object",
        "properties": {
            "project": {"type": "string", "description": "Project id or name."},
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "priority": {"type": "string", "enum": PRIORITIES},
                        "due": {"type": "string", "description": "Optional due date, ideally YYYY-MM-DD."},
                    },
                    "required": ["text"],
                },
            },
        },
        "required": ["project", "tasks"],
    },
)
def add_tasks(project: str, tasks: list[dict]) -> str:
    if not tasks:
        raise ValueError("Provide at least one task.")
    with _lock:
        data = _load()
        p = _find(data, project)
        ids = []
        for task in tasks:
            priority = task.get("priority") or "medium"
            if priority not in PRIORITIES:
                raise ValueError(f"priority must be one of {PRIORITIES}")
            task_id = f"T{p['next_task']}"
            p["next_task"] += 1
            p["tasks"].append(
                {
                    "id": task_id,
                    "text": task["text"].strip(),
                    "priority": priority,
                    "due": task.get("due"),
                    "done": False,
                    "created": _now(),
                }
            )
            ids.append(task_id)
        _touch(p)
        _save(data)
    return f"Added {len(ids)} task(s) to {p['name']}: {', '.join(ids)}."


@registry.register(
    name="complete_task",
    description="Mark a project task as done (or re-open it).",
    input_schema={
        "type": "object",
        "properties": {
            "project": {"type": "string", "description": "Project id or name."},
            "task_id": {"type": "string", "description": "Task id, e.g. T3."},
            "done": {"type": "boolean", "description": "False re-opens the task. Defaults to true."},
        },
        "required": ["project", "task_id"],
    },
)
def complete_task(project: str, task_id: str, done: bool = True) -> str:
    with _lock:
        data = _load()
        p = _find(data, project)
        for t in p["tasks"]:
            if t["id"].lower() == task_id.strip().lower():
                t["done"] = bool(done)
                t["completed"] = _now() if done else None
                _touch(p)
                _save(data)
                d, total = _progress(p)
                verb = "Completed" if done else "Re-opened"
                return f"{verb} {t['id']} '{t['text']}'. {p['name']} is at {d}/{total}."
    raise ValueError(f"No task '{task_id}' in {p['name']}.")


@registry.register(
    name="log_decision",
    description="Record a decision on a project together with the reasoning behind it.",
    input_schema={
        "type": "object",
        "properties": {
            "project": {"type": "string"},
            "decision": {"type": "string"},
            "rationale": {"type": "string"},
        },
        "required": ["project", "decision", "rationale"],
    },
)
def log_decision(project: str, decision: str, rationale: str) -> str:
    with _lock:
        data = _load()
        p = _find(data, project)
        p["decisions"].append({"date": _now(), "decision": decision.strip(), "rationale": rationale.strip()})
        _touch(p)
        _save(data)
    return f"Decision logged on {p['name']}."


@registry.register(
    name="log_note",
    description="Add a dated note to a project: progress updates, findings, customer feedback, numbers.",
    input_schema={
        "type": "object",
        "properties": {"project": {"type": "string"}, "text": {"type": "string"}},
        "required": ["project", "text"],
    },
)
def log_note(project: str, text: str) -> str:
    with _lock:
        data = _load()
        p = _find(data, project)
        p["notes"].append({"date": _now(), "text": text.strip()})
        _touch(p)
        _save(data)
    return f"Note added to {p['name']}."


@registry.register(
    name="save_brief",
    description=(
        "Save a substantial piece of analysis (SWOT, business plan, pre-mortem, build plan, "
        "market sizing) to a project as Markdown so it can be revisited later."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "project": {"type": "string"},
            "title": {"type": "string"},
            "content": {"type": "string", "description": "The brief, in Markdown."},
        },
        "required": ["project", "title", "content"],
    },
)
def save_brief(project: str, title: str, content: str) -> str:
    with _lock:
        data = _load()
        p = _find(data, project)
        p["briefs"] = [b for b in p["briefs"] if b["title"].lower() != title.strip().lower()]
        p["briefs"].append({"date": _now(), "title": title.strip(), "content": content})
        _touch(p)
        _save(data)
    return f"Brief '{title}' saved to {p['name']}."


@registry.register(
    name="read_brief",
    description="Read the full text of a saved brief.",
    input_schema={
        "type": "object",
        "properties": {"project": {"type": "string"}, "title": {"type": "string"}},
        "required": ["project", "title"],
    },
)
def read_brief(project: str, title: str) -> str:
    with _lock:
        p = _find(_load(), project)
    for b in p["briefs"]:
        if title.strip().lower() in b["title"].lower():
            return f"# {b['title']} ({b['date'][:10]})\n\n{b['content']}"
    raise ValueError(f"No brief matching '{title}' on {p['name']}.")


@registry.register(
    name="delete_project",
    description="Permanently delete a project. Only call this after the user has explicitly confirmed.",
    input_schema={
        "type": "object",
        "properties": {"project": {"type": "string"}},
        "required": ["project"],
    },
)
def delete_project(project: str) -> str:
    with _lock:
        data = _load()
        p = _find(data, project)
        data["projects"] = [x for x in data["projects"] if x["id"] != p["id"]]
        _save(data)
    return f"Deleted {p['id']} {p['name']}."
