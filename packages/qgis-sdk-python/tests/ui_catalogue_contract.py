"""The container, feedback and button contract both renderings meet (TASK-96 AC 2).

Not a test module itself: ``test_ui_catalogue.py`` runs these against the
fake rendering (attached, never mounted) and ``test_ui_catalogue_native.py``
against the mounted widgets under a ``QgsApplication``, through the same
``rendering`` fixture :mod:`ui_component_contract` provides.
"""

from __future__ import annotations

import pytest
from qgis_sdk.jobs import JobStatus
from qgis_sdk.models import QgisSdkUiError
from qgis_sdk.ui import (
    AcceptCancel,
    Button,
    Column,
    Custom,
    Group,
    JobProgress,
    LogView,
    Number,
    Panel,
    ResultTable,
    Row,
    RunButton,
    Tabs,
    Text,
    Toggle,
    snapshot_names,
    ui_snapshot,
)
from ui_component_contract import Rendering

# -- containers -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "factory",
    [
        lambda children: Column("root", children),
        lambda children: Row("root", children),
        lambda children: Panel("root", children),
        lambda children: Panel("root", children, scrollable=True),
        lambda children: Group("root", children, label="Options"),
        lambda children: Group("root", children, collapsible=True),
        lambda children: Tabs("root", children),
    ],
    ids=["column", "row", "panel", "scrolling", "group", "collapsible", "tabs"],
)
def test_every_container_attaches_its_children_and_finds_them_by_name(
    rendering: Rendering, factory
) -> None:
    note = Text("note")
    inner = Column("inner", [Toggle("enabled"), Number("count")])
    root = rendering.attach(factory([note, inner]))

    assert root.children() == (note, inner)
    assert all(child.attached for child in (note, inner, *inner.children()))
    assert root.find("count") is inner.find("count")
    assert root.object_name == "root"
    with pytest.raises(QgisSdkUiError, match="no child named 'missing'"):
        root.find("missing")

    names = snapshot_names(ui_snapshot(root))
    assert names == ("root", "form/note", "inner", "form/enabled", "form/count")

    rendering.scope.close()
    assert not any(child.attached for child in (root, note, inner))


def test_a_container_refuses_two_children_with_one_name() -> None:
    with pytest.raises(QgisSdkUiError, match="two children named 'form/a'"):
        Row("root", [Text("a"), Text("a")])
    with pytest.raises(QgisSdkUiError, match="children must be components"):
        Row("root", ["a"])  # type: ignore[list-item]


def test_tabs_show_one_page_at_a_time_and_report_switches(
    rendering: Rendering,
) -> None:
    seen: list[str] = []
    tabs = rendering.attach(
        Tabs(
            "pages",
            [Column("input", [Text("note")]), Column("output", [Text("result")])],
        )
    )
    tabs.changed(seen.append)

    assert tabs.pages == ("input", "output")
    assert tabs.current() == "input"
    tabs.set_current("output")
    assert tabs.current() == "output"
    assert seen == ["output"]
    tabs.set_current("output")
    assert seen == ["output"]
    with pytest.raises(QgisSdkUiError, match="no page 'other'"):
        tabs.set_current("other")
    assert tabs.current() == "output"
    assert tabs.snapshot()["current"] == "output"
    if rendering.native:
        assert tabs.widget.currentIndex() == 1
        assert tabs.widget.tabText(0) == "Input"
        tabs.widget.setCurrentIndex(0)
        assert tabs.current() == "input"
        assert seen == ["output", "input"]

    with pytest.raises(QgisSdkUiError, match="at least one page"):
        Tabs("empty", [])
    assert Tabs("t", [Column("a", []), Column("b", [])], current="b").current() == "b"


# -- feedback: JobProgress --------------------------------------------------------------


def test_job_progress_follows_a_handle_to_success(rendering: Rendering) -> None:
    progress = rendering.attach(JobProgress("job"))
    seen: list[str] = []
    progress.changed(seen.append)
    assert progress.status == "idle"
    assert progress.cancel() is False

    handle = rendering.ctx.actions.sum_slowly(a=1, b=2)
    progress.bind(handle)
    assert progress.handle is handle
    assert progress.status == "queued"
    rendering.tick()

    assert progress.status == "succeeded"
    assert progress.fraction == 1.0
    assert progress.message == ""
    assert seen[0] == "queued"
    assert "running" in seen
    assert seen[-1] == "succeeded"
    assert progress.snapshot()["job"] == handle.id
    if rendering.native:
        bar = progress.widget.findChild(object, "feedback/job/bar")
        assert bar.value() == 100
        cancel = progress.widget.findChild(object, "feedback/job/cancel")
        assert cancel.isEnabled() is False


def test_job_progress_shows_a_failure_and_can_cancel(rendering: Rendering) -> None:
    progress = rendering.attach(JobProgress("job"))

    failing = rendering.ctx.actions.sum_slowly(a=1, b=2, fail=True)
    progress.bind(failing)
    rendering.tick()
    assert progress.status == "failed"
    assert progress.message == "no sum today"
    if rendering.native:
        label = progress.widget.findChild(object, "feedback/job/message")
        assert label.text() == "no sum today"

    cancelled = rendering.ctx.actions.sum_slowly(a=3, b=4)
    progress.bind(cancelled)
    assert progress.message == ""
    if rendering.native:
        progress.widget.findChild(object, "feedback/job/cancel").click()
    else:
        assert progress.cancel() is True
    rendering.tick()
    assert cancelled.status is JobStatus.CANCELLED
    assert progress.status == "cancelled"

    progress.reset()
    assert (progress.status, progress.handle) == ("idle", None)
    with pytest.raises(QgisSdkUiError, match="takes a job handle"):
        progress.bind(object())


def test_job_progress_stops_listening_when_the_scope_closes(
    rendering: Rendering,
) -> None:
    progress = rendering.attach(JobProgress("job"))
    handle = rendering.ctx.actions.sum_slowly(a=1, b=2)
    progress.bind(handle)
    rendering.scope.close()
    rendering.tick()

    assert handle.status is JobStatus.SUCCEEDED
    assert progress.status == "queued"


# -- feedback: LogView ------------------------------------------------------------------


def test_a_log_view_shows_ctx_log_records_as_they_arrive(rendering: Rendering) -> None:
    view = rendering.attach(LogView("log", limit=2))
    seen: list[object] = []
    view.changed(seen.append)

    rendering.ctx.log.info("started", layer="sites")
    rendering.ctx.log.warning("slow")
    rendering.ctx.log.error("failed", code=7)

    assert [record.level for record in view.records()] == ["warning", "error"]
    assert view.lines() == ("[warning] slow", "[error] failed code=7")
    assert len(seen) == 3
    assert view.snapshot()["lines"] == list(view.lines())
    if rendering.native:
        assert view.widget.toPlainText() == "[warning] slow\n[error] failed code=7"

    view.clear()
    assert view.records() == ()
    log = rendering.ctx.log
    rendering.scope.close()
    log.info("after close")
    assert view.records() == ()


def test_a_log_view_without_ctx_log_refuses_by_name(rendering: Rendering) -> None:
    from qgis_sdk.testing import fake_ui_context

    bare = fake_ui_context(rendering.scope, log=None)
    with pytest.raises(QgisSdkUiError, match="needs ctx.log"):
        LogView("log").attach(bare)
    with pytest.raises(QgisSdkUiError, match="limit"):
        LogView("log", limit=0)


# -- feedback: ResultTable --------------------------------------------------------------


def test_a_result_table_lists_rows_and_tracks_the_selection(
    rendering: Rendering,
) -> None:
    table = rendering.attach(ResultTable("results", ["name", ("count", "How many")]))
    seen: list[object] = []
    table.changed(seen.append)

    assert table.headings == ("Name", "How many")
    table.set_rows([{"name": "a", "count": 1}, {"name": "b", "count": 2.5, "x": 1}])
    assert table.cells() == (("a", "1"), ("b", "2.5"))
    assert table.selected() is None
    table.select(1)
    assert table.selected_row() == {"name": "b", "count": 2.5, "x": 1}
    assert seen == [None, 1]
    table.select(1)
    assert seen == [None, 1]
    with pytest.raises(QgisSdkUiError, match="cannot select 5"):
        table.select(5)
    if rendering.native:
        widget = table.widget
        assert widget.rowCount() == 2
        assert widget.item(1, 1).text() == "2.5"
        assert {index.row() for index in widget.selectionModel().selectedRows()} == {1}
        widget.selectRow(0)
        assert table.selected() == 0
        assert seen[-1] == 0

    table.set_rows([])
    assert table.selected() is None
    assert table.snapshot()["rows"] == []
    with pytest.raises(QgisSdkUiError, match="row 0 must be a mapping"):
        table.set_rows(["x"])  # type: ignore[list-item]
    with pytest.raises(QgisSdkUiError, match="unique"):
        ResultTable("t", ["a", "a"])
    with pytest.raises(QgisSdkUiError, match="at least one column"):
        ResultTable("t", [])


# -- buttons ----------------------------------------------------------------------------


def test_a_run_button_calls_the_action_with_the_form_s_values(
    rendering: Rendering,
) -> None:
    from qgis_sdk.ui import Form

    form = Form([Number("distance"), Text("note")])
    progress = JobProgress("job")
    run = RunButton("run", "buffer", values=form, text="Go")
    results: list[object] = []
    run.finished(results.append)
    rendering.attach(Column("root", [form, run, progress]))

    form.set_values({"distance": 2, "note": "hi"})
    run.click()
    assert run.last == "2.0:hi"
    assert results == ["2.0:hi"]
    assert rendering.plugin.calls == [("buffer", {"distance": 2.0, "note": "hi"})]
    assert run.snapshot()["action"] == "buffer"
    assert run.object_name == "buttons/run"
    if rendering.native:
        assert run.widget.text() == "Go"
        run.widget.click()
        assert len(results) == 2


def test_a_run_button_binds_a_job_handle_to_its_progress(rendering: Rendering) -> None:
    progress = JobProgress("job")
    run = RunButton(
        "run", "sum_slowly", values=lambda: {"a": 2, "b": 3}, progress=progress
    )
    rendering.attach(Row("root", [run, progress]))

    run.click()
    handle = run.last
    assert progress.handle is handle
    rendering.tick()
    assert handle.result == 5
    assert progress.status == "succeeded"


def test_a_run_button_s_refusal_is_a_warning_not_an_exception(
    rendering: Rendering,
) -> None:
    run = rendering.attach(RunButton("run", "buffer", values={"distance": "wide"}))

    assert run.run() is None
    assert run.last is None
    assert any(
        "distance" in message for message in rendering.ctx.notifications.messages
    )

    with pytest.raises(QgisSdkUiError, match="must be attached"):
        RunButton("loose", "buffer").run()
    with pytest.raises(QgisSdkUiError, match="action id"):
        RunButton("bad", "")


def test_accept_cancel_reports_each_press(rendering: Rendering) -> None:
    buttons = rendering.attach(AcceptCancel(accept_text="Run", cancel_text="Close"))
    presses: list[str] = []
    buttons.accepted(lambda: presses.append("accept"))
    unsubscribe = buttons.cancelled(lambda: presses.append("cancel"))

    buttons.accept()
    buttons.cancel()
    unsubscribe()
    buttons.cancel()
    assert presses == ["accept", "cancel"]
    assert buttons.object_name == "buttons/dialog_buttons"
    assert buttons.snapshot()["accept"] == "Run"
    if rendering.native:
        accept = buttons.widget.findChild(object, "buttons/dialog_buttons/accept")
        cancel = buttons.widget.findChild(object, "buttons/dialog_buttons/cancel")
        assert (accept.text(), cancel.text()) == ("Run", "Close")
        accept.click()
        cancel.click()
        assert presses == ["accept", "cancel", "accept"]

    rendering.scope.close()
    buttons.accept()
    assert len(presses) == (3 if rendering.native else 2)


def test_a_plain_button_still_presses(rendering: Rendering) -> None:
    button = rendering.attach(Button("go", "Go"))
    presses: list[int] = []
    button.clicked(lambda: presses.append(1))
    button.click()
    assert presses == [1]


# -- Custom -----------------------------------------------------------------------------


def test_custom_builds_its_widget_only_when_mounted(rendering: Rendering) -> None:
    built: list[object] = []

    def make(parent: object = None) -> object:
        from qgis.PyQt.QtWidgets import QLabel

        widget = QLabel("mine", parent)
        built.append(widget)
        return widget

    custom = Custom("mine", make)
    assert custom.factory is True
    assert custom.snapshot() == {
        "type": "Custom",
        "name": "mine",
        "label": "Mine",
        "objectName": "custom/mine",
        "widget": "make",
        "built": False,
    }
    rendering.attach(Column("root", [Text("note"), custom]))

    if rendering.native:
        assert len(built) == 1
        assert custom.widget is built[0]
        assert custom.widget.objectName() == "custom/mine"
        assert custom.snapshot()["widget"] == "QLabel"
    else:
        assert built == []
        with pytest.raises(QgisSdkUiError, match="not mounted"):
            _ = custom.widget

    with pytest.raises(QgisSdkUiError, match="needs a widget"):
        Custom("none", None)


# -- snapshots --------------------------------------------------------------------------


def test_a_snapshot_lists_the_semantic_tree_with_the_same_ids(
    rendering: Rendering,
) -> None:
    root = rendering.attach(
        Panel(
            "root",
            [
                Group("options", [Toggle("enabled")]),
                Tabs("pages", [Column("one", [Text("a")]), Column("two", [Text("b")])]),
                Row("actions", [RunButton("run", "buffer"), AcceptCancel()]),
                JobProgress("job"),
                LogView("log"),
                ResultTable("results", ["name"]),
            ],
        )
    )
    expected = (
        "root",
        "options",
        "form/enabled",
        "pages",
        "one",
        "form/a",
        "two",
        "form/b",
        "actions",
        "buttons/run",
        "buttons/dialog_buttons",
        "feedback/job",
        "feedback/log",
        "feedback/results",
    )
    semantic = ui_snapshot(root)
    assert snapshot_names(semantic) == expected
    assert semantic["type"] == "Panel"
    assert [child["type"] for child in semantic["children"]] == [
        "Group",
        "Tabs",
        "Row",
        "JobProgress",
        "LogView",
        "ResultTable",
    ]
    if rendering.native:
        native = ui_snapshot(root.widget)
        assert set(expected) <= set(snapshot_names(native))
        assert native["objectName"] == "root"
        assert native["type"] == "QWidget"


__all__ = [
    "test_a_container_refuses_two_children_with_one_name",
    "test_a_log_view_shows_ctx_log_records_as_they_arrive",
    "test_a_log_view_without_ctx_log_refuses_by_name",
    "test_a_plain_button_still_presses",
    "test_a_result_table_lists_rows_and_tracks_the_selection",
    "test_a_run_button_binds_a_job_handle_to_its_progress",
    "test_a_run_button_calls_the_action_with_the_form_s_values",
    "test_a_run_button_s_refusal_is_a_warning_not_an_exception",
    "test_a_snapshot_lists_the_semantic_tree_with_the_same_ids",
    "test_accept_cancel_reports_each_press",
    "test_custom_builds_its_widget_only_when_mounted",
    "test_every_container_attaches_its_children_and_finds_them_by_name",
    "test_job_progress_follows_a_handle_to_success",
    "test_job_progress_shows_a_failure_and_can_cancel",
    "test_job_progress_stops_listening_when_the_scope_closes",
    "test_tabs_show_one_page_at_a_time_and_report_switches",
]
