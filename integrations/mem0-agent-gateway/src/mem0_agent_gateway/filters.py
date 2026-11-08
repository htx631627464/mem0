from __future__ import annotations

from typing import Any

ENTITY_KEYS = {"user_id", "agent_id", "run_id"}


def normalize_filters(value: Any, *, map_app_id: bool = True) -> Any:
    if isinstance(value, list):
        return [normalize_filters(item, map_app_id=map_app_id) for item in value]
    if not isinstance(value, dict):
        return value

    if set(value.keys()) == {"metadata"} and isinstance(value.get("metadata"), dict):
        return normalize_filters(value["metadata"], map_app_id=map_app_id)

    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"AND", "OR", "NOT"}:
            if isinstance(item, list):
                normalized[key] = [normalize_filters(child, map_app_id=map_app_id) for child in item]
            else:
                normalized[key] = normalize_filters(item, map_app_id=map_app_id)
            continue

        if key == "metadata" and isinstance(item, dict):
            normalized.update(normalize_filters(item, map_app_id=map_app_id))
            continue

        if key in {"app_id", "appId"}:
            target_key = "agent_id" if map_app_id else "app_id"
            normalized[target_key] = normalize_filters(item, map_app_id=map_app_id)
            continue

        normalized[_camel_entity_key(key)] = normalize_filters(item, map_app_id=map_app_id)
    return normalized


def flatten_filters(filters: Any, *, map_app_id: bool = False) -> dict[str, Any]:
    """Flatten AND/metadata filters for Platform API request bodies."""
    flat: dict[str, Any] = {}

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if not isinstance(node, dict):
            return
        for key, value in node.items():
            if key == "AND":
                visit(value)
            elif key in {"OR", "NOT"}:
                continue
            elif key == "metadata" and isinstance(value, dict):
                visit(value)
            else:
                normalized = normalize_filters({key: value}, map_app_id=map_app_id)
                flat.update(normalized)

    visit(filters)
    return flat


def extract_entities(filters: Any) -> dict[str, str]:
    entities: dict[str, str] = {}

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if not isinstance(node, dict):
            return
        for key, value in node.items():
            if key in {"AND", "NOT"}:
                visit(value)
            elif key == "OR":
                continue
            elif key in ENTITY_KEYS and isinstance(value, str) and value != "*":
                entities.setdefault(key, value)

    visit(normalize_filters(filters))
    return entities


def memory_matches_filter(memory: dict[str, Any], filters: Any, *, map_app_id: bool = True) -> bool:
    normalized = normalize_filters(filters, map_app_id=map_app_id)
    if not normalized:
        return True
    return _match_node(memory, normalized)


def _match_node(memory: dict[str, Any], node: Any) -> bool:
    if isinstance(node, list):
        return all(_match_node(memory, item) for item in node)
    if not isinstance(node, dict):
        return True

    for key, expected in node.items():
        if key == "AND":
            children = expected if isinstance(expected, list) else [expected]
            if not all(_match_node(memory, child) for child in children):
                return False
            continue
        if key == "OR":
            children = expected if isinstance(expected, list) else [expected]
            if not any(_match_node(memory, child) for child in children):
                return False
            continue
        if key == "NOT":
            children = expected if isinstance(expected, list) else [expected]
            if any(_match_node(memory, child) for child in children):
                return False
            continue

        actual = _memory_value(memory, key)
        if not _value_matches(actual, expected):
            return False
    return True


def _memory_value(memory: dict[str, Any], key: str) -> Any:
    metadata = memory.get("metadata") if isinstance(memory.get("metadata"), dict) else {}
    if key == "agent_id":
        return memory.get("agent_id") or metadata.get("app_id")
    if key == "app_id":
        return memory.get("app_id") or metadata.get("app_id") or memory.get("agent_id")
    if key in memory:
        return memory.get(key)
    return metadata.get(key)


def _value_matches(actual: Any, expected: Any) -> bool:
    if expected == "*":
        return actual not in {None, ""}
    if isinstance(expected, dict):
        if "exists" in expected:
            exists = actual not in {None, ""}
            return exists is bool(expected["exists"])
        if "eq" in expected:
            return actual == expected["eq"]
        if "ne" in expected:
            return actual != expected["ne"]
        if "in" in expected and isinstance(expected["in"], list):
            return actual in expected["in"]
        if "nin" in expected and isinstance(expected["nin"], list):
            return actual not in expected["nin"]
        if "contains" in expected:
            return str(expected["contains"]) in str(actual or "")
        if "icontains" in expected:
            return str(expected["icontains"]).lower() in str(actual or "").lower()
    return actual == expected


def _camel_entity_key(key: str) -> str:
    return {
        "userId": "user_id",
        "agentId": "agent_id",
        "runId": "run_id",
    }.get(key, key)
