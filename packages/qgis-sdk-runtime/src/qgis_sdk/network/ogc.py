"""A typed OGC API - Features client composed over ``ctx.network``.

This is the pattern decision-4 asks typed GIS-service clients to follow: no
session or manager of its own, just a derived :class:`Network` with the
service's base URL and ``Accept`` header, typed values parsed from JSON, and
``QgisSdkServiceResponseError`` when a well-formed reply is not the service's
shape. Loading a collection as a QGIS layer is still the ``OAPIF`` provider's
job; this client is for the REST operations around it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from qgis_sdk.models import QgisSdkServiceResponseError, Response
from qgis_sdk.services import Network

__all__ = ["CollectionInfo", "FeaturesPage", "OgcApiFeatures"]


@dataclass(frozen=True, slots=True)
class CollectionInfo:
    """One entry of ``/collections``."""

    id: str
    title: str | None
    description: str | None
    crs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FeaturesPage:
    """One page of ``/collections/{id}/items``: GeoJSON features and paging facts."""

    features: tuple[Mapping[str, object], ...]
    number_returned: int
    number_matched: int | None
    next_url: str | None


def _payload(response: Response) -> Mapping[str, object]:
    document = response.raise_for_status().json()
    if not isinstance(document, Mapping):
        raise QgisSdkServiceResponseError(
            "expected a JSON object", method=response.method, url=response.url
        )
    return document


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def parse_collections(response: Response) -> tuple[CollectionInfo, ...]:
    """Read ``/collections``; every entry must at least have a string ``id``."""
    document = _payload(response)
    entries = document.get("collections")
    if not isinstance(entries, Sequence) or isinstance(entries, str):
        raise QgisSdkServiceResponseError(
            "the collections document has no 'collections' array",
            method=response.method,
            url=response.url,
        )
    parsed: list[CollectionInfo] = []
    for index, entry in enumerate(entries):
        identifier = entry.get("id") if isinstance(entry, Mapping) else None
        if not isinstance(identifier, str):
            raise QgisSdkServiceResponseError(
                f"collection {index} has no string 'id'",
                method=response.method,
                url=response.url,
            )
        crs = entry.get("crs", ())
        parsed.append(
            CollectionInfo(
                id=identifier,
                title=_text(entry.get("title")),
                description=_text(entry.get("description")),
                crs=tuple(item for item in crs if isinstance(item, str))
                if isinstance(crs, Sequence) and not isinstance(crs, str)
                else (),
            )
        )
    return tuple(parsed)


def parse_features(response: Response) -> FeaturesPage:
    """Read an ``items`` page: a GeoJSON FeatureCollection with paging links."""
    document = _payload(response)
    features = document.get("features")
    if document.get("type") != "FeatureCollection" or not isinstance(
        features, Sequence
    ):
        raise QgisSdkServiceResponseError(
            "expected a GeoJSON FeatureCollection",
            method=response.method,
            url=response.url,
        )
    next_url = None
    links = document.get("links", ())
    if isinstance(links, Sequence) and not isinstance(links, str):
        for link in links:
            if isinstance(link, Mapping) and link.get("rel") == "next":
                next_url = _text(link.get("href"))
                break
    matched = document.get("numberMatched")
    returned = document.get("numberReturned")
    return FeaturesPage(
        features=tuple(feature for feature in features if isinstance(feature, Mapping)),
        number_returned=returned if isinstance(returned, int) else len(features),
        number_matched=matched if isinstance(matched, int) else None,
        next_url=next_url,
    )


class OgcApiFeatures:
    """Coroutine methods for one OGC API - Features landing URL."""

    def __init__(self, network: Network, base_url: str) -> None:
        self._network = network.configure(
            base_url=base_url, headers={"Accept": "application/json"}
        )

    async def collections(self) -> tuple[CollectionInfo, ...]:
        """List the service's collections."""
        return parse_collections(await self._network.get("collections"))

    async def items(
        self,
        collection_id: str,
        *,
        limit: int = 10,
        bbox: Sequence[float] | None = None,
    ) -> FeaturesPage:
        """Fetch one page of a collection's features."""
        params: dict[str, str | int | float | bool | None] = {"limit": limit}
        if bbox is not None:
            params["bbox"] = ",".join(f"{value:g}" for value in bbox)
        return parse_features(
            await self._network.get(f"collections/{collection_id}/items", params=params)
        )

    async def next_page(self, page: FeaturesPage) -> FeaturesPage | None:
        """Follow a page's ``next`` link, or return ``None`` on the last page."""
        if page.next_url is None:
            return None
        return parse_features(await self._network.get(page.next_url))
