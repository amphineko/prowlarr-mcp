from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from prowlarr_mcp.models import (
    ApiDownloadClient,
    ApiIndexer,
    ApiIndexerCategory,
    ApiRelease,
    ApiReleaseSubmission,
    Category,
    CategoryResults,
    DownloadClientResults,
    DownloadClientSummary,
    IndexerResults,
    IndexerSummary,
    ReleaseSubmissionResult,
    ReleaseSummary,
    SearchCategory,
    SearchResults,
    SearchType,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


class ReleaseSearchClient(Protocol):
    async def search_releases(
        self,
        *,
        query: str,
        search_type: SearchType,
        indexer_ids: Sequence[int],
        categories: Sequence[int],
        limit: int,
        offset: int,
    ) -> list[ApiRelease]: ...


class DiscoveryClient(Protocol):
    async def list_indexers(self) -> list[ApiIndexer]: ...

    async def list_categories(self) -> list[ApiIndexerCategory]: ...

    async def list_download_clients(self) -> list[ApiDownloadClient]: ...


class ReleaseSubmissionClient(Protocol):
    async def grab_release(
        self,
        *,
        indexer_id: int,
        guid: str,
        download_client_id: int | None,
    ) -> ApiReleaseSubmission: ...


class SearchService:
    def __init__(self, client: ReleaseSearchClient, *, max_results: int) -> None:
        self._client = client
        self._max_results = max_results

    async def search_releases(
        self,
        *,
        query: str = "",
        search_type: SearchType = SearchType.SEARCH,
        indexer_ids: Sequence[int] = (),
        categories: Sequence[int] = (),
        limit: int = 20,
        offset: int = 0,
    ) -> SearchResults:
        if not 1 <= limit <= self._max_results:
            raise ValueError(f"limit must be between 1 and {self._max_results}")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if any(indexer_id <= 0 for indexer_id in indexer_ids):
            raise ValueError("indexer_ids must contain only positive integers")
        if any(category < 0 for category in categories):
            raise ValueError("categories must contain only non-negative integers")

        releases = await self._client.search_releases(
            query=query,
            search_type=search_type,
            indexer_ids=indexer_ids,
            categories=categories,
            limit=limit,
            offset=offset,
        )
        summaries = [self._to_summary(release) for release in releases[:limit]]
        return SearchResults(
            query=query,
            search_type=search_type,
            limit=limit,
            offset=offset,
            returned=len(summaries),
            truncated=len(releases) > limit,
            releases=summaries,
        )

    @staticmethod
    def _to_summary(release: ApiRelease) -> ReleaseSummary:
        return ReleaseSummary(
            indexer_id=release.indexer_id,
            guid=release.guid,
            indexer=release.indexer,
            title=release.title,
            protocol=release.protocol,
            size_bytes=release.size,
            publish_date=release.publish_date,
            seeders=release.seeders,
            leechers=release.leechers,
            grabs=release.grabs,
            categories=[
                Category(id=category.id, name=category.name)
                for category in release.categories
            ],
            info_hash=release.info_hash,
            info_url=release.info_url,
        )


class ReleaseSubmissionService:
    def __init__(self, client: ReleaseSubmissionClient) -> None:
        self._client = client

    async def grab_release(
        self,
        *,
        indexer_id: int,
        guid: str,
        download_client_id: int | None = None,
    ) -> ReleaseSubmissionResult:
        if indexer_id <= 0:
            raise ValueError("indexer_id must be a positive integer")
        if not guid.strip():
            raise ValueError("guid must not be empty")
        if download_client_id is not None and download_client_id <= 0:
            raise ValueError("download_client_id must be a positive integer")

        submitted = await self._client.grab_release(
            indexer_id=indexer_id,
            guid=guid,
            download_client_id=download_client_id,
        )
        return ReleaseSubmissionResult(
            indexer_id=submitted.indexer_id,
            guid=submitted.guid,
            download_client_id=submitted.download_client_id,
        )


class DiscoveryService:
    def __init__(self, client: DiscoveryClient) -> None:
        self._client = client

    async def list_indexers(self, *, enabled_only: bool = True) -> IndexerResults:
        indexers = await self._client.list_indexers()
        summaries = [
            self._to_indexer_summary(indexer)
            for indexer in indexers
            if not enabled_only or indexer.enable
        ]
        return IndexerResults(total=len(summaries), indexers=summaries)

    async def list_categories(self) -> CategoryResults:
        api_categories = await self._client.list_categories()
        categories = [self._to_search_category(category) for category in api_categories]
        return CategoryResults(
            total=self._category_count(api_categories),
            categories=categories,
        )

    async def list_download_clients(
        self,
        *,
        enabled_only: bool = True,
    ) -> DownloadClientResults:
        download_clients = await self._client.list_download_clients()
        summaries = [
            self._to_download_client_summary(download_client)
            for download_client in download_clients
            if not enabled_only or download_client.enable
        ]
        return DownloadClientResults(
            total=len(summaries),
            download_clients=summaries,
        )

    @classmethod
    def _to_indexer_summary(cls, indexer: ApiIndexer) -> IndexerSummary:
        capabilities = indexer.capabilities
        search_types: list[SearchType] = []
        if indexer.supports_search and (
            capabilities.supports_raw_search or capabilities.search_params
        ):
            search_types.append(SearchType.SEARCH)
        search_parameter_groups = (
            (SearchType.TV, capabilities.tv_search_params),
            (SearchType.MOVIE, capabilities.movie_search_params),
            (SearchType.MUSIC, capabilities.music_search_params),
            (SearchType.BOOK, capabilities.book_search_params),
        )
        search_types.extend(
            search_type
            for search_type, parameters in search_parameter_groups
            if indexer.supports_search and parameters
        )
        return IndexerSummary(
            id=indexer.id,
            name=indexer.name,
            enabled=indexer.enable,
            protocol=indexer.protocol,
            privacy=indexer.privacy,
            priority=indexer.priority,
            supports_search=indexer.supports_search,
            supports_pagination=indexer.supports_pagination,
            search_types=search_types,
            category_ids=cls._category_ids(capabilities.categories or []),
        )

    @classmethod
    def _category_ids(cls, categories: list[ApiIndexerCategory]) -> list[int]:
        category_ids: list[int] = []
        for category in categories:
            category_ids.append(category.id)
            category_ids.extend(cls._category_ids(category.sub_categories or []))
        return list(dict.fromkeys(category_ids))

    @classmethod
    def _category_count(cls, categories: list[ApiIndexerCategory]) -> int:
        return sum(
            1 + cls._category_count(category.sub_categories or [])
            for category in categories
        )

    @staticmethod
    def _to_download_client_summary(
        download_client: ApiDownloadClient,
    ) -> DownloadClientSummary:
        return DownloadClientSummary(
            id=download_client.id,
            name=download_client.name,
            enabled=download_client.enable,
            protocol=download_client.protocol,
            priority=download_client.priority,
            supports_categories=download_client.supports_categories,
            category_ids=list(
                dict.fromkeys(
                    category_id
                    for mapping in download_client.categories
                    for category_id in mapping.categories or []
                )
            ),
        )

    @classmethod
    def _to_search_category(
        cls,
        category: ApiIndexerCategory,
    ) -> SearchCategory:
        return SearchCategory(
            id=category.id,
            name=category.name,
            subcategories=[
                cls._to_search_category(subcategory)
                for subcategory in category.sub_categories or []
            ],
        )
