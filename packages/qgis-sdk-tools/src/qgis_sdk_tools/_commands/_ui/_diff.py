"""The JSON form of one structural diff."""

from __future__ import annotations

from typing import Any

__all__ = ["diff_payload"]


def diff_payload(difference) -> dict[str, Any]:
    """The JSON form of one structural diff, including its pixel-only changes."""
    return {
        "structural": bool(difference),
        "identical": difference.identical,
        "changes": [
            {
                "where": change.where,
                "field": change.field,
                "before": change.before,
                "after": change.after,
            }
            for change in difference.changes
        ],
        "pixels": [
            {"where": change.where, "field": change.field}
            for change in difference.pixels
        ],
    }
