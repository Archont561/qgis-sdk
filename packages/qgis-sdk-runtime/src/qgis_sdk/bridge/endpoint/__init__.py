"""The roles one :class:`~qgis_sdk.bridge.dispatch.Dispatcher` is assembled from.

An endpoint answers a call the same way every time: read the envelope, check
that this view may make it, check the payload, run the handler, check the
result, reply. Each role here owns one stretch of that and the state it needs -
the registry holds what may be called, the views hold who may call it, the
streams hold what is already running, the calls hold the invocation itself -
and :class:`~qgis_sdk.bridge.dispatch.Dispatcher` is the object a caller sees:
one method per role method, and no logic of its own.

The split is by responsibility, not by size. A change that touches how a call is
authorized lands in :mod:`._views` and cannot reach the handler lookup in
:mod:`._registry`; a change to framing lands in :mod:`._streams` and cannot
reach the invocation path in :mod:`._calls`.
"""
