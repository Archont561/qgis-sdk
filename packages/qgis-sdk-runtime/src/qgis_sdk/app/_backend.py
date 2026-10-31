"""What an application host needs from the toolkit it runs on: Qt, or a fake.

``qgis_sdk.app.run`` is the shell; this module is the seam. A backend owns the
``QgsApplication`` (``initQgis``/``exitQgis``), opens the main window when the app
is graphical, and spins the event loop. Everything the SDK decides - when the
runtime starts, which loops are named, how long shutdown may wait, what it
reports - lives in :mod:`qgis_sdk.app._session` and is proven against a fake, so
the toolkit is the only thing a native test has to bring.

Two objects, because they answer two different questions:

* :class:`AppBackend` is process-wide and lives exactly as long as ``run()``.
* :class:`AppSurface` is what one run got from the backend - a context, and the
  UI it may place bindings in. ``gui=False`` still has a surface: the context a
  headless app needs, with no window.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from qgis_sdk.core import NamedLoop, PluginContext, PluginRuntime
from qgis_sdk.core._application import QgisSdkPlugin

__all__ = ["AppBackend", "AppSurface"]


class AppSurface(Protocol):
    """What a backend built for one run: the context, and its UI if it has one."""

    @property
    def context(self) -> PluginContext:
        """The plugin context this surface offers, before the runtime starts."""

    def bind(self, runtime: PluginRuntime) -> tuple[NamedLoop, ...]:
        """Place the plugin's UI and start its loops; return the loops started.

        Called once, after the runtime started, on the thread that owns the
        event loop: this is where toolbar buttons, menu entries, surfaces and
        the job pump are created. A headless surface returns no loops.
        """

    def close(self) -> None:
        """Take the UI down again; safe to call twice and after ``bind`` failed."""


class AppBackend(Protocol):
    """The toolkit behind one ``qgis_sdk.app.run`` call."""

    def init(self, argv: Sequence[str], *, gui: bool) -> None:
        """Create the application and initialise it (``QgsApplication.initQgis``).

        ``gui`` is passed before any widget exists because it is a property of
        the application itself: Qt decides at construction whether a window
        system is used (``QgsApplication(argv, GUIenabled)``), and a window
        created under a non-GUI application is undefined behaviour rather than
        an error.
        """

    def build(self, app: QgisSdkPlugin, *, gui: bool, title: str) -> AppSurface:
        """Build the surface for this run: a window when ``gui``, else headless."""

    def exec(self) -> int:
        """Run the event loop until the app quits; return the process exit code."""

    def process_events(self) -> None:
        """Deliver what is already queued, without waiting: ``--once``'s one turn."""

    def quit(self) -> None:
        """Leave the event loop; safe to call before :meth:`exec`."""

    def exit(self) -> None:
        """Tear the application down (``QgsApplication.exitQgis``), exactly once."""
