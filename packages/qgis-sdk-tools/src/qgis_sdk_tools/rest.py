"""Client for an explicitly hosted local plugin HTTP server."""

from __future__ import annotations

import http.client
import json
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote, urlsplit

# The server never emits a larger response, so a longer body means the client
# and the host disagree; say so instead of failing inside the JSON parser.
_RESPONSE_LIMIT = 1024 * 1024


class PluginClientError(Exception):
    """The local plugin server refused a request or could not be reached."""


class PluginClient:
    """Connect to an explicitly hosted loopback plugin using its private token."""

    def __init__(self, url: str, *, token_file: Path, timeout: float = 10) -> None:
        parsed = urlsplit(url)
        try:
            port = parsed.port
        except ValueError as error:
            raise PluginClientError("Invalid plugin URL") from error
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or port is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise PluginClientError("Plugin URL must be http://127.0.0.1:<port>")
        self._port = port
        self._token_file = Path(token_file)
        self._timeout = timeout

    def _open(self, method: str, path: str, payload: dict | None = None):
        connection = None
        try:
            token = self._token_file.read_text(encoding="ascii").strip()
            connection = http.client.HTTPConnection(
                "127.0.0.1", self._port, timeout=self._timeout
            )
            body = None if payload is None else json.dumps(payload, allow_nan=False)
            headers = {"Authorization": f"Bearer {token}"}
            if payload is not None:
                headers["Content-Type"] = "application/json"
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
        except (OSError, ValueError, UnicodeError, http.client.HTTPException) as error:
            if connection is not None:
                connection.close()
            raise PluginClientError(str(error)) from error
        if response.status != 200:
            body = response.read(_RESPONSE_LIMIT).decode("utf-8", errors="replace")
            connection.close()
            raise PluginClientError(f"Plugin HTTP {response.status}: {body}")
        return connection, response

    def _json(self, method: str, path: str, payload: dict | None = None) -> dict:
        connection, response = self._open(method, path, payload)
        try:
            body = response.read(_RESPONSE_LIMIT + 1)
        except (OSError, http.client.HTTPException) as error:
            raise PluginClientError(str(error)) from error
        finally:
            connection.close()
        if len(body) > _RESPONSE_LIMIT:
            raise PluginClientError(f"Plugin response exceeds {_RESPONSE_LIMIT} bytes")
        try:
            value = json.loads(body)
        except ValueError as error:
            raise PluginClientError(str(error)) from error
        if not isinstance(value, dict):
            raise PluginClientError("Invalid plugin response")
        return value

    def describe(self) -> dict:
        """Return the plugin's explicitly exposed action and stream descriptions."""
        return self._json("GET", "/plugin")

    def call(self, action: str, arguments: dict) -> object:
        """Invoke one exposed action with JSON arguments."""
        reply = self._json("POST", "/actions/" + quote(action, safe=""), arguments)
        if "value" not in reply:
            raise PluginClientError("Plugin response has no value")
        return reply["value"]

    def stream(self, stream: str, arguments: dict) -> Iterator[dict]:
        """Yield stream frames. Close the iterator early to disconnect."""
        connection, response = self._open(
            "POST", "/streams/" + quote(stream, safe=""), arguments
        )
        try:
            if response.getheader("Content-Type") != "text/event-stream":
                raise PluginClientError("Invalid stream response")
            while True:
                line = response.readline(_RESPONSE_LIMIT + 1)
                if not line:
                    raise PluginClientError("Stream ended without a terminal frame")
                if len(line) > _RESPONSE_LIMIT:
                    raise PluginClientError(
                        f"Stream frame exceeds {_RESPONSE_LIMIT} bytes"
                    )
                if line.startswith(b"data: "):
                    frame = json.loads(line[6:])
                    if not isinstance(frame, dict):
                        raise PluginClientError("Invalid stream frame")
                    yield frame
                    if "terminal" in frame:
                        return
        except (OSError, ValueError, http.client.HTTPException) as error:
            raise PluginClientError(str(error)) from error
        finally:
            connection.close()
