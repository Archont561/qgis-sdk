"""Measure what the TASK-5 networking limits must be set from.

decision-4 leaves two numbers to measurement rather than to the decision record:
the redirect limit and the buffered body-size ceiling. This harness starts a real
headless QGIS application, serves bytes from loopback HTTP servers it owns, and
reports what the real ``QgsNetworkAccessManager`` does:

- its redirect policy and how many hops it follows unaided;
- whether ``Authorization`` and ``Cookie`` survive a redirect to another origin,
  which decides whether the SDK transport may let Qt follow redirects at all;
- the per-hop cost of a redirect that the SDK follows itself;
- how long the GUI thread stalls turning a finished reply of N MiB into Python
  bytes, and how much resident memory the buffered copy costs.

It prints a machine-readable report with a ``recommended`` block derived by the
pure :func:`recommend` rule, which the QGIS-free suite tests. Loopback numbers are
an upper bound on throughput and a lower bound on latency, not a field result;
the record of a run lives in the TASK-5 evidence document.

Run it from the repository root with the default Pixi environment::

    pixi run -e default python packages/qgis-sdk-python/scripts/network_limits_probe.py
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


def _recommend_facts1(ceiling, follows_itself, limit, reasons):
    return Recommendation(
        max_redirects=limit,
        max_body_mib=ceiling,
        transport_follows_redirects_itself=follows_itself,
        reasons=tuple(reasons),
    )


GUI_STALL_BUDGET_MS = 40.0


BODY_SIZES_MIB = (1, 4, 8, 16, 32, 64, 128)


BODY_SAMPLES = 5


REDIRECT_CHAIN = 20


PROBE_REDIRECT_CEILING = 80


BROWSER_REDIRECT_LIMIT = 20


_CREDENTIAL_HEADERS = ("Authorization", "Cookie")


@dataclass(frozen=True)
class RedirectFindings:
    """What the real manager does with redirects."""

    policy: str
    unaided_hops_followed: int
    headers_forwarded_cross_origin: tuple[str, ...]
    manual_hop_mean_ms: float


@dataclass(frozen=True)
class BodyFinding:
    """Cost of buffering one response of ``size_mib`` MiB on the GUI thread.

    ``finish_stall_ms`` is the median over the samples of turning the finished
    reply into Python bytes; ``worst_stall_ms`` is the slowest sample.
    """

    size_mib: int
    finish_stall_ms: float
    worst_stall_ms: float
    transfer_ms: float
    resident_delta_mib: float


@dataclass(frozen=True)
class Recommendation:
    """The two limits the measurements support, with the rule that picked them."""

    max_redirects: int
    max_body_mib: int
    transport_follows_redirects_itself: bool
    reasons: tuple[str, ...]


def _body_ceiling(
    bodies: tuple[BodyFinding, ...], stall_budget_ms: float, reasons: list[str]
) -> int:
    """The largest measured body whose finish stall fits the GUI budget."""
    within = [body for body in bodies if body.finish_stall_ms <= stall_budget_ms]
    if within:
        ceiling = max(body.size_mib for body in within)
        reasons.append(
            f"largest measured body whose finish stall is within {stall_budget_ms:g} ms"
            f" is {ceiling} MiB"
        )
    else:
        ceiling = min(body.size_mib for body in bodies) if bodies else 1
        reasons.append("no measured body stayed inside the stall budget")
    return ceiling


def _redirect_limit(
    redirects: RedirectFindings, stall_budget_ms: float, reasons: list[str]
) -> int:
    """Browser limit if the measured hops fit the budget, budget over cost if not."""
    hop_ms = redirects.manual_hop_mean_ms
    if hop_ms <= 0 or hop_ms * BROWSER_REDIRECT_LIMIT <= stall_budget_ms:
        limit = BROWSER_REDIRECT_LIMIT
        reasons.append(
            f"{BROWSER_REDIRECT_LIMIT} hops at {hop_ms:.2f} ms each stay within"
            f" {stall_budget_ms:g} ms, so the browser limit applies"
        )
    else:
        limit = max(1, int(stall_budget_ms // hop_ms))
        reasons.append(
            f"{hop_ms:.2f} ms per hop allows {limit} hops within {stall_budget_ms:g} ms"
        )
    return limit


def _forwarding_reason(redirects: RedirectFindings, reasons: list[str]) -> bool:
    """Whether the transport must follow redirects itself, and why."""
    follows_itself = bool(redirects.headers_forwarded_cross_origin)
    if follows_itself:
        listed = ", ".join(redirects.headers_forwarded_cross_origin)
        reasons.append(
            f"the manager forwards {listed} to another origin, so the transport"
            " follows redirects itself and drops credentials on an origin change"
        )
    else:
        reasons.append("the manager drops credentials on an origin change")
    return follows_itself


def recommend(
    redirects: RedirectFindings,
    bodies: tuple[BodyFinding, ...],
    *,
    stall_budget_ms: float = GUI_STALL_BUDGET_MS,
) -> Recommendation:
    """Turn measurements into limits by a rule a reader can check.

    The body ceiling is the largest measured size whose finish stall stays inside
    the GUI budget: a buffered response is handed to Python in one go on the GUI
    thread, so the stall is what a user feels. The redirect limit is the browser
    limit when the measured per-hop cost keeps that many hops inside the same
    budget; otherwise the budget divided by the hop cost. Credential forwarding
    across origins means the transport must follow redirects itself.
    """
    reasons: list[str] = []
    ceiling = _body_ceiling(bodies, stall_budget_ms, reasons)
    limit = _redirect_limit(redirects, stall_budget_ms, reasons)
    follows_itself = _forwarding_reason(redirects, reasons)
    return _recommend_facts1(ceiling, follows_itself, limit, reasons)


@dataclass(frozen=True)
class ProbeReport:
    """Everything one run observed, serialisable as JSON."""

    platform: str
    python_version: str
    qgis_version: str | None
    qt_version: str | None
    redirects: RedirectFindings | None
    bodies: tuple[BodyFinding, ...]
    recommended: Recommendation | None
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Return the report as plain data."""
        return asdict(self)
