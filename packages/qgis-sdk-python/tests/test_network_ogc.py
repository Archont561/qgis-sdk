"""A typed service client composed over the injected network, with no session of its own."""

from __future__ import annotations

from collections.abc import Coroutine

import pytest
from qgis_sdk.core import JobState, ResourceScope, StepScheduler
from qgis_sdk.models import QgisSdkHttpStatusError, QgisSdkServiceResponseError
from qgis_sdk.network import CollectionInfo, NetworkClient, OgcApiFeatures
from qgis_sdk.testing import FakeNetworkTransport, reply

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


def test_items_pages_carry_features_and_the_next_link(
    service: OgcApiFeatures, transport: FakeNetworkTransport
) -> None:
    first = f"{BASE}/collections/sites/items?limit=2&bbox=1%2C2%2C3%2C4"
    second = f"{BASE}/collections/sites/items?limit=2&offset=2"
    transport.expect(
        "GET",
        first,
        reply(
            json={
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "id": 1},
                    {"type": "Feature", "id": 2},
                ],
                "numberMatched": 3,
                "numberReturned": 2,
                "links": [
                    {"rel": "self", "href": first},
                    {"rel": "next", "href": second},
                ],
            }
        ),
    )
    transport.expect(
        "GET",
        second,
        reply(
            json={
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "id": 3}],
            }
        ),
    )

    async def both() -> tuple[object, object, object]:
        page = await service.items("sites", limit=2, bbox=(1, 2, 3, 4))
        last = await service.next_page(page)
        assert last is not None
        return page, last, await service.next_page(last)

    page, last, after_last = run(both())

    assert page.number_matched == 3
    assert page.number_returned == 2
    assert [feature["id"] for feature in page.features] == [1, 2]
    assert page.next_url == second
    assert last.number_returned == 1
    assert last.next_url is None
    assert after_last is None
    transport.assert_satisfied()


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
