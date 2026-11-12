"""An in-memory ``Features`` backend: pages, filters, expressions and editing.

The fake exists so the contract can be exercised without QGIS: the same page
shapes, the same deterministic ordering, the same refusals. It is honest about
its bounds - the expression subset in :mod:`qgis_sdk.testing.expressions` is not
``QgsExpression`` - and it makes the parts of editing the native adapter cannot
guarantee explicit, because a fake is the one place where a test can say which
guarantee it is asserting.

Editing here behaves like the providers this SDK supports best: a buffer that is
written on commit, an id the fake assigns for an add, and a rollback that
discards. ``atomic=False`` models the providers that write row by row, so a test
can prove the outcome says so instead of implying a transaction the provider does
not have.
"""

from __future__ import annotations

from ._features import FakeFeatures
from ._layer import FakeLayer
from ._session import FakeEditingSession

__all__ = ["FakeEditingSession", "FakeFeatures", "FakeLayer"]
