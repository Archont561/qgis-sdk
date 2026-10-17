"""Allow ``python -m qgis_sdk_release`` invocation from Pixi tasks."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
