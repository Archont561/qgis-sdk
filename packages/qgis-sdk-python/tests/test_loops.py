"""``LoopRegistry``: the named loops a host starts, and what stopping them reports.

decision-69 point 4 says every loop the SDK starts on a host's behalf carries a
name and is enumerated when the host stops, instead of being assumed stopped.
This is that bookkeeping on its own, without Qt or a host: a loop is anything
with a name, a ``running`` flag and ``stop()``.
"""

from __future__ import annotations

import pytest
from qgis_sdk.core import LoopRegistry, LoopState, NamedLoop
from qgis_sdk.testing import FakeLoop


def test_a_loop_is_anything_with_a_name_running_and_stop() -> None:
    assert isinstance(FakeLoop(), NamedLoop)


def test_loops_are_kept_in_start_order_and_report_their_own_state() -> None:
    pump = FakeLoop(name="job-pump")
    watcher = FakeLoop(name="reload-watcher")
    registry = LoopRegistry()
    for loop in (pump, watcher):
        registry.run(loop)

    assert registry.inventory() == (
        LoopState("job-pump", True),
        LoopState("reload-watcher", True),
    )

    pump.stop()

    assert registry.inventory()[0] == LoopState("job-pump", False)


def test_two_loops_cannot_share_a_name() -> None:
    """The report names loops, so a duplicate would name the wrong one."""
    registry = LoopRegistry([FakeLoop(name="job-pump")])

    with pytest.raises(ValueError, match="'job-pump' is already registered"):
        registry.add(FakeLoop(name="job-pump"))


def test_a_loop_can_be_looked_up_by_the_name_it_reports() -> None:
    pump = FakeLoop(name="job-pump")
    registry = LoopRegistry([pump])

    assert registry.get("job-pump") is pump
    assert registry.get("nothing") is None
    assert len(registry) == 1


def test_run_starts_the_loop_it_records() -> None:
    loop = FakeLoop(name="host-timer")

    registry = LoopRegistry()
    registry.run(loop)

    assert loop.running is True
    assert registry.inventory() == (LoopState("host-timer", True),)


def test_run_records_a_loop_that_has_no_start_of_its_own() -> None:
    """A loop already running when the host adopted it needs no ``start``."""

    class Adopted:
        name = "adopted"
        running = True
        stopped = 0

        def stop(self) -> None:
            self.stopped += 1

    loop = Adopted()

    assert LoopRegistry().run(loop) is loop  # type: ignore[arg-type]


def test_stopping_reports_every_loop_last_started_first() -> None:
    first = FakeLoop(name="first")
    second = FakeLoop(name="second")
    registry = LoopRegistry([first, second])

    states = registry.stop_all()

    assert [state.name for state in states] == ["second", "first"]
    assert [state.running for state in states] == [False, False]
    assert (first.stops, second.stops) == (1, 1)


def test_a_loop_that_refuses_to_disarm_is_reported_as_still_running() -> None:
    class Stubborn(FakeLoop):
        def stop(self) -> None:
            self.stops += 1  # asked, but it stays armed

    registry = LoopRegistry()
    stubborn = registry.run(Stubborn(name="stubborn"))

    states = registry.stop_all()

    assert stubborn.stops == 1  # asked
    assert states == (LoopState("stubborn", True),)  # and still armed


def test_a_loop_that_raises_does_not_strand_the_others() -> None:
    class Exploding(FakeLoop):
        def stop(self) -> None:
            raise RuntimeError("the timer is gone")

    stubborn = FakeLoop(name="stubborn")
    exploding = Exploding(name="exploding")
    registry = LoopRegistry([stubborn, exploding])

    with pytest.raises(RuntimeError, match="exploding \\(the timer is gone\\)"):
        registry.stop_all()

    assert stubborn.stops == 1  # the loop after the failure was still asked


def test_a_state_renders_for_a_log_line() -> None:
    assert str(LoopState("job-pump", True)) == "job-pump (running)"
    assert str(LoopState("job-pump", False)) == "job-pump (stopped)"


def test_the_registry_renders_what_it_holds() -> None:
    registry = LoopRegistry([FakeLoop(name="a"), FakeLoop(name="b")])

    assert repr(registry) == "LoopRegistry(a, b)"
    assert repr(LoopRegistry()) == "LoopRegistry()"
