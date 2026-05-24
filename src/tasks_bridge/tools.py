"""All MCP tools. Registered onto the FastMCP app in server.py."""

from __future__ import annotations

import re
import logging
from typing import Optional

from googleapiclient.errors import HttpError

from tasks_bridge import google_tasks, resolve as _resolve

logger = logging.getLogger(__name__)

_NOTES_PREVIEW_LEN = 200


def _task_shape(task: dict, full_notes: bool = False) -> dict:
    notes = task.get("notes") or ""
    if full_notes:
        notes_field = {"notes": notes or None}
    else:
        if len(notes) > _NOTES_PREVIEW_LEN:
            preview = notes[:_NOTES_PREVIEW_LEN] + "…"
        else:
            preview = notes or None
        notes_field = {"notes_preview": preview}

    due_raw = task.get("due")
    due = due_raw[:10] if due_raw else None  # strip time component

    return {
        "id": task["id"],
        "title": task.get("title") or "",
        "status": task.get("status", "needsAction"),
        "due": due,
        "position": task.get("position", ""),
        "parent": task.get("parent") or None,
        **notes_field,
    }


def register_tools(mcp):
    """Register all tools on the given FastMCP instance."""

    # ------------------------------------------------------------------
    # List management
    # ------------------------------------------------------------------

    @mcp.tool()
    def list_task_lists() -> list[dict]:
        """Return all Google Tasks task lists with their id and title."""
        service = google_tasks.get_service()
        try:
            result = service.tasklists().list().execute()
        except HttpError as exc:
            return [google_tasks.handle_http_error(exc, "task lists")]
        return [{"id": tl["id"], "title": tl["title"]} for tl in result.get("items", [])]

    @mcp.tool()
    def create_task_list(name: str) -> dict:
        """Create a new task list with the given name. Returns {id, title}."""
        service = google_tasks.get_service()
        try:
            result = service.tasklists().insert(body={"title": name}).execute()
        except HttpError as exc:
            return google_tasks.handle_http_error(exc, "task list")
        return {"id": result["id"], "title": result["title"]}

    # ------------------------------------------------------------------
    # list_tasks — general view (flat + nested, no dropped childless tasks)
    # ------------------------------------------------------------------

    @mcp.tool()
    def list_tasks(list_id: str, include_completed: bool = False) -> list[dict] | dict:
        """
        List all tasks in a list (general view).

        Returns every top-level task with any subtasks nested under it.
        Use this for flat shopping lists, simple todos, or task-with-steps lists.
        Unlike list_tasks_by_category, childless top-level tasks are NOT dropped.

        list_id accepts a list name or id.
        """
        service = google_tasks.get_service()
        list_id = _resolve.resolve_list(service, list_id)
        if isinstance(list_id, dict):
            return list_id  # error

        try:
            all_tasks = google_tasks.fetch_all_tasks(service, list_id, include_completed)
        except HttpError as exc:
            return google_tasks.handle_http_error(exc, "tasks")

        top_level = sorted(
            [t for t in all_tasks if "parent" not in t],
            key=lambda t: t.get("position", ""),
        )
        by_parent: dict[str, list[dict]] = {}
        for t in all_tasks:
            if "parent" in t:
                by_parent.setdefault(t["parent"], []).append(t)

        result = []
        for task in top_level:
            entry = _task_shape(task)
            subs = sorted(by_parent.get(task["id"], []), key=lambda t: t.get("position", ""))
            entry["subtasks"] = [_task_shape(s) for s in subs]
            result.append(entry)
        return result

    # ------------------------------------------------------------------
    # list_tasks_by_category — parent-as-category view (renamed from old list_tasks)
    # ------------------------------------------------------------------

    @mcp.tool()
    def list_tasks_by_category(
        list_id: str,
        category_ids: Optional[list[str]] = None,
        include_completed: bool = False,
    ) -> list[dict] | dict:
        """
        List tasks grouped by parent task (treated as a category label).

        This is the Satura-style view: each parent task is a category header
        and its subtasks are the items. Childless top-level tasks are NOT shown
        (they have no subtasks and don't represent categories in this view —
        use list_tasks for those).

        list_id accepts a list name or id.
        category_ids accepts category names or ids; omit to discover all categories
        (parents that have subtasks). Empty categories are returned explicitly.

        NOTE: This was called list_tasks in the old server. Satura skill must
        call list_tasks_by_category going forward.
        """
        service = google_tasks.get_service()
        list_id = _resolve.resolve_list(service, list_id)
        if isinstance(list_id, dict):
            return list_id

        try:
            all_tasks = google_tasks.fetch_all_tasks(service, list_id, include_completed)
        except HttpError as exc:
            return google_tasks.handle_http_error(exc, "tasks")

        tasks_by_id = {t["id"]: t for t in all_tasks}

        if category_ids is not None:
            resolved_ids = []
            for ref in category_ids:
                r = _resolve.resolve_task(service, list_id, ref, all_tasks)
                if isinstance(r, dict):
                    return r  # resolution error
                resolved_ids.append(r)
            target_ids = resolved_ids
        else:
            has_children = {t["parent"] for t in all_tasks if "parent" in t}
            target_ids = sorted(
                [t["id"] for t in all_tasks if t["id"] in has_children and "parent" not in t],
                key=lambda pid: tasks_by_id[pid].get("position", ""),
            )

        result = []
        for pid in target_ids:
            parent = tasks_by_id.get(pid)
            title = parent.get("title", "(untitled)") if parent else "(unknown)"
            subs = sorted(
                [t for t in all_tasks if t.get("parent") == pid],
                key=lambda t: t.get("position", ""),
            )
            result.append({
                "category_id": pid,
                "category_title": title,
                "tasks": [_task_shape(s) for s in subs],
            })
        return result

    # ------------------------------------------------------------------
    # Single-task tools
    # ------------------------------------------------------------------

    @mcp.tool()
    def get_task(list_id: str, task_id: str) -> dict:
        """
        Get full details of a single task, including complete (untruncated) notes.

        list_id accepts a list name or id.
        """
        service = google_tasks.get_service()
        list_id = _resolve.resolve_list(service, list_id)
        if isinstance(list_id, dict):
            return list_id

        try:
            task = service.tasks().get(tasklist=list_id, task=task_id).execute()
        except HttpError as exc:
            return google_tasks.handle_http_error(exc, "task")
        return _task_shape(task, full_notes=True)

    @mcp.tool()
    def create_task(
        list_id: str,
        title: str,
        notes: Optional[str] = None,
        due: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> dict:
        """
        Create a new task or subtask.

        list_id accepts a list name or id.
        due is a date string "YYYY-MM-DD" (no time; Google Tasks is date-only).
        parent_id creates it as a subtask under that parent (name or id).
        """
        service = google_tasks.get_service()
        list_id = _resolve.resolve_list(service, list_id)
        if isinstance(list_id, dict):
            return list_id

        resolved_parent = None
        if parent_id is not None:
            resolved_parent = _resolve.resolve_task(service, list_id, parent_id)
            if isinstance(resolved_parent, dict):
                return resolved_parent

        body: dict = {"title": title}
        if notes:
            body["notes"] = notes
        if due:
            body["due"] = f"{due}T00:00:00.000Z"

        params: dict = {"tasklist": list_id, "body": body}
        if resolved_parent:
            params["parent"] = resolved_parent

        try:
            task = service.tasks().insert(**params).execute()
        except HttpError as exc:
            return google_tasks.handle_http_error(exc, "task")
        return _task_shape(task, full_notes=True)

    @mcp.tool()
    def update_task(
        list_id: str,
        task_id: str,
        title: Optional[str] = None,
        notes: Optional[str] = None,
        due: Optional[str] = None,
    ) -> dict:
        """
        Update a task's title, notes, and/or due date (partial merge).

        Only the fields you pass are changed; omitted fields are preserved.
        Does NOT change status (use complete_task / uncomplete_task).
        Does NOT re-parent (the Tasks API move endpoint is out of scope for v1).

        list_id accepts a list name or id.
        due is "YYYY-MM-DD" or null to clear it.
        """
        service = google_tasks.get_service()
        list_id = _resolve.resolve_list(service, list_id)
        if isinstance(list_id, dict):
            return list_id

        try:
            task = service.tasks().get(tasklist=list_id, task=task_id).execute()
        except HttpError as exc:
            return google_tasks.handle_http_error(exc, "task")

        if title is not None:
            task["title"] = title
        if notes is not None:
            task["notes"] = notes
        if due is not None:
            task["due"] = f"{due}T00:00:00.000Z"
        elif due is None and "due" in task and due == "":
            del task["due"]

        try:
            updated = service.tasks().update(
                tasklist=list_id, task=task_id, body=task
            ).execute()
        except HttpError as exc:
            return google_tasks.handle_http_error(exc, "task")
        return _task_shape(updated, full_notes=True)

    @mcp.tool()
    def complete_task(list_id: str, task_id: str) -> dict:
        """
        Mark a task as completed.

        list_id accepts a list name or id.
        """
        service = google_tasks.get_service()
        list_id = _resolve.resolve_list(service, list_id)
        if isinstance(list_id, dict):
            return list_id

        try:
            task = service.tasks().get(tasklist=list_id, task=task_id).execute()
            task["status"] = "completed"
            updated = service.tasks().update(
                tasklist=list_id, task=task_id, body=task
            ).execute()
        except HttpError as exc:
            return google_tasks.handle_http_error(exc, "task")
        return _task_shape(updated, full_notes=True)

    @mcp.tool()
    def uncomplete_task(list_id: str, task_id: str) -> dict:
        """
        Mark a completed task as not done (needsAction).

        Explicitly clears the hidden flag so the task reappears in default listings.

        list_id accepts a list name or id.
        """
        service = google_tasks.get_service()
        list_id = _resolve.resolve_list(service, list_id)
        if isinstance(list_id, dict):
            return list_id

        try:
            task = service.tasks().get(tasklist=list_id, task=task_id).execute()
            task["status"] = "needsAction"
            task.pop("completed", None)  # clear completed timestamp
            task["hidden"] = False       # ensure it reappears in default listings
            updated = service.tasks().update(
                tasklist=list_id, task=task_id, body=task
            ).execute()
        except HttpError as exc:
            return google_tasks.handle_http_error(exc, "task")
        return _task_shape(updated, full_notes=True)

    @mcp.tool()
    def delete_task(list_id: str, task_id: str) -> dict:
        """
        Delete a task permanently.

        Accepts task_id only (no name/fuzzy matching). This is intentional:
        destructive operations must be called with a resolved id. Use list_tasks
        or search_tasks to find the id first, then call this tool.

        list_id accepts a list name or id.
        """
        service = google_tasks.get_service()
        list_id = _resolve.resolve_list(service, list_id)
        if isinstance(list_id, dict):
            return list_id

        try:
            service.tasks().delete(tasklist=list_id, task=task_id).execute()
        except HttpError as exc:
            return google_tasks.handle_http_error(exc, "task")
        return {"deleted": True, "task_id": task_id}

    # ------------------------------------------------------------------
    # search_tasks
    # ------------------------------------------------------------------

    @mcp.tool()
    def search_tasks(
        query: str,
        regex: bool = False,
        lists: Optional[list[str]] = None,
        parents: Optional[list[str]] = None,
        include_completed: bool = False,
    ) -> list[dict] | dict:
        """
        Search tasks by title and notes across one or more lists.

        query is required. By default it is a plain case-insensitive substring
        match (metacharacters are literal). Set regex=True to use Python regex;
        on invalid pattern a structured error is returned, never a traceback.

        lists: list of list names or ids to search; omit to search all lists.
        parents: restrict to tasks under these parent categories (names or ids).
        include_completed: include completed tasks (default false).

        Returns each match with list_id, list_title, and matched_in ("title" /
        "notes" / "both").
        """
        service = google_tasks.get_service()

        if regex:
            try:
                pattern = re.compile(query, re.IGNORECASE)
            except re.error as exc:
                return {"error": "invalid_regex", "detail": str(exc), "query": query}
            def matches(text: str) -> bool:
                return bool(pattern.search(text))
        else:
            q = query.lower()
            def matches(text: str) -> bool:
                return q in text.lower()

        # Resolve list scope
        if lists is not None:
            resolved_lists = []
            for ref in lists:
                r = _resolve.resolve_list(service, ref)
                if isinstance(r, dict):
                    return r
                resolved_lists.append(r)
            list_ids = resolved_lists
        else:
            try:
                all_lists_result = service.tasklists().list().execute()
            except HttpError as exc:
                return [google_tasks.handle_http_error(exc, "task lists")]
            list_ids = [lst["id"] for lst in all_lists_result.get("items", [])]

        # Build list id→title map
        try:
            list_meta_result = service.tasklists().list().execute()
            list_title_map = {
                lst["id"]: lst["title"]
                for lst in list_meta_result.get("items", [])
            }
        except HttpError:
            list_title_map = {}

        results = []
        for lid in list_ids:
            try:
                all_tasks = google_tasks.fetch_all_tasks(service, lid, include_completed)
            except HttpError as exc:
                results.append(google_tasks.handle_http_error(exc, f"tasks in list {lid}"))
                continue

            # Optionally restrict to tasks under certain parents
            if parents is not None:
                allowed_parent_ids = set()
                for ref in parents:
                    r = _resolve.resolve_task(service, lid, ref, all_tasks)
                    if isinstance(r, str):
                        allowed_parent_ids.add(r)
                all_tasks = [
                    t for t in all_tasks
                    if t.get("parent") in allowed_parent_ids
                ]

            list_title = list_title_map.get(lid, lid)
            for task in all_tasks:
                title = task.get("title") or ""
                notes = task.get("notes") or ""
                in_title = matches(title)
                in_notes = matches(notes)
                if not (in_title or in_notes):
                    continue

                matched_in = "both" if (in_title and in_notes) else ("title" if in_title else "notes")
                entry = _task_shape(task)
                entry["list_id"] = lid
                entry["list_title"] = list_title
                entry["matched_in"] = matched_in
                results.append(entry)

        return results
