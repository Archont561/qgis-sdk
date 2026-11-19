"""``ResultTable``: rows of plain mappings under named columns."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.ui.components import split_name_and_children
from qgis_sdk.ui.form_fields import label_for

from ._feedback import _Feedback

__all__ = ["ResultTable"]


def _columns_of(
    table: ResultTable, columns: Sequence[str | tuple[str, str]]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    keys: list[str] = []
    headings: list[str] = []
    for column in columns:
        key, heading = (
            (column, label_for(column)) if isinstance(column, str) else column
        )
        if not key or key in keys:
            raise QgisSdkUiError(
                f"{table._describe()}: column keys must be unique, got {key!r}"
            )
        keys.append(key)
        headings.append(heading)
    if not keys:
        raise QgisSdkUiError(f"{table._describe()} needs at least one column")
    return tuple(keys), tuple(headings)


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


class ResultTable(_Feedback):
    """Rows of plain mappings under named columns, one of them selectable.

    ``columns`` are the keys read from every row (``("name", "count")``) or
    ``(key, heading)`` pairs; a row missing a key shows an empty cell.
    ``set_rows`` replaces the rows and clears the selection; ``select(i)``
    picks a row (``None`` clears), ``selected()`` reads the index and
    ``changed`` hears the user's picks too.

    Args:
        name: The component's name in the surface.
        columns: The column names to show, in order.
        label: The text shown above it.
    """

    def __init__(
        self,
        name: str | Sequence[str | tuple[str, str]] | None = None,
        columns: Sequence[str | tuple[str, str]] | None = None,
        *,
        label: str | None = None,
    ) -> None:
        # ``ResultTable(["id", "name"])`` and ``ResultTable(columns=[...])``
        # both leave the name to the class attribute (decision-55).
        """Build the table over its columns.

        Args:
            name: The table's name in the surface, or its columns.
            columns: The column names to show, in order.
            label: The text shown above it.
        """
        name, columns = split_name_and_children("ResultTable", name, columns)  # type: ignore[assignment]
        super().__init__(name, label=label)
        self.columns, self.headings = _columns_of(self, columns)
        self._rows: tuple[Mapping[str, Any], ...] = ()
        self._selected: int | None = None

    def rows(self) -> tuple[Mapping[str, Any], ...]:
        return self._rows

    def set_rows(self, rows: Sequence[Mapping[str, Any]]) -> None:
        """Replace every row; the selection is cleared.

        Args:
            rows: The row mappings to show.
        """
        checked: list[Mapping[str, Any]] = []
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                raise QgisSdkUiError(
                    f"{self._describe()}: row {index} must be a mapping, "
                    f"got {type(row).__name__}"
                )
            checked.append(dict(row))
        self._rows = tuple(checked)
        self._selected = None
        self._sync()
        self._notify(None)

    def cells(self) -> tuple[tuple[str, ...], ...]:
        """Every row as text cells in column order; what the widget shows."""
        return tuple(
            tuple(_cell(row.get(key)) for key in self.columns) for row in self._rows
        )

    def selected(self) -> int | None:
        """The index of the selected row, or ``None``."""
        return self._selected

    def selected_row(self) -> Mapping[str, Any] | None:
        """The selected row itself, or ``None``."""
        return None if self._selected is None else self._rows[self._selected]

    def select(self, index: int | None) -> None:
        """Select row ``index`` (``None`` clears); out of range is refused.

        Args:
            index: Which row to select, counting from zero.
        """
        if index is not None and not 0 <= index < len(self._rows):
            raise QgisSdkUiError(
                f"{self._describe()} has {len(self._rows)} rows; "
                f"cannot select {index!r}"
            )
        if index == self._selected:
            return
        self._selected = index
        self._sync()
        self._notify(index)

    def snapshot(self) -> dict[str, Any]:
        node = super().snapshot()
        node["columns"] = list(self.columns)
        node["rows"] = [list(cells) for cells in self.cells()]
        node["selected"] = self._selected
        return node

    def _state(self) -> object:
        return (self.cells(), self._selected)

    def _from_widget(self, value: object) -> None:
        if self._syncing:
            return
        index = (
            value if isinstance(value, int) and 0 <= value < len(self._rows) else None
        )
        if index != self._selected:
            self._selected = index
            self._notify(index)
