"""The developer tools of the QGIS SDK: what runs before a plugin exists in QGIS.

``qgis-sdk new`` (:mod:`.scaffold`), ``check`` (:mod:`.check`), ``test`` and
``dev`` (:mod:`.devtools`), ``bridge generate`` (:mod:`.generate`), the pytest
plugin and the Typer command itself live here, next to - never inside - the
runtime package ``qgis_sdk`` a plugin imports (decision-35). The boundary is
tested: this tree may import the runtime, Typer and pytest; the runtime never
imports this tree and nothing here is shipped in a plugin ZIP.
"""
