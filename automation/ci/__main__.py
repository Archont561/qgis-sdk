"""The ``python -m automation.ci`` entry point.

A package is not runnable on its own, and every workflow step, the LTS harness
and the ``run_logged`` wrapper call this tool by module path rather than through
a console script - there is no installed ``qgis-sdk-ci`` to call. This module is
the one place the process is created; :func:`main` is the whole implementation.
"""

from __future__ import annotations

from ._main import main

__all__ = ["main"]

if __name__ == "__main__":
    raise SystemExit(main())
