"""Property tests of the public cleanup and ownership contract."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from qgis_sdk.core import ResourceScope


@given(
    view_cleanup_counts=st.lists(st.integers(min_value=0, max_value=4), max_size=5),
    plugin_cleanup_count=st.integers(min_value=0, max_value=4),
)
@settings(max_examples=80, deadline=None)
def test_closing_plugin_releases_every_view_then_plugin_once(
    view_cleanup_counts: list[int], plugin_cleanup_count: int
) -> None:
    released: list[str] = []
    plugin = ResourceScope()
    for callback_index in range(plugin_cleanup_count):
        plugin.on_close(
            lambda index=callback_index: released.append(f"plugin cleanup {index}")
        )
    views = []
    for view_index, cleanup_count in enumerate(view_cleanup_counts):
        view = plugin.child()
        views.append(view)
        for callback_index in range(cleanup_count):
            view.on_close(
                lambda view_id=view_index, index=callback_index: released.append(
                    f"view {view_id} cleanup {index}"
                )
            )

    plugin.close()
    plugin.close()

    expected = [
        f"view {view_index} cleanup {callback_index}"
        for view_index in reversed(range(len(view_cleanup_counts)))
        for callback_index in reversed(range(view_cleanup_counts[view_index]))
    ] + [
        f"plugin cleanup {callback_index}"
        for callback_index in reversed(range(plugin_cleanup_count))
    ]
    assert released == expected
    assert plugin.closed and all(view.closed for view in views)


@given(failing_indices=st.sets(st.integers(min_value=0, max_value=6)))
@settings(max_examples=80, deadline=None)
def test_failed_cleanup_cannot_prevent_remaining_callbacks(
    failing_indices: set[int],
) -> None:
    attempted: list[int] = []
    scope = ResourceScope()

    def cleanup(index: int) -> None:
        attempted.append(index)
        if index in failing_indices:
            raise ValueError(f"listener {index}")

    for index in range(7):
        scope.on_close(lambda index=index: cleanup(index))

    if failing_indices:
        with pytest.raises(ExceptionGroup) as caught:
            scope.close()
        assert [str(error) for error in caught.value.exceptions] == [
            f"listener {index}"
            for index in reversed(range(7))
            if index in failing_indices
        ]
    else:
        scope.close()

    scope.close()
    assert attempted == list(reversed(range(7)))
    assert scope.closed
