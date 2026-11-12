"""Assemble every PyQGIS-backed service into one ``PluginContext``.

``qgis_sdk.adapters.desktop.host()`` is the one place that knows a plugin is
running inside QGIS Desktop (decision-43). This module is what it calls there -
or what a plugin's own ``context_factory`` calls - so a plugin gets the whole
curated surface - layers, project, settings, styles, Processing, the
task-manager worker backend and the network client - on ``self.ctx`` with one
line, and the web view built from the same context
(``HostServices.from_context``) answers from the very same instances.
Everything is owned by the scope passed in: closing it releases the layers,
aborts the requests in flight and stops new submissions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qgis_sdk.bridge.authority import HostAuthority
from qgis_sdk.core import Host, PluginContext, PluginServices, ResourceScope
from qgis_sdk.files import FilesService
from qgis_sdk.network import NetworkClient
from qgis_sdk.services import Notifications

from .algorithms import AlgorithmWiring, NativeAlgorithms
from .canvas import NativeCanvas
from .features import NativeFeatures
from .layers import NativeLayers
from .layouts import NativeLayouts
from .log import NativeLog
from .network import NativeNetworkTransport
from .notifications import NativeNotifications
from .processing import NativeProcessing, ProcessingServices
from .project import NativeProject
from .rasters import NativeRasters
from .settings import NativeSettings
from .styles import NativeStyles
from .tasks import QgsTaskWorkers


def _cc_expr1_kw1(_s):
    return {
        "host": _s.options.host,
        "desktop": None
        if _s.options.iface is None
        else IfaceDesktopAccess(_s.options.iface),
        "network": NetworkClient(_s.transport, _s.scope),
        "layers": _s.layers,
        "rasters": _s.rasters,
        "features": _s.features,
        "layouts": _s.layouts,
        "canvas": _s.canvas_service,
    }


def _cc_expr1_kw2(_s):
    return {
        "project": _s.project,
        "settings": NativeSettings(_s.scope, prefix=_s.options.settings_prefix),
        "styles": NativeStyles(_s.layers, _s.scope),
        "algorithms": _s.algorithms,
        "workers": _s.workers,
    }


def _cc_expr1_kw3(_s):
    return {
        "processing": NativeProcessing(
            ProcessingServices(
                layers=_s.layers,
                algorithms=_s.algorithms,
                project=_s.project,
                scope=_s.scope,
                authority=_s.authority,
                rasters=_s.rasters,
            )
        )
    }


def _cc_expr1_kw4(_s):
    return {"files": _s.files, "log": NativeLog(_s.scope, _s.options.settings_prefix)}


def _cc_expr1_call5(_s):
    args = []
    kwargs = {}
    kwargs.update(_cc_expr1_kw1(_s))
    kwargs.update(_cc_expr1_kw2(_s))
    kwargs.update(_cc_expr1_kw3(_s))
    kwargs.update(_cc_expr1_kw4(_s))
    return PluginServices(*args, **kwargs)


def _cc_expr1_args6(_s):
    return [
        _s.options.notifications
        if _s.options.notifications is not None
        else NativeNotifications(_s.scope),
        _s.scope,
        _cc_expr1_call5(_s),
    ]


def _cc_expr1_call7(_s):
    args = []
    args.extend(_cc_expr1_args6(_s))
    kwargs = {}
    return PluginContext(*args, **kwargs)


def _cc_expr1_args8(_s):
    return [_cc_expr1_call7(_s)]


def _cc_expr1_call9(_s):
    args = []
    args.extend(_cc_expr1_args8(_s))
    kwargs = {}
    return _CcReturn(*args, **kwargs)


def _cc_expr1_apply(_s):
    return _cc_expr1_call9(_s)


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


def _cc_native_plugin_co_p1(_s):
    _s.scope.ensure_open()
    # The raster adapter is built first and the vector one holds it: a raster is
    # a layer too, so ``ctx.layers.list_layers`` answers both kinds and a raster
    # id reaching a vector-only method is refused by name rather than reported
    # missing (TASK-87).
    _s.rasters = NativeRasters(_s.scope)
    _s.layers = NativeLayers(_s.scope, rasters=_s.rasters)
    _s.transport = NativeNetworkTransport(_s.scope)
    _s.project = NativeProject(_s.layers, _s.scope, rasters=_s.rasters)
    _s.features = NativeFeatures(_s.layers, _s.scope)


def _cc_native_plugin_co_p2(_s):
    # A canvas is a view, so the capability exists when there is one behind it:
    # the Desktop interface, an app window's own widget, or a server, which keeps
    # the capability to refuse by name rather than pretend a request has a map
    # somebody pans. A bare QgsApplication has no view, and `ctx.has("canvas")`
    # says so instead of handing back a service that refuses every call.
    _s.canvas_service: NativeCanvas | None = None
    if _s.options.host is Host.SERVER:
        _s.canvas_service = NativeCanvas(
            _s.scope, layers=_s.layers, host=_s.options.host
        )
    elif _s.options.iface is not None or _s.options.canvas is not None:
        _s.canvas_service = NativeCanvas(
            _s.scope, layers=_s.layers, iface=_s.options.iface, canvas=_s.options.canvas
        )


def _cc_native_plugin_co_p3(_s):
    # One authority per runtime (decision-20): the refs Processing mints for
    # a toolbox run, the ones a page receives through ``HostServices``, the
    # ones the form components hand a handler and the file outputs of
    # ``ctx.algorithms.run`` all resolve through it.
    _s.authority = HostAuthority()
    _s.files = FilesService(
        _s.authority, _s.scope, owner=f"plugin:{_s.options.settings_prefix}"
    )
    # One worker backend for the context: the layouts service renders through
    # it exactly as ``ctx.jobs`` does, so an export or a batch is one task in
    # the task bar.
    _s.workers = QgsTaskWorkers(_s.scope)


def _cc_native_plugin_co_p4(_s):
    _s.algorithms = NativeAlgorithms(
        AlgorithmWiring(
            layers=_s.layers,
            scope=_s.scope,
            working_directory=_s.options.working_directory,
            files=_s.files,
            workers=_s.workers,
        )
    )
    _s.layouts = NativeLayouts(_s.scope, workers=_s.workers, files=_s.files)


def _cc_native_plugin_co_p5(_s):
    return _cc_expr1_apply(_s)


@dataclass(frozen=True, slots=True)
class IfaceDesktopAccess:
    """``DesktopAccess`` over the ``QgisInterface`` QGIS handed ``classFactory``."""

    iface: object


@dataclass(frozen=True, slots=True)
class NativeContextOptions:
    """What a Desktop host may vary when it assembles the plugin context.

    ``settings_prefix`` scopes the settings service to this plugin's keys; the
    rest are the host's own objects - the ``QgisInterface`` it was created with,
    the desktop access, the working directory temporary outputs land in, and the
    ``Host`` the context states it belongs to (decision-52).
    """

    settings_prefix: str
    iface: object | None = None
    notifications: Notifications | None = None
    working_directory: Path | None = None
    host: Host = Host.DESKTOP
    canvas: object | None = None


def native_plugin_context(
    scope: ResourceScope, options: NativeContextOptions
) -> PluginContext:
    "Build the plugin context a QGIS Desktop host offers.\n\n    ``settings_prefix`` scopes the settings service to this plugin's keys in\n    the QGIS profile. ``iface`` becomes ``ctx.desktop``; without one (a\n    standalone ``QgsApplication``) reading ``ctx.desktop`` refuses by name,\n    and the other services still work. ``notifications`` defaults to the QGIS message log;\n    a plugin passes its own to reach the message bar. ``working_directory``\n    is where Processing outputs land; left out, the service owns a temporary\n    directory and removes it with the scope. ``processing`` is the registry\n    ``PluginRuntime.start()`` advertises the plugin's ``providers`` with.\n    ``log`` writes to the QGIS message log under ``settings_prefix`` as its tag.\n    ``host`` is what ``ctx.host`` reports: Desktop by default, and the standalone\n    app host says ``Host.APP`` without touching anything else here. ``canvas`` is\n    the ``QgsMapCanvas`` an app window owns; a Desktop host resolves its own from\n    ``iface.mapCanvas()`` at the first call.\n"
    _s = _CcState(scope=scope, options=options)
    for _p in (
        _cc_native_plugin_co_p1,
        _cc_native_plugin_co_p2,
        _cc_native_plugin_co_p3,
        _cc_native_plugin_co_p4,
        _cc_native_plugin_co_p5,
    ):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None
