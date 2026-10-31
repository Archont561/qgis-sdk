"""Features, expressions and editing, as three Protocols a host can implement.

decision-54 point 3 makes features a service of its own rather than another
method on ``Layers``: a layer is a description, a feature is data, and the two
have different bounds (a layer list is a handful of rows, a feature list is a
dataset). The split also keeps the write path honest - :class:`Features` reads,
and editing is an explicitly opened :class:`EditingSession` the view owns.

No method here names a ``QgsFeature``, a ``QgsGeometry`` or a path: a feature
crosses as ids, plain attribute values and an encoded geometry, so the fake and
the native adapter answer the same shapes and a page cannot tell them apart.

The protocols are deliberately narrow. A caller that wants SQL, a provider
capability or the project's relations is asking a different question, and this
module would answer it badly.
"""

from __future__ import annotations

from typing import Protocol

from qgis_sdk.models.features import (
    EditOutcome,
    ExpressionCheck,
    ExpressionOutcome,
    Feature,
    FeaturePage,
    FeatureQuery,
    Geometry,
)

__all__ = ["EditingSession", "Features"]


class EditingSession(Protocol):
    """One open edit session over one layer, owned by one caller.

    A session buffers changes and writes them on :meth:`commit`. It is not a
    transaction in the database sense and the host cannot make it one: a
    provider that does not support atomic writes commits row by row, and the
    outcome says so rather than implying an atomicity the provider lacks
    (decision-54 status review). ``rollback`` discards the buffer, ``close`` does
    that too and ends the session; both are idempotent, because a closing view
    races the page all the time.
    """

    @property
    def id(self) -> str:
        """The host-minted id the page names in later calls."""
        ...

    @property
    def layer_id(self) -> str:
        """The layer this session edits."""
        ...

    @property
    def pending(self) -> int:
        """How many edits are buffered and not yet committed."""
        ...

    def add(
        self, attributes: dict[str, object], geometry: Geometry | None = None
    ) -> int:
        """Buffer one new feature and return the id the provider assigned."""
        ...

    def update(
        self,
        feature_id: int,
        attributes: dict[str, object] | None = None,
        geometry: Geometry | None = None,
    ) -> None:
        """Buffer a change to one existing feature; fields left out are untouched."""
        ...

    def delete(self, feature_id: int) -> None:
        """Buffer the deletion of one feature."""
        ...

    def commit(self) -> EditOutcome:
        """Write the buffered changes and report what happened."""
        ...

    def rollback(self) -> int:
        """Discard the buffered changes and return how many were dropped."""
        ...

    def close(self) -> None:
        """Roll back whatever is still buffered and end the session."""
        ...


class Features(Protocol):
    """Read a layer's features, evaluate expressions and open editing sessions.

    Every method raises ``QgisSdkLayerNotFoundError`` for an unknown layer, and a
    provider that cannot answer - a raster layer asked for features, an
    expression a provider cannot parse - raises
    ``QgisSdkUnsupportedCapabilityError`` rather than returning an empty result
    that a caller would read as "there is nothing there".
    """

    def page(self, layer_id: str, query: FeatureQuery) -> FeaturePage:
        """Return one bounded, deterministically ordered page of features.

        ``query.expression`` is evaluated by the provider, so a page never holds
        the whole layer to filter it; ``query.limit`` is the caller's ask and the
        implementation refuses anything above its own ceiling
        (``MAX_FEATURE_PAGE``) instead of silently returning fewer rows.
        """
        ...

    def feature(
        self, layer_id: str, feature_id: int, *, encoding: str = "wkb"
    ) -> Feature:
        """Return one feature by id, in the requested geometry encoding."""
        ...

    def evaluate(
        self,
        text: str,
        *,
        layer_id: str | None = None,
        feature_id: int | None = None,
    ) -> ExpressionOutcome:
        """Evaluate ``text``, optionally against a layer and one of its features.

        With no layer the expression is evaluated with the empty context: useful
        for arithmetic and string work, and the answer says ``valid: false`` when
        it needs a column that is not there.
        """
        ...

    def check(self, text: str, *, layer_id: str | None = None) -> ExpressionCheck:
        """Parse ``text`` without running it, and say whether it would run."""
        ...

    def begin_edit(self, layer_id: str) -> EditingSession:
        """Open an editing session over ``layer_id``.

        A provider that cannot edit (a read-only source, a raster layer) raises
        here, by name, rather than at the first write: a caller learns before it
        has buffered anything.
        """
        ...
