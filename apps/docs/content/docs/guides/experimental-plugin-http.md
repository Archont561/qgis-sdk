---
title: Experimental plugin HTTP API
description: Call explicitly exposed plugin actions and streams from outside QGIS.
---

The experimental local HTTP API lets an advanced host expose selected plugin
actions and streams without MCP. This API is not yet security-qualified for
production. Only use it with trusted clients and trusted plugin code; actions
can modify files and have other side effects. It binds only to `127.0.0.1`,
requires a bearer token, and refuses browser `Origin` headers. Token creation
currently requires POSIX; Windows ACL support is not implemented.

An advanced host must start `PluginHttpServer` on the runtime's QGIS owner
thread, after `runtime.start()`, and close it before unloading the runtime.
`post` must enqueue callbacks on that owner thread, not run them inline on an
HTTP thread. The server does nothing merely by being imported; there is no
automatic activation or Desktop consent UI.

```python
from pathlib import Path
from qgis.PyQt.QtCore import QObject, Qt, pyqtSignal
from qgis_sdk.http import PluginHttpServer

class GuiPost(QObject):
    submitted = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.submitted.connect(self._run, Qt.ConnectionType.QueuedConnection)

    def _run(self, callback):
        callback()

def start_http(runtime, private_directory: Path, report_cleanup_error):
    post = GuiPost()  # Keep this object alive alongside the server.
    server = PluginHttpServer(
        runtime,
        post=post.submitted.emit,
        token_file=private_directory / "plugin.token",
        actions=("my_action", "my_stream"),
        on_cleanup_error=report_cleanup_error,
    )
    server.start()
    return server, post
```

The host must create the private directory first; the token file must not
already exist. Protect the directory, keep the token secret, and give its path
only to trusted local clients. `server.port` is the assigned port. A host must
call `server.close()` before unloading; a non-owner may use
`server.wait_cleanup(timeout)` to wait for an asynchronous cleanup attempt.
Completion does not imply success, so supply `on_cleanup_error`. Never block the
owner thread while awaiting its own queued cleanup. An already-running action
can have effects even if the client disconnects or the host closes.

## Client

With `qgis-sdk-tools` installed outside QGIS:

```sh
qgis-sdk plugin describe --url http://127.0.0.1:PORT --token-file /private/plugin.token
qgis-sdk plugin call my_action --url http://127.0.0.1:PORT --token-file /private/plugin.token --args '{"value": 1}'
qgis-sdk plugin stream my_stream --url http://127.0.0.1:PORT --token-file /private/plugin.token --args '{}'
```

The stream command prints newline-delimited JSON frames until a terminal event.
The Python client exposes the same operations:

```python
from pathlib import Path
from qgis_sdk_tools.rest import PluginClient

client = PluginClient("http://127.0.0.1:PORT", token_file=Path("/private/plugin.token"))
print(client.describe())
print(client.call("my_action", {"value": 1}))
for frame in client.stream("my_stream", {}):
    print(frame)
```

The client raises `PluginClientError` carrying the HTTP status for any non-`200`
reply, refuses a response or stream frame larger than 1 MiB instead of parsing a
truncated body, and reports a `200` action reply that carries no `value` as
`PluginClientError` rather than a `KeyError`.

Calls are serialized per plugin runtime. A second request waits for its turn
for up to the server's deadline and then fails with `503` and the `host_busy`
code; it never runs inside another handler, and a handler that opens a modal
dialog cannot be re-entered. Requests that arrive while a handler is running
therefore queue rather than interleave. A call made from the thread that is
already running plugin work is refused immediately, so it cannot block the
owner thread until the deadline.

Closing the listener withdraws queued work, and the callers it withdrew still
answer `503` with the `host_reloaded` code. Those replies are written before the
connections are shut down: `close()` waits for the handlers already running, for
up to `close_grace` seconds (2 by default), and only then does it sever the
sockets. A handler still running after the grace is cut off, so a close never
hangs on a stuck action.

Refusals carry `{"error": {"code": ..., "message": ...}}`. `host_busy`,
`host_reloaded` and the per-plugin `capacity` session budget answer `503`,
because waiting or retrying can succeed; malformed input and failed operations
answer `400`. `PluginHttpServer.pending_requests` and `PluginHttpServer.busy`
report the dispatch state without exposing the internal queue.

At the HTTP level, `GET /plugin` returns the filtered description,
`POST /actions/<id>` calls an action with a JSON object, and
`POST /streams/<id>` returns server-sent events. Every request needs the bearer
token. Only IDs selected by the host are exposed. The directory is not a
sandbox and the client cannot confer additional access to the process.

## Support boundary

Creating the token file relies on POSIX file permissions. Windows credential
storage is not implemented, so `start()` refuses on a non-POSIX platform with a
`QgisSdkHttpError` that names the limitation, and creates no token or listener.
A host on Windows must not substitute a world-readable token; the rest of the
SDK, including the CLI MCP server, works there. This is a deliberate scope
decision for this release, not a transient bug.

Static imports of `qgis_sdk.http` opt the HTTP implementation into a built
plugin ZIP; it is otherwise excluded. The boundary is deliberate: MCP serves
developers and agents at the project level, while this HTTP API is the only
runtime interface for calling an opted-in plugin from outside QGIS. MCP does
not adapt this endpoint. This API remains experimental.
