from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from prowlarr_mcp.models import (
    ApiRelease,
    Category,
    ReleaseSummary,
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
        if any(category <= 0 for category in categories):
            raise ValueError("categories must contain only positive integers")

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
