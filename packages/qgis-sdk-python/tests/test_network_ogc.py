"""A typed service client composed over the injected network, with no session of its own."""

from __future__ import annotations

import copy
from collections.abc import Coroutine

import pytest
from qgis_sdk.core import JobState, ResourceScope, StepScheduler
from qgis_sdk.models import QgisSdkHttpStatusError, QgisSdkServiceResponseError
from qgis_sdk.network import CollectionInfo, NetworkClient, OgcApiFeatures
from qgis_sdk.testing import FakeNetworkTransport, reply


class _CcState:
    """A mutable record shared by the phases of one long function."""

    def __init__(_cc_self, **values):
        _cc_self.__dict__.update(values)


class _CcReturn:
    """An early return travelling out of a phase."""

    def __init__(_cc_self, value):
        _cc_self.value = value


class _CcBreak:
    """A loop break travelling out of a phase."""


class _CcContinue:
    """A loop continue travelling out of a phase."""


def _cc_test_items_pages_p1(_s):
    _s.first = f"{BASE}/collections/sites/items?limit=2&bbox=1%2C2%2C3%2C4"
    _s.second = f"{BASE}/collections/sites/items?limit=2&offset=2"


def _cc_test_items_pages_p2(_s):
    _s.transport.expect(
        "GET",
        _s.first,
        reply(
            json={
                "type": "FeatureCollection",
                "features": _cc_fresh_1(),
                "numberMatched": 3,
                "numberReturned": 2,
                "links": [
                    {"rel": "self", "href": _s.first},
                    {"rel": "next", "href": _s.second},
                ],
            }
        ),
    )


def _cc_test_items_pages_p3(_s):
    _s.transport.expect(
        "GET",
        _s.second,
        reply(json=_cc_fresh_2()),
    )

    async def both() -> tuple[object, object, object]:
        page = await _s.service.items("sites", limit=2, bbox=(1, 2, 3, 4))
        last = await _s.service.next_page(page)
        assert last is not None
        return page, last, await _s.service.next_page(last)

    _s.both = both


def _cc_test_items_pages_p4(_s):

    _s.page, _s.last, _s.after_last = run(_s.both())

    assert _s.page.number_matched == 3
    assert _s.page.number_returned == 2
    _items_pages_carry_features_phase1(
        _s.after_last, _s.last, _s.page, _s.second, _s.transport
    )


_CC_DATA_1 = [
    {"type": "Feature", "id": 1},
    {"type": "Feature", "id": 2},
]


def _cc_fresh_1():
    """Return a fresh copy of the shared data literal."""
    return copy.deepcopy(_CC_DATA_1)


_CC_DATA_2 = {
    "type": "FeatureCollection",
    "features": [{"type": "Feature", "id": 3}],
}


def _cc_fresh_2():
    """Return a fresh copy of the shared data literal."""
    return copy.deepcopy(_CC_DATA_2)


def _collections_are_typed_values_facts1(collections, transport):
    assert collections == (
        CollectionInfo(
            id="sites",
            title="Sites",
            description="Monitoring sites",
            crs=("http://www.opengis.net/def/crs/OGC/1.3/CRS84",),
        ),
        CollectionInfo(id="roads", title=None, description=None, crs=()),
    )
    assert transport.requests[0].headers["accept"] == "application/json"
    transport.assert_satisfied()


def _items_pages_carry_features_phase1(after_last, last, page, second, transport):
    assert [feature["id"] for feature in page.features] == [1, 2]
    assert page.next_url == second
    assert last.number_returned == 1
    assert last.next_url is None
    assert after_last is None
    transport.assert_satisfied()


BASE = "https://features.example.test/ogc"


def run(coro: Coroutine[object, None, object]) -> object:
    scheduler = StepScheduler(ResourceScope())
    job = scheduler.submit(coro)
    scheduler.drain(max_ticks=100)
    if job.error is not None:
        raise job.error
    assert job.state is JobState.COMPLETED
    return job.result


@pytest.fixture
def transport() -> FakeNetworkTransport:
    return FakeNetworkTransport()


@pytest.fixture
def service(transport: FakeNetworkTransport) -> OgcApiFeatures:
    return OgcApiFeatures(NetworkClient(transport, ResourceScope()), BASE)


def test_collections_are_typed_values_fetched_through_the_shared_client(
    service: OgcApiFeatures, transport: FakeNetworkTransport
) -> None:
    transport.expect(
        "GET",
        f"{BASE}/collections",
        reply(
            json={
                "collections": [
                    {
                        "id": "sites",
                        "title": "Sites",
                        "description": "Monitoring sites",
                        "crs": ["http://www.opengis.net/def/crs/OGC/1.3/CRS84", 7],
                    },
                    {"id": "roads"},
                ]
            }
        ),
    )

    collections = run(service.collections())

    _collections_are_typed_values_facts1(collections, transport)


def test_items_pages_carry_features_and_the_next_link(
    service: OgcApiFeatures, transport: FakeNetworkTransport
) -> None:
    _s = _CcState(service=service, transport=transport)
    for _p in (
        _cc_test_items_pages_p1,
        _cc_test_items_pages_p2,
        _cc_test_items_pages_p3,
        _cc_test_items_pages_p4,
    ):
        _r = _p(_s)
        if isinstance(_r, _CcReturn):
            return _r.value
    return None


def test_an_http_failure_surfaces_as_the_status_error(
    service: OgcApiFeatures, transport: FakeNetworkTransport
) -> None:
    transport.expect("GET", f"{BASE}/collections", reply(503))

    with pytest.raises(QgisSdkHttpStatusError) as caught:
        run(service.collections())
    assert caught.value.status_code == 503


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "expected a JSON object"),
        ({"collections": "nope"}, "no 'collections' array"),
        ({"collections": [{"title": "no id"}]}, "collection 0 has no string 'id'"),
    ],
)
def test_a_reply_that_is_not_the_service_shape_is_a_service_response_error(
    service: OgcApiFeatures,
    transport: FakeNetworkTransport,
    payload: object,
    message: str,
) -> None:
    transport.expect("GET", f"{BASE}/collections", reply(json=payload))

    with pytest.raises(QgisSdkServiceResponseError, match=message) as caught:
        run(service.collections())
    assert caught.value.code == "service_response_invalid"


def test_an_items_reply_that_is_not_a_feature_collection_is_refused(
    service: OgcApiFeatures, transport: FakeNetworkTransport
) -> None:
    transport.expect(
        "GET", f"{BASE}/collections/x/items?limit=10", reply(json={"type": "Feature"})
    )

    with pytest.raises(QgisSdkServiceResponseError, match="FeatureCollection"):
        run(service.items("x"))
