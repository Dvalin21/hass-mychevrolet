"""Parsing helpers for OnStar API responses.

The response shapes here are the verified contract for pyonstar 0.0.14 (a Python
port of OnStarJS): data commands return
``{"commandResponse": {"status": ..., "body": {...}}}`` and the body carries a
``diagnosticResponse`` list of ``{"name", "diagnosticElement": [{"name","value",
"message"}]}`` or a ``location`` dict. Kept in one place so every entity reads
the same paths.
"""

from __future__ import annotations

from typing import Any


def get_nested_value(
    data: Any, path: list[str], default: Any = None
) -> Any:
    """Safely walk ``path`` in ``data``, returning ``default`` if anything is missing."""
    current = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def get_diagnostics(data: Any) -> list[dict[str, Any]] | None:
    """Return the diagnostic element list, or None if unavailable."""
    if not isinstance(data, dict):
        return None
    diagnostics = get_nested_value(
        data, ["diagnostics", "commandResponse", "body", "diagnosticResponse"]
    )
    return diagnostics if isinstance(diagnostics, list) else None


def get_diagnostic_value(
    diagnostics: list[dict[str, Any]] | None,
    name: str,
    element_name: str | None = None,
) -> Any:
    """Return the ``value`` of diagnostic ``element_name`` (defaults to ``name``)."""
    if not diagnostics:
        return None
    element_name = element_name or name
    for diagnostic in diagnostics:
        if diagnostic.get("name") != name:
            continue
        for element in diagnostic.get("diagnosticElement", []):
            if element.get("name") == element_name and "value" in element:
                return element["value"]
    return None


def get_diagnostic_status(
    diagnostics: list[dict[str, Any]] | None, name: str
) -> str | None:
    """Return the ``message`` (e.g. tire-pressure status text) for a diagnostic."""
    if not diagnostics:
        return None
    for diagnostic in diagnostics:
        if diagnostic.get("name") == name:
            return diagnostic.get("status")
    return None


def get_location(data: Any) -> dict[str, Any] | None:
    """Return the ``location`` dict (latitude/longitude/...), or None."""
    if not isinstance(data, dict):
        return None
    location = get_nested_value(
        data, ["location", "commandResponse", "body", "location"]
    )
    return location if isinstance(location, dict) else None


def is_ev(diagnostics: list[dict[str, Any]] | None) -> bool:
    """An EV advertises an 'EV BATTERY LEVEL' diagnostic."""
    if not diagnostics:
        return False
    return any(d.get("name") == "EV BATTERY LEVEL" for d in diagnostics)
