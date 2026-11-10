"""The listener's failure vocabulary: one exception, and the status a code maps to."""

from __future__ import annotations

from typing import Any

from qgis_sdk.models.errors import QgisSdkError

# Retryable server conditions answer 503; anything else is the caller's fault.
ERROR_STATUS = {"host_busy": 503, "host_reloaded": 503, "capacity": 503}
"""The codes that are worth retrying, and the status each one answers."""


class QgisSdkHttpError(QgisSdkError):
    """An HTTP listener could not be started safely."""

    code = "http_error"


def error_status(payload: dict[str, Any]) -> int:
    """The status an error reply answers: 503 when retrying could help, else 400."""
    code = payload.get("error", {}).get("code")
    return ERROR_STATUS.get(code, 400)
