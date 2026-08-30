from __future__ import annotations

import unittest
from datetime import UTC, datetime
from typing import override

from prowlarr_mcp.models import (
    ApiCategory,
    ApiDownloadClient,
    ApiDownloadClientCategory,
    ApiIndexer,
    ApiIndexerCapabilities,
    ApiIndexerCategory,
    ApiRelease,
    ApiReleaseSubmission,
    DownloadProtocol,
    IndexerPrivacy,
    SearchType,
)
from prowlarr_mcp.service import (
    DiscoveryService,
    ReleaseSubmissionService,
    SearchService,
)


class StubClient:
    def __init__(self, releases: list[ApiRelease]) -> None:
        self.releases = releases

    async def search_releases(self, **_: object) -> list[ApiRelease]:
        return self.releases


class StubDiscoveryClient:
    def __init__(
        self,
        *,
        indexers: list[ApiIndexer],
        categories: list[ApiIndexerCategory],
        download_clients: list[ApiDownloadClient],
    ) -> None:
        self.indexers = indexers
        self.categories = categories
        self.download_clients = download_clients

    async def list_indexers(self) -> list[ApiIndexer]:
        return self.indexers

    async def list_categories(self) -> list[ApiIndexerCategory]:
        return self.categories

    async def list_download_clients(self) -> list[ApiDownloadClient]:
        return self.download_clients


class StubSubmissionClient:
    def __init__(self) -> None:
        self.submissions: list[ApiReleaseSubmission] = []

    async def grab_release(
        self,
        *,
        indexer_id: int,
        guid: str,
        download_client_id: int | None,
    ) -> ApiReleaseSubmission:
        submission = ApiReleaseSubmission(
            indexer_id=indexer_id,
            guid=guid,
            download_client_id=download_client_id,
        )
        self.submissions.append(submission)
        return submission


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

        with self.assertRaisesRegex(ValueError, "non-negative integers"):
            await service.search_releases(categories=[-1])

        result = await service.search_releases(categories=[0])
        self.assertEqual(result.returned, 0)

    async def test_rejects_invalid_pagination(self) -> None:
        service = SearchService(StubClient([]), max_results=100)

        with self.assertRaisesRegex(ValueError, "between 1 and 100"):
            await service.search_releases(limit=0)

        with self.assertRaisesRegex(ValueError, "non-negative"):
            await service.search_releases(offset=-1)


class ReleaseSubmissionServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_submits_and_maps_release_identity(self) -> None:
        client = StubSubmissionClient()
        service = ReleaseSubmissionService(client)

        result = await service.grab_release(
            indexer_id=7,
            guid="release-guid",
            download_client_id=3,
        )

        self.assertEqual(len(client.submissions), 1)
        self.assertEqual(result.indexer_id, 7)
        self.assertEqual(result.guid, "release-guid")
        self.assertEqual(result.download_client_id, 3)

    async def test_rejects_invalid_release_identity(self) -> None:
        service = ReleaseSubmissionService(StubSubmissionClient())

        with self.assertRaisesRegex(ValueError, "indexer_id"):
            await service.grab_release(indexer_id=0, guid="release-guid")
        with self.assertRaisesRegex(ValueError, "guid"):
            await service.grab_release(indexer_id=7, guid="  ")
        with self.assertRaisesRegex(ValueError, "download_client_id"):
            await service.grab_release(
                indexer_id=7,
                guid="release-guid",
                download_client_id=0,
            )


class DiscoveryServiceTest(unittest.IsolatedAsyncioTestCase):
    @override
    def setUp(self) -> None:
        category = ApiIndexerCategory(
            id=5000,
            name="TV",
            description="Television",
            sub_categories=[ApiIndexerCategory(id=5070, name="TV/Anime")],
        )
        self.enabled_indexer = ApiIndexer(
            id=7,
            name="Example Indexer",
            enable=True,
            protocol=DownloadProtocol.TORRENT,
            privacy=IndexerPrivacy.PRIVATE,
            supports_search=True,
            capabilities=ApiIndexerCapabilities(
                supports_raw_search=True,
                search_params=[{"name": "q"}],
                tv_search_params=[{"name": "season"}],
                categories=[category],
            ),
        )
        self.disabled_indexer = self.enabled_indexer.model_copy(
            update={"id": 8, "name": "Disabled", "enable": False}
        )
        self.enabled_download_client = ApiDownloadClient(
            id=3,
            name="Example Download Client",
            enable=True,
            protocol=DownloadProtocol.TORRENT,
            priority=1,
            supports_categories=True,
            categories=[
                ApiDownloadClientCategory(categories=[5000, 5070]),
                ApiDownloadClientCategory(categories=[5070]),
                ApiDownloadClientCategory(),
            ],
        )
        self.disabled_download_client = self.enabled_download_client.model_copy(
            update={"id": 4, "name": "Disabled", "enable": False}
        )
        self.service = DiscoveryService(
            StubDiscoveryClient(
                indexers=[self.enabled_indexer, self.disabled_indexer],
                categories=[category],
                download_clients=[
                    self.enabled_download_client,
                    self.disabled_download_client,
                ],
            )
        )

    async def test_maps_enabled_indexer_capabilities(self) -> None:
        result = await self.service.list_indexers()

        self.assertEqual(result.total, 1)
        self.assertEqual(result.indexers[0].id, 7)
        self.assertEqual(
            result.indexers[0].search_types,
            [SearchType.SEARCH, SearchType.TV],
        )
        self.assertEqual(result.indexers[0].category_ids, [5000, 5070])

    async def test_can_include_disabled_indexers(self) -> None:
        result = await self.service.list_indexers(enabled_only=False)

        self.assertEqual(result.total, 2)
        self.assertFalse(result.indexers[1].enabled)

    async def test_maps_category_tree(self) -> None:
        result = await self.service.list_categories()

        self.assertEqual(result.total, 2)
        self.assertEqual(result.categories[0].id, 5000)
        self.assertEqual(result.categories[0].subcategories[0].id, 5070)

    async def test_maps_enabled_download_clients(self) -> None:
        result = await self.service.list_download_clients()

        self.assertEqual(result.total, 1)
        self.assertEqual(result.download_clients[0].id, 3)
        self.assertTrue(result.download_clients[0].supports_categories)
        self.assertEqual(result.download_clients[0].category_ids, [5000, 5070])

    async def test_can_include_disabled_download_clients(self) -> None:
        result = await self.service.list_download_clients(enabled_only=False)

        self.assertEqual(result.total, 2)
        self.assertFalse(result.download_clients[1].enabled)
