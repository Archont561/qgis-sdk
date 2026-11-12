"""The requests-like client over an injected transport (decision-4).

:class:`NetworkClient` is what a host injects as ``ctx.network``. It validates
and resolves a request into a :class:`NetworkRequest`, hands it to the transport,
and suspends the calling job on a :class:`Handoff` until the transport delivers.
Nothing here blocks: the coroutine form yields to the step scheduler, and the
blocking form is a separate object the transport may refuse on the GUI thread.

Ownership follows the scope the client was built with: closing it cancels what
is in flight, and a request started after that is refused. Cancellation of the
awaiting job - thrown in at the suspension point by the scheduler - cancels the
transport request on the way out, so a cancelled job leaves no socket behind.

One :class:`~qgis_sdk.services.network.RequestOptions` mapping carries the
per-call knobs and one :class:`~qgis_sdk.services.network.ConfigureOptions`
mapping carries a derived client's overrides (decision-81). The keyword-call
form is unchanged: ``Unpack`` keeps the names statically typed while each
method takes one parameter. Both mappings are parsed into frozen records before
any transport is touched, so defaults and limit checks live in one place.
"""

from __future__ import annotations

from ._clients import BlockingNetworkClient, NetworkClient
from ._request import NetworkDefaults, build_request

__all__ = ["BlockingNetworkClient", "NetworkClient", "NetworkDefaults", "build_request"]
