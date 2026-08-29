from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.lifespan import lifespan
from pydantic import Field

from prowlarr_mcp import __version__
from prowlarr_mcp.client import ProwlarrClient
from prowlarr_mcp.config import Settings
from prowlarr_mcp.errors import ProwlarrError
from prowlarr_mcp.models import (
    CategoryResults,
    DownloadClientResults,
    IndexerResults,
    ReleaseSubmissionResult,
    SearchResults,
    SearchType,
)
from prowlarr_mcp.service import (
    DiscoveryService,
    ReleaseSubmissionService,
    SearchService,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    import httpx


def create_server(
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastMCP[None]:
    client = ProwlarrClient(settings, transport=transport)
    search_service = SearchService(client, max_results=settings.max_results)
    discovery_service = DiscoveryService(client)
    submission_service = ReleaseSubmissionService(client)

    @lifespan
    async def server_lifespan(_: FastMCP[None]) -> AsyncGenerator[None]:
        try:
            yield None
        finally:
            await client.close()

    mcp: FastMCP[None] = FastMCP(
        "prowlarr-mcp",
        version=__version__,
        instructions=(
            "Search releases, inspect search and download capabilities, and submit "
            "selected releases through Prowlarr."
        ),
        lifespan=server_lifespan,
    )

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        }
    )
    async def search_releases(
        query: str = "",
        search_type: SearchType = SearchType.SEARCH,
        indexer_ids: list[Annotated[int, Field(gt=0)]] | None = None,
        categories: list[Annotated[int, Field(ge=0)]] | None = None,
        limit: Annotated[int, Field(ge=1, le=1000)] = 20,
        offset: Annotated[int, Field(ge=0)] = 0,
    ) -> SearchResults:
        """Search enabled Prowlarr indexers for Torrent or Usenet releases.

        An empty query requests recent releases. Omit indexer_ids and categories to
        search all enabled indexers and categories. Results preserve Prowlarr's
        ordering. The indexer_id and guid uniquely identify a release.
        """
        try:
            return await search_service.search_releases(
                query=query,
                search_type=search_type,
                indexer_ids=indexer_ids or (),
                categories=categories or (),
                limit=limit,
                offset=offset,
            )
        except (ProwlarrError, ValueError) as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        }
    )
    async def list_indexers(enabled_only: bool = True) -> IndexerResults:
        """List configured Prowlarr indexers and their search capabilities.

        By default, omit disabled indexers that cannot participate in searches.
        Returned category_ids can be resolved with list_categories.
        """
        try:
            return await discovery_service.list_indexers(enabled_only=enabled_only)
        except ProwlarrError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        }
    )
    async def list_categories() -> CategoryResults:
        """List Prowlarr's hierarchical search category taxonomy.

        The total counts both top-level categories and nested subcategories.
        """
        try:
            return await discovery_service.list_categories()
        except ProwlarrError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        }
    )
    async def list_download_clients(
        enabled_only: bool = True,
    ) -> DownloadClientResults:
        """List safe, submission-relevant details for configured download clients.

        By default, omit disabled clients. Use a returned id as the optional
        download_client_id when submitting a selected release.
        """
        try:
            return await discovery_service.list_download_clients(
                enabled_only=enabled_only
            )
        except ProwlarrError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        }
    )
    async def grab_release(
        indexer_id: Annotated[int, Field(gt=0)],
        guid: Annotated[str, Field(min_length=1)],
        download_client_id: Annotated[int, Field(gt=0)] | None = None,
    ) -> ReleaseSubmissionResult:
        """Submit a recently searched release to a configured download client.

        The indexer_id and guid must come from search_releases. Prowlarr caches
        search results for about 30 minutes; search again if the release expired.
        Omit download_client_id to let Prowlarr select its configured default.
        """
        try:
            return await submission_service.grab_release(
                indexer_id=indexer_id,
                guid=guid,
                download_client_id=download_client_id,
            )
        except (ProwlarrError, ValueError) as exc:
            raise ToolError(str(exc)) from exc

    return mcp


def main() -> None:
    create_server(Settings()).run()


if __name__ == "__main__":
    main()
