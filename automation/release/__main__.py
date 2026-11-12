"""The ``python -m automation.release`` entry point.

The release workflow and the release tasks call the tool by module path, so the
package needs a runnable module; :func:`main` lives in :mod:`._main` and this
file only turns its return value into an exit status.
"""

from __future__ import annotations

from ._main import main

__all__ = ["main"]

if __name__ == "__main__":
    raise SystemExit(main())
