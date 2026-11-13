"""The records ``automation.pr`` passes around.

They live beside the tool rather than inside it because the tool is one module
with a 400-line limit and two halves - ``gh`` and ``git`` I/O, and the polling
loop - that both speak these types. Nothing here runs anything.

``automation.pr`` re-exports every name below, so ``pr.Snapshot`` and
``pr_records.Snapshot`` are the same class and patching either attribute is the
same object (decision-84: patch the module that defines what the caller reads).
"""

from __future__ import annotations

from dataclasses import dataclass

#: Conclusions that mean the check failed. A completed check with any other
#: conclusion is not a failure; one outside both sets is still pending.
FAILED_CONCLUSIONS = frozenset(
    {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STALE", "STARTUP_FAILURE"}
)
PASSED_CONCLUSIONS = frozenset({"SUCCESS", "SKIPPED", "NEUTRAL"})


class QgisSdkPrError(RuntimeError):
    """``gh`` failed, or answered with something this watcher cannot read."""


@dataclass(frozen=True)
class Check:
    """One check of a pull request, as ``statusCheckRollup`` reports it."""

    name: str
    status: str
    conclusion: str | None


@dataclass(frozen=True)
class Snapshot:
    """Every check of one pull request at one moment."""

    pr: int
    state: str
    checks: tuple[Check, ...]

    @property
    def failed(self) -> tuple[Check, ...]:
        return tuple(
            check
            for check in self.checks
            if check.status == "COMPLETED" and check.conclusion in FAILED_CONCLUSIONS
        )

    @property
    def pending(self) -> tuple[Check, ...]:
        return tuple(
            check
            for check in self.checks
            if check.status != "COMPLETED"
            or check.conclusion not in FAILED_CONCLUSIONS | PASSED_CONCLUSIONS
        )

    @property
    def passed(self) -> tuple[Check, ...]:
        return tuple(
            check
            for check in self.checks
            if check.status == "COMPLETED" and check.conclusion in PASSED_CONCLUSIONS
        )


@dataclass(frozen=True, slots=True)
class Branch:
    """The branch a pull request opens and the branch it lands on."""

    head: str
    base: str


@dataclass(frozen=True, slots=True)
class PullRequestRequest:
    """Everything ``open`` needs, so no function takes five loose strings."""

    branch: Branch
    title: str = ""
    body: str = ""
    draft: bool = False
    repo: str = ""
