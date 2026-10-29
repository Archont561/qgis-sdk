"""Experimental, explicitly hosted loopback transport for bridge envelopes.

Importing this module never starts a listener. A host must construct and start
an :class:`PluginHttpServer` on the runtime's owning GUI thread, provide an owner
scheduler, and close it before unloading the runtime. The transport is not MCP.
It is experimental and is not automatically enabled by project metadata.
"""

from ._server import PluginHttpServer, QgisSdkHttpError

__all__ = ["PluginHttpServer", "QgisSdkHttpError"]
