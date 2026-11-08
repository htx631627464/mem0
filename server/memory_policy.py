"""Drop memories whose text is an English "User ..." narration."""

from __future__ import annotations

USER_PREFIX = "User "


def is_user_narration(text: str | None) -> bool:
    return bool(text) and text.startswith(USER_PREFIX)


def drop_user_narration(memory, response):
    """Delete stored rows that start with "User " and remove them from the response."""
    if not isinstance(response, dict):
        return response
    results = response.get("results")
    if not isinstance(results, list):
        return response
    kept = []
    for item in results:
        text = item.get("memory") if isinstance(item, dict) else None
        memory_id = item.get("id") if isinstance(item, dict) else None
        if is_user_narration(text) and memory_id and item.get("event", "ADD") == "ADD":
            memory.delete(memory_id)
            continue
        kept.append(item)
    response["results"] = kept
    return response
