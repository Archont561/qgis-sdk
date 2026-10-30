"""Which kind of process a plugin is running in, said out loud (decision-52).

Host detection is explicit: the host that builds a context says which one it
is, and ``ctx.host`` reports it. Nothing infers the host from an ``iface``,
from ``QgsApplication`` or from an environment variable, because a plugin that
guesses wrong does the wrong thing quietly - opening a window in a server, or
reaching for a canvas that does not exist.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["Host"]


class Host(StrEnum):
    """The three hosts one plugin class can run on.

    ``DESKTOP`` is a QGIS Desktop plugin loaded through ``classFactory``,
    ``SERVER`` a QGIS Server plugin loaded through ``serverClassFactory``, and
    ``APP`` a standalone PyQGIS application started by ``qgis_sdk.app.run``.
    """

    DESKTOP = "desktop"
    SERVER = "server"
    APP = "app"

    @property
    def gui(self) -> bool:
        """Whether this host has a user interface to open a surface in.

        Desktop and a standalone app with ``gui=True`` do; a server never does,
        which is what makes ``HOST001`` a finding rather than a preference.
        """
        return self is not Host.SERVER
