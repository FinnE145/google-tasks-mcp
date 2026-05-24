"""Shared name→id resolver for task lists and parent tasks."""

from __future__ import annotations

from googleapiclient.errors import HttpError

from tasks_bridge import google_tasks


def resolve_list(service, ref: str) -> str | dict:
    """
    Resolve a task list name or id to its id.

    Resolution order:
    1. Exact case-insensitive name match
    2. Unique case-insensitive substring match
    3. Direct id match
    4. Ambiguous / not found → structured error dict

    Returns the list id string on success, or an error dict on failure.
    """
    try:
        result = service.tasklists().list().execute()
    except HttpError as exc:
        return google_tasks.handle_http_error(exc, "task lists")

    lists = result.get("items", [])

    # Exact name match (case-insensitive)
    ref_lower = ref.lower()
    exact = [lst for lst in lists if lst.get("title", "").lower() == ref_lower]
    if len(exact) == 1:
        return exact[0]["id"]
    if len(exact) > 1:
        return {"error": "ambiguous_list", "query": ref, "candidates": [
            {"id": lst["id"], "title": lst["title"]} for lst in exact
        ]}

    # Substring match
    sub = [lst for lst in lists if ref_lower in lst.get("title", "").lower()]
    if len(sub) == 1:
        return sub[0]["id"]
    if len(sub) > 1:
        return {"error": "ambiguous_list", "query": ref, "candidates": [
            {"id": lst["id"], "title": lst["title"]} for lst in sub
        ]}

    # Direct id match
    by_id = [lst for lst in lists if lst["id"] == ref]
    if by_id:
        return by_id[0]["id"]

    return {"error": "list_not_found", "query": ref, "available": [
        {"id": lst["id"], "title": lst["title"]} for lst in lists
    ]}


def resolve_task(service, list_id: str, ref: str, tasks: list[dict] | None = None) -> str | dict:
    """
    Resolve a task name or id to its id within a list.

    Same resolution order as resolve_list. Pass pre-fetched tasks to avoid
    a redundant API call.
    """
    if tasks is None:
        try:
            from tasks_bridge.google_tasks import fetch_all_tasks
            tasks = fetch_all_tasks(service, list_id, include_completed=True)
        except HttpError as exc:
            return google_tasks.handle_http_error(exc, "tasks")

    ref_lower = ref.lower()

    # Exact name match
    exact = [t for t in tasks if t.get("title", "").lower() == ref_lower]
    if len(exact) == 1:
        return exact[0]["id"]
    if len(exact) > 1:
        return {"error": "ambiguous_task", "query": ref, "candidates": [
            {"id": t["id"], "title": t.get("title", "")} for t in exact
        ]}

    # Substring match
    sub = [t for t in tasks if ref_lower in t.get("title", "").lower()]
    if len(sub) == 1:
        return sub[0]["id"]
    if len(sub) > 1:
        return {"error": "ambiguous_task", "query": ref, "candidates": [
            {"id": t["id"], "title": t.get("title", "")} for t in sub
        ]}

    # Direct id match
    by_id = [t for t in tasks if t["id"] == ref]
    if by_id:
        return by_id[0]["id"]

    return {"error": "task_not_found", "query": ref}
