"""Author-facing ownership scenarios against the public ResourceScope API."""

from dataclasses import dataclass

import pytest
from pytest_bdd import given, scenarios, then, when
from qgis_sdk.core import ResourceScope
from qgis_sdk.models import QgisSdkScopeClosedError

scenarios("features/scope_lifecycle.feature")


@dataclass
class ScopedWork:
    plugin: ResourceScope
    first_view: ResourceScope
    sibling_view: ResourceScope
    job: ResourceScope
    released: list[str]


@given("a plugin with two views and a job in the first view", target_fixture="work")
def plugin_with_views() -> ScopedWork:
    released: list[str] = []
    plugin = ResourceScope()
    plugin.on_close(lambda: released.append("plugin"))
    first_view = plugin.child()
    first_view.on_close(lambda: released.append("first view"))
    sibling_view = plugin.child()
    sibling_view.on_close(lambda: released.append("sibling view"))
    job = first_view.child()
    job.on_close(lambda: released.append("job"))
    return ScopedWork(plugin, first_view, sibling_view, job, released)


@when("the first view closes")
def close_first_view(work: ScopedWork) -> None:
    work.first_view.close()


@then("only the first view and its job are released")
def only_first_view_released(work: ScopedWork) -> None:
    assert work.released == ["job", "first view"]
    assert work.first_view.closed and work.job.closed


@then("the sibling view and plugin still accept work")
def other_owners_remain_open(work: ScopedWork) -> None:
    assert not work.sibling_view.closed and not work.plugin.closed
    work.sibling_view.on_close(lambda: work.released.append("late sibling cleanup"))
    work.plugin.on_close(lambda: work.released.append("late plugin cleanup"))


@when("the plugin closes twice")
def close_plugin_twice(work: ScopedWork) -> None:
    work.plugin.close()
    work.plugin.close()


@then("each cleanup runs once from descendants to plugin")
def cleanup_order(work: ScopedWork) -> None:
    assert work.released == ["sibling view", "job", "first view", "plugin"]
    assert all(
        scope.closed
        for scope in (work.plugin, work.first_view, work.sibling_view, work.job)
    )


@then("the closed plugin rejects new work")
def closed_plugin_rejects_work(work: ScopedWork) -> None:
    with pytest.raises(QgisSdkScopeClosedError):
        work.plugin.child()
