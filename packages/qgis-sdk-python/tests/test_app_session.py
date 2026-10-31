"""``qgis_sdk.app.run``: the standalone app host's lifecycle, without Qt.

Decision-52 point 3 makes a standalone PyQGIS application the third host one
plugin class runs on, and decision-69 points 2 and 4 bound what stopping one may
do: wait ``grace`` seconds for running jobs, name every loop it stops and every
job it abandons, and call ``exitQgis`` exactly once. Every claim here is proven
against ``qgis_sdk.testing.FakeAppBackend`` - no ``QgsApplication``, no display,
no event loop - which is why this file runs everywhere. The window, the map
canvas and the real bindings are ``test_app_native.py``'s business on a row that
has QGIS.
"""

from __future__ import annotations

import pytest
from qgis_sdk import QgisSdkPlugin
from qgis_sdk import app as app_module
from qgis_sdk.app import AppSession, QgisSdkAppError, parse_argv, run
from qgis_sdk.core import Host, PluginContext, WorkerContext
from qgis_sdk.jobs import JobStatus, job
from qgis_sdk.models import QgisSdkUnsupportedCapabilityError
from qgis_sdk.testing import FakeAppBackend, FakeLoop, FakeWorkers
from qgis_sdk.ui import Dialog

# -- the plugin every test runs ----------------------------------------------------


@job(id="demo.slow", title="Slow work")
def slow(ctx: WorkerContext, value: int) -> int:
    """A job that finishes only when the test lets the worker run."""
    return value


class Details(Dialog):
    """A surface: only a GUI host can open one."""

    def build(self):  # pragma: no cover - never built without a window
        return None


def make_app(**declared: object) -> QgisSdkPlugin:
    app = QgisSdkPlugin(id="demo_app", title="Demo app")

    @app.action(id="ping", title="Ping")
    def ping(ctx: PluginContext, value: int) -> int:
        return value

    app.jobs = {"slow": slow}
    for name, value in declared.items():
        setattr(app, name, value)
    return app


def start(
    backend: FakeAppBackend, *, gui: bool = False, **options: object
) -> AppSession:
    session = AppSession(
        make_app(),
        backend=backend,
        gui=gui,
        grace=options.pop("grace", 0.5),
        **options,  # type: ignore[arg-type]
    )
    session.start()
    return session


# -- what the host offers -----------------------------------------------------------


def test_a_headless_app_reports_the_app_host_and_runs_the_plugin() -> None:
    backend = FakeAppBackend()

    session = start(backend)

    assert session.context is not None
    assert session.context.host is Host.APP
    assert session.runtime is not None
    assert session.runtime.actions["ping"](value=3) == 3
    assert session.runtime.state.value == "running"
    session.stop()


def test_a_headless_app_refuses_the_desktop_and_the_ui_by_name() -> None:
    session = start(FakeAppBackend())

    context = session.context
    assert context is not None
    with pytest.raises(QgisSdkUnsupportedCapabilityError, match="desktop"):
        _ = context.desktop
    with pytest.raises(QgisSdkUnsupportedCapabilityError, match="'ui'"):
        _ = context.ui

    session.stop()


def test_a_gui_app_offers_a_ui_and_the_surface_is_told_to_show_it() -> None:
    backend = FakeAppBackend()

    session = start(backend, gui=True)

    assert session.context is not None
    assert session.context.has("ui")
    assert backend.surface.binds == 1
    assert backend.surface.runtime is session.runtime
    session.stop()


def test_a_context_that_reports_another_host_is_refused() -> None:
    """``ctx.host`` is stated by the host, so a host that states the wrong one is wrong."""
    backend = FakeAppBackend(host=Host.DESKTOP)

    with pytest.raises(QgisSdkAppError, match="reported 'desktop'"):
        start(backend)

    # The refusal still tore the application down: nothing is left initialised.
    assert backend.exits == 1


# -- starting ----------------------------------------------------------------------


def test_start_builds_the_context_before_it_starts_the_plugin() -> None:
    backend = FakeAppBackend()

    session = start(backend)
    session.stop()

    assert backend.calls[:2] == ["init", "build"]
    assert backend.argv == ()


def test_a_build_that_raises_still_exits_the_toolkit_once() -> None:
    backend = FakeAppBackend(build_error=RuntimeError("no window for you"))

    with pytest.raises(RuntimeError, match="no window for you"):
        start(backend)

    assert backend.calls == ["init", "build", "exit"]
    assert backend.exits == 1


def test_an_init_that_raises_does_not_exit_what_never_started() -> None:
    """``initQgis`` failed, so there is no application to tear down."""
    backend = FakeAppBackend(init_error=RuntimeError("no QGIS"))

    with pytest.raises(RuntimeError, match="no QGIS"):
        start(backend)

    assert backend.calls == ["init"]
    assert backend.exits == 0


def test_a_session_starts_once() -> None:
    session = start(FakeAppBackend())

    with pytest.raises(QgisSdkAppError, match="already started"):
        session.start()

    session.stop()


# -- running -----------------------------------------------------------------------


def test_run_returns_the_applications_exit_code_and_stops_in_order() -> None:
    backend = FakeAppBackend(exec_code=3)

    code = run(make_app(), backend=backend, grace=0.5)

    assert code == 3
    assert backend.calls == ["init", "build", "exec", "exit"]


def test_run_once_delivers_what_is_queued_instead_of_waiting() -> None:
    """``qgis-sdk run --once``: the smoke run a script can make in CI."""
    backend = FakeAppBackend()

    code = run(make_app(), backend=backend, once=True, grace=0.5)

    assert code == 0
    assert backend.calls == ["init", "build", "process_events", "exit"]


def test_quit_reaches_the_backend_of_the_running_app() -> None:
    recorded: list[str] = []

    class Quitting(FakeAppBackend):
        def exec(self) -> int:
            recorded.append("exec")
            self.calls.append("exec")
            app_module.quit()
            return 0

    backend = Quitting()
    code = run(make_app(), backend=backend)

    assert code == 0
    assert backend.calls == ["init", "build", "exec", "quit", "exit"]


def test_quit_refuses_by_name_when_no_app_is_running() -> None:
    with pytest.raises(QgisSdkAppError, match="no application host is running"):
        app_module.quit()


def test_a_second_app_in_one_process_is_refused() -> None:
    class Nested(FakeAppBackend):
        def exec(self) -> int:
            with pytest.raises(QgisSdkAppError, match="still running"):
                app_module.run(make_app(), backend=FakeAppBackend())
            return 0

    assert run(make_app(), backend=Nested()) == 0


# -- stopping: loops, jobs, exitQgis -----------------------------------------------


def test_shutdown_names_every_loop_it_stopped() -> None:
    pump = FakeLoop(name="job-pump")
    watcher = FakeLoop(name="reload-watcher")
    said: list[str] = []
    backend = FakeAppBackend(loops=(pump, watcher))

    session = start(backend, say=said.append)
    report = session.stop()

    assert report.stopped == ("job-pump", "reload-watcher")
    assert [state.running for state in report.loops] == [False, False]
    assert pump.stops == 1 and watcher.stops == 1
    assert "app: stopping 2 background loops: job-pump, reload-watcher" in said
    assert "no background loops were running" not in said


def test_a_host_that_started_no_loop_says_so_instead_of_nothing() -> None:
    said: list[str] = []
    backend = FakeAppBackend(loops=())

    session = start(backend, say=said.append)
    report = session.stop()

    assert report.stopped == ()
    assert "app: no background loops were running" in said


def test_a_job_that_finishes_inside_the_grace_window_is_drained_not_abandoned() -> None:
    backend = FakeAppBackend()
    session = start(backend, grace=5.0)
    service = session.runtime.jobs
    handle = service.slow.delay(value=1)

    def finish_while_waiting(_seconds: float) -> None:
        backend.workers.run_all()

    session._pause = finish_while_waiting  # type: ignore[attr-defined]
    report = session.stop()

    assert report.drained == (handle.id,)
    assert report.abandoned == ()
    assert handle.status is JobStatus.SUCCEEDED


def test_a_job_still_running_at_the_deadline_is_named_and_settled_cancelled() -> None:
    clock = {"now": 0.0}
    said: list[str] = []
    backend = FakeAppBackend()
    session = AppSession(
        make_app(),
        backend=backend,
        grace=2.0,
        say=said.append,
        clock=lambda: clock["now"],
        pause=lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
    )
    session.start()
    handle = session.runtime.jobs.slow.delay(value=1)

    report = session.stop()

    assert report.abandoned == (handle.id,)
    assert report.drained == ()
    assert handle.cancel_requested is True
    assert handle.status is JobStatus.CANCELLED
    assert report.elapsed >= 2.0
    assert any(f"abandoning job {handle.id} after 2s" in line for line in said)


def test_a_plugin_with_no_jobs_spends_no_time_waiting() -> None:
    app = QgisSdkPlugin(id="demo_app", title="Demo app")
    backend = FakeAppBackend()
    session = AppSession(app, backend=backend, grace=30.0)
    session.start()

    report = session.stop()

    assert (report.drained, report.abandoned) == ((), ())
    assert report.elapsed < 1.0


def test_stopping_twice_reports_once_and_exits_once() -> None:
    backend = FakeAppBackend()
    session = start(backend)

    first = session.stop()
    second = session.stop()

    assert first is second
    assert backend.exits == 1
    assert backend.calls.count("exit") == 1


def test_the_stop_order_is_loops_then_ui_then_runtime_then_the_toolkit() -> None:
    order: list[str] = []
    pump = FakeLoop(name="job-pump")
    pump.stop = lambda: order.append("loop")  # type: ignore[method-assign]
    backend = FakeAppBackend(loops=(pump,), surface_closer=lambda: order.append("ui"))

    session = start(backend)
    runtime = session.runtime
    assert runtime is not None
    runtime.unload = lambda: order.append("runtime")  # type: ignore[method-assign]
    backend.exit = lambda: order.append("exit")  # type: ignore[method-assign]

    report = session.stop()

    assert order == ["loop", "ui", "runtime", "exit"]
    assert report.exited is True


def test_the_report_describes_itself_for_a_terminal_and_for_json() -> None:
    backend = FakeAppBackend()
    session = start(backend)

    report = session.stop()

    assert report.summary().startswith("stopped 1 loop: job-pump")
    assert report.to_json()["exited"] is True
    assert report.to_json()["stopped_loops"] == ["job-pump"]
    assert report.to_json()["loops"] == [{"name": "job-pump", "running": False}]


def test_the_grace_period_must_not_be_negative() -> None:
    with pytest.raises(QgisSdkAppError, match="grace"):
        AppSession(make_app(), backend=FakeAppBackend(), grace=-1.0)


def test_a_runtime_that_is_not_a_plugin_is_refused() -> None:
    from qgis_sdk.declarations import QgisSdkDeclarationError

    with pytest.raises(QgisSdkDeclarationError):
        AppSession(object(), backend=FakeAppBackend())  # type: ignore[arg-type]


def test_the_session_reports_its_own_state() -> None:
    backend = FakeAppBackend()
    session = AppSession(make_app(), backend=backend)

    assert repr(session) == "AppSession('demo_app', new)"
    session.start()
    assert repr(session) == "AppSession('demo_app', running)"
    session.stop()
    assert repr(session) == "AppSession('demo_app', stopped)"


def test_a_worker_pool_is_what_runs_a_job() -> None:
    """The context carries the workers the runtime needs; a fake one is enough."""
    backend = FakeAppBackend()
    session = start(backend)
    assert isinstance(backend.workers, FakeWorkers)

    handle = session.runtime.jobs.slow.delay(value=7)
    session.runtime.jobs.tick()
    backend.workers.run_all()
    session.runtime.jobs.tick()

    assert handle.status is JobStatus.SUCCEEDED
    assert handle.result == 7
    session.stop()


# -- the launcher entry ------------------------------------------------------------


def test_a_launcher_opens_a_window_unless_it_is_told_not_to() -> None:
    backend = FakeAppBackend()

    code = app_module.main(make_app(), ["--once"], backend=backend)

    assert code == 0
    assert backend.calls == ["init", "build", "process_events", "exit"]
    assert backend.surfaces[0].gui is True


def test_headless_is_a_flag_a_launcher_can_pass() -> None:
    backend = FakeAppBackend()

    app_module.main(make_app(), ["--headless", "--once"], backend=backend)

    assert backend.surfaces[0].gui is False


def test_the_toolkit_gets_what_follows_the_separator() -> None:
    backend = FakeAppBackend()

    app_module.main(
        make_app(),
        ["--headless", "--once", "--", "-platform", "offscreen"],
        backend=backend,
    )

    assert backend.argv == ("-platform", "offscreen")


def test_an_option_the_sdk_does_not_know_goes_to_the_toolkit() -> None:
    backend = FakeAppBackend()

    app_module.main(
        make_app(), ["--headless", "--once", "-style", "Fusion"], backend=backend
    )

    assert backend.argv == ("-style", "Fusion")


def test_a_launcher_can_set_the_grace_period_and_the_title() -> None:
    options = parse_argv(["--grace", "0.5", "--title", "Field tools"])

    assert (options.grace, options.title) == (0.5, "Field tools")
    assert parse_argv(["--grace=2", "--title=Other"]).grace == 2.0


def test_a_grace_period_that_is_not_a_number_is_refused_with_a_code(capsys) -> None:
    code = app_module.main(make_app(), ["--grace", "soon"], backend=FakeAppBackend())

    assert code == 2
    assert "--grace wants seconds" in capsys.readouterr().err


def test_a_launcher_reports_a_refusal_instead_of_a_traceback(capsys) -> None:
    """No PyQGIS, a second app, a bad flag: one line and exit code 2."""
    backend = FakeAppBackend(init_error=QgisSdkAppError("no PyQGIS here"))

    code = app_module.main(make_app(), ["--once"], backend=backend)

    assert code == 2
    assert "qgis-sdk app: no PyQGIS here" in capsys.readouterr().err


def test_a_missing_flag_value_is_refused_rather_than_guessed() -> None:
    with pytest.raises(QgisSdkAppError, match="needs a value"):
        parse_argv(["--title"])


def test_the_parsed_options_describe_themselves() -> None:
    options = parse_argv(["--headless", "--once"])

    assert options.to_json() == {
        "gui": False,
        "once": True,
        "grace": 15.0,
        "title": None,
        "argv": [],
    }
