from __future__ import annotations

import unittest
from datetime import UTC, datetime

from prowlarr_mcp.models import (
    ApiCategory,
    ApiRelease,
    DownloadProtocol,
    SearchType,
)
from prowlarr_mcp.service import SearchService


class StubClient:
    def __init__(self, releases: list[ApiRelease]) -> None:
        self.releases = releases

    async def search_releases(self, **_: object) -> list[ApiRelease]:
        return self.releases


class SearchServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_maps_compact_search_result(self) -> None:
        release = ApiRelease(
            guid="guid",
            indexer_id=12,
            indexer="Example",
            title="Release",
            protocol=DownloadProtocol.TORRENT,
            size=1000,
            publish_date=datetime(2026, 8, 23, tzinfo=UTC),
            seeders=10,
            categories=[ApiCategory(id=5070, name="TV/Anime")],
        )
        service = SearchService(
            StubClient([release]),
            max_results=100,
        )

        result = await service.search_releases(query="anime")

        self.assertEqual(result.returned, 1)
        self.assertEqual(result.releases[0].size_bytes, 1000)
        self.assertEqual(result.releases[0].categories[0].id, 5070)

    async def test_enforces_limit_on_upstream_results(self) -> None:
        releases = [
            ApiRelease(
                guid=f"guid-{index}",
                indexer_id=12,
                title=f"Release {index}",
                protocol=DownloadProtocol.TORRENT,
                publish_date=datetime(2026, 8, 23, tzinfo=UTC),
            )
            for index in range(3)
        ]
        service = SearchService(StubClient(releases), max_results=100)

        result = await service.search_releases(limit=1)

        self.assertEqual(result.returned, 1)
        self.assertTrue(result.truncated)
        self.assertEqual([release.guid for release in result.releases], ["guid-0"])

    async def test_rejects_limit_above_configured_maximum(self) -> None:
        service = SearchService(
            StubClient([]),
            max_results=50,
        )

        with self.assertRaisesRegex(ValueError, "between 1 and 50"):
            await service.search_releases(limit=51)

    async def test_rejects_invalid_filter_ids(self) -> None:
        service = SearchService(
            StubClient([]),
            max_results=100,
        )

        with self.assertRaisesRegex(ValueError, "positive integers"):
            await service.search_releases(
                search_type=SearchType.SEARCH,
                indexer_ids=[0],
            )

        with self.assertRaisesRegex(ValueError, "positive integers"):
            await service.search_releases(categories=[-1])

    async def test_rejects_invalid_pagination(self) -> None:
        service = SearchService(StubClient([]), max_results=100)

        with self.assertRaisesRegex(ValueError, "between 1 and 100"):
            await service.search_releases(limit=0)

        with self.assertRaisesRegex(ValueError, "non-negative"):
            await service.search_releases(offset=-1)
