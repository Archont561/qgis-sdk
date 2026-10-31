"""``python -m simple``: the reference plugin as a standalone PyQGIS app.

The declaration is the one QGIS Desktop loads through ``classFactory``
(``simple.plugin:app``, named in ``pyproject.toml``); here ``qgis_sdk.app`` owns
the ``QgsApplication`` instead, with no ``iface`` and no plugin lifecycle - the
third host of decision-52 point 3. ``qgis-sdk run`` starts this module, and
``qgis-sdk build --target app`` installs it as a console script, so the entry
stays the same three lines whatever starts it.

Two things a reader should see side by side:

* the bridge is unchanged - a page in ``web/`` reaches the same
  ``runtime.actions`` through the same grants and the same WebChannel transport
  as inside QGIS Desktop, because the host wraps the same runtime;
* the flags are the runtime's, not this file's: ``--headless`` runs the workflow
  without a window (a batch job over the fixture, or CI), ``--once`` starts and
  stops so a script can prove the app is healthy, and everything after ``--``
  goes to Qt.
"""

from __future__ import annotations

from collections.abc import Sequence

from qgis_sdk.app import main as run_app

from .plugin import app


def main(argv: Sequence[str] | None = None) -> int:
    """Run Simple; close the window (or Ctrl+C) to leave."""
    return run_app(app, argv)


if __name__ == "__main__":
    raise SystemExit(main())
