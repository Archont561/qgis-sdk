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

import json
import os
import statistics
import sys
import threading
import time
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar


def _recommend_facts1(ceiling, follows_itself, limit, reasons):
    return Recommendation(
        max_redirects=limit,
        max_body_mib=ceiling,
        transport_follows_redirects_itself=follows_itself,
        reasons=tuple(reasons),
    )


SCRIPT_DIR = Path(__file__).resolve().parent

GUI_STALL_BUDGET_MS = 40.0


def _resident_kib() -> int:
    """Peak resident set in KiB; zero where the Unix ``resource`` module is absent.

    The probe only runs where QGIS is, but the QGIS-free tests import this module
    on Windows as well, so the import must not be a hard one.
    """
    try:
        import resource
    except ImportError:  # pragma: no cover - Windows
        return 0
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


"""The event-loop gap budget doc-6 held the scheduler to; the same bar applies here."""

BODY_SIZES_MIB = (1, 4, 8, 16, 32, 64, 128)
BODY_SAMPLES = 5
"""Per size; the median stall is reported, so one scheduler hiccup cannot decide."""
REDIRECT_CHAIN = 20
PROBE_REDIRECT_CEILING = 80
"""More hops than any client default surveyed (curl and Qt stop at 50)."""

BROWSER_REDIRECT_LIMIT = 20
"""What Chromium and Firefox allow; services in the wild are built against it."""

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


# --- loopback servers -------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    seen: ClassVar[list[tuple[int, str, dict[str, str]]]] = []
    partner_port = 0

    def log_message(self, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        _Handler.seen.append((self.server.server_port, self.path, dict(self.headers)))
        if self.path.startswith("/redirect/"):
            remaining = int(self.path.rsplit("/", 1)[1])
            if remaining > 0:
                self._redirect(f"/redirect/{remaining - 1}")
                return
        elif self.path == "/cross":
            self._redirect(f"http://127.0.0.1:{_Handler.partner_port}/final")
            return
        elif self.path.startswith("/bytes/"):
            self._bytes(int(self.path.rsplit("/", 1)[1]))
            return
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _bytes(self, size: int) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.end_headers()
        chunk = b"x" * (1 << 20)
        left = size
        while left > 0:
            piece = chunk[: min(left, len(chunk))]
            self.wfile.write(piece)
            left -= len(piece)


def _serve() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


# --- the run ------------------------------------------------------------------------


def _headless_environment(prefix: Path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("PROJ_LIB", str(prefix / "share" / "proj"))
    os.environ.setdefault("QGIS_PREFIX_PATH", str(prefix))
    bindings = str(prefix / "share" / "qgis" / "python")
    if bindings not in sys.path:
        sys.path.insert(0, bindings)


@dataclass(frozen=True, slots=True)
class _Fetcher:
    """One QGIS network manager with the Qt classes its requests need."""

    manager: object
    request_cls: object
    url_cls: object
    loop_cls: object

    def _request(self, url: str, headers: dict[str, str] | None, manual: bool):
        request = self.request_cls(self.url_cls(url))
        for name, value in (headers or {}).items():
            request.setRawHeader(name.encode(), value.encode())
        if manual:
            request.setAttribute(
                self.request_cls.Attribute.RedirectPolicyAttribute,
                self.request_cls.RedirectPolicy.ManualRedirectPolicy,
            )
        return request

    def fetch(self, url: str, headers: dict[str, str] | None = None, *, manual=False):
        request = self._request(url, headers, manual)
        loop = self.loop_cls()
        reply = self.manager.get(request)
        reply.finished.connect(loop.quit)
        transfer, payload, stall = _read_reply(reply, loop)
        location = reply.header(self.request_cls.KnownHeaders.LocationHeader)
        reply.deleteLater()
        return payload, transfer, stall, location


def _read_reply(reply, loop):
    """Wait for the reply, then time both the transfer and the Python copy."""
    started = time.perf_counter()
    loop.exec()
    transfer = time.perf_counter() - started
    stall_started = time.perf_counter()
    payload = bytes(reply.readAll())
    stall = time.perf_counter() - stall_started
    return transfer, payload, stall


@dataclass(frozen=True, slots=True)
class _ProbeRig:
    """Everything one measurement run owns: Qt bindings, origins and versions."""

    fetcher: _Fetcher
    application: object
    origin_a: ThreadingHTTPServer
    origin_b: ThreadingHTTPServer
    base: str
    platform: object
    qgis_version: object
    qt_version: str


@dataclass(frozen=True, slots=True)
class _Bindings:
    """The Qt and QGIS classes a probe needs, imported only where QGIS exists."""

    qt_version: str
    loop_cls: object
    url_cls: object
    request_cls: object
    qgis_cls: object
    application_cls: object
    manager_cls: object


def _qt_bindings() -> _Bindings:
    from PyQt6.QtCore import QT_VERSION_STR, QEventLoop, QUrl
    from PyQt6.QtNetwork import QNetworkRequest
    from qgis.core import Qgis, QgsApplication, QgsNetworkAccessManager

    return _Bindings(
        qt_version=QT_VERSION_STR,
        loop_cls=QEventLoop,
        url_cls=QUrl,
        request_cls=QNetworkRequest,
        qgis_cls=Qgis,
        application_cls=QgsApplication,
        manager_cls=QgsNetworkAccessManager,
    )


def _start_probe(prefix: Path) -> _ProbeRig:
    import platform

    bindings = _qt_bindings()
    bindings.application_cls.setPrefixPath(str(prefix), True)
    application = bindings.application_cls([b"qgis-sdk-network-limits-probe"], True)
    application.initQgis()
    origin_a = _serve()
    origin_b = _serve()
    _Handler.partner_port = origin_b.server_port
    return _ProbeRig(
        fetcher=_Fetcher(
            bindings.manager_cls.instance(),
            bindings.request_cls,
            bindings.url_cls,
            bindings.loop_cls,
        ),
        application=application,
        origin_a=origin_a,
        origin_b=origin_b,
        base=f"http://127.0.0.1:{origin_a.server_port}",
        platform=platform,
        qgis_version=bindings.qgis_cls.version,
        qt_version=bindings.qt_version,
    )


def _unaided_and_forwarded(rig: _ProbeRig) -> tuple[int, tuple[str, ...]]:
    """How many hops the manager follows alone, and what it sends cross-origin."""
    _Handler.seen.clear()
    rig.fetcher.fetch(f"{rig.base}/redirect/{PROBE_REDIRECT_CEILING}")
    unaided = len(_Handler.seen) - 1
    _Handler.seen.clear()
    sent = {name: "probe" for name in _CREDENTIAL_HEADERS}
    rig.fetcher.fetch(f"{rig.base}/cross", headers=sent)
    final_hop = next(
        h for p, _path, h in _Handler.seen if p == rig.origin_b.server_port
    )
    forwarded = tuple(
        name
        for name in _CREDENTIAL_HEADERS
        if any(key.lower() == name.lower() for key in final_hop)
    )
    return unaided, forwarded


def _manual_hop_ms(rig: _ProbeRig) -> float:
    """The mean cost of one redirect the SDK follows itself."""
    started = time.perf_counter()
    url = f"{rig.base}/redirect/{REDIRECT_CHAIN}"
    hops = 0
    while True:
        _payload, _transfer, _stall, location = rig.fetcher.fetch(url, manual=True)
        if location is None:
            break
        resolved = rig.fetcher.url_cls(url).resolved(rig.fetcher.url_cls(location))
        url = resolved.toString()
        hops += 1
    return (time.perf_counter() - started) * 1000 / max(hops, 1)


def _measure_redirects(rig: _ProbeRig) -> RedirectFindings:
    unaided, forwarded = _unaided_and_forwarded(rig)
    hop_ms = _manual_hop_ms(rig)
    return RedirectFindings(
        policy=rig.fetcher.manager.redirectPolicy().name,
        unaided_hops_followed=unaided,
        headers_forwarded_cross_origin=forwarded,
        manual_hop_mean_ms=round(hop_ms, 3),
    )


def _measure_body(rig: _ProbeRig, size_mib: int) -> BodyFinding:
    stalls: list[float] = []
    transfers: list[float] = []
    before = _resident_kib()
    for _ in range(BODY_SAMPLES):
        payload, transfer, stall, _location = rig.fetcher.fetch(
            f"{rig.base}/bytes/{size_mib << 20}"
        )
        assert len(payload) == size_mib << 20
        del payload
        stalls.append(stall * 1000)
        transfers.append(transfer * 1000)
    after = _resident_kib()
    return BodyFinding(
        size_mib=size_mib,
        finish_stall_ms=round(statistics.median(stalls), 2),
        worst_stall_ms=round(max(stalls), 2),
        transfer_ms=round(statistics.median(transfers), 1),
        resident_delta_mib=round((after - before) / 1024, 1),
    )


def _measure_bodies(rig: _ProbeRig) -> tuple[BodyFinding, ...]:
    return tuple(_measure_body(rig, size_mib) for size_mib in BODY_SIZES_MIB)


def _report(
    rig: _ProbeRig, redirects: RedirectFindings, bodies: tuple[BodyFinding, ...]
) -> ProbeReport:
    return ProbeReport(
        platform=rig.platform.platform(),
        python_version=rig.platform.python_version(),
        qgis_version=rig.qgis_version(),
        qt_version=rig.qt_version,
        redirects=redirects,
        bodies=bodies,
        recommended=recommend(redirects, bodies),
    )


def _run(prefix: Path) -> ProbeReport:
    rig = _start_probe(prefix)
    try:
        redirects = _measure_redirects(rig)
        bodies = _measure_bodies(rig)
        return _report(rig, redirects, bodies)
    finally:
        rig.origin_a.shutdown()
        rig.origin_b.shutdown()
        rig.application.exitQgis()


def run_probe(prefix: Path | None = None) -> ProbeReport:
    """Start QGIS, measure, and report; a broken environment is a report too."""
    import platform

    prefix = prefix or Path(sys.prefix)
    _headless_environment(prefix)
    try:
        return _run(prefix)
    except Exception as error:  # noqa: BLE001 - report broken environments
        return ProbeReport(
            platform=platform.platform(),
            python_version=platform.python_version(),
            qgis_version=None,
            qt_version=None,
            redirects=None,
            bodies=(),
            recommended=None,
            error=f"{type(error).__name__}: {error}",
        )


def main() -> int:
    """Print the report as JSON; exit non-zero when nothing could be measured."""
    report = run_probe()
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    return 0 if report.error is None else 1


if __name__ == "__main__":
    sys.exit(main())
