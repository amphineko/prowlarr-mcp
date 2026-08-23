from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.lifespan import lifespan
from pydantic import Field

from prowlarr_mcp import __version__
from prowlarr_mcp.client import ProwlarrClient, ProwlarrError
from prowlarr_mcp.config import Settings
from prowlarr_mcp.models import SearchResults, SearchType
from prowlarr_mcp.service import SearchService

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    import httpx


def create_server(
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastMCP[None]:
    client = ProwlarrClient(settings, transport=transport)
    service = SearchService(client, max_results=settings.max_results)

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
            "Search releases through Prowlarr. Version 0.1 is strictly read-only "
            "and cannot submit releases to download clients."
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
        categories: list[Annotated[int, Field(gt=0)]] | None = None,
        limit: Annotated[int, Field(ge=1, le=1000)] = 20,
        offset: Annotated[int, Field(ge=0)] = 0,
    ) -> SearchResults:
        """Search enabled Prowlarr indexers for Torrent or Usenet releases.

        An empty query requests recent releases. Omit indexer_ids and categories to
        search all enabled indexers and categories. Results preserve Prowlarr's
        ordering. The indexer_id and guid identify a release for a future download
        submission capability, which is not available in version 0.1.
        """
        try:
            return await service.search_releases(
                query=query,
                search_type=search_type,
                indexer_ids=indexer_ids or (),
                categories=categories or (),
                limit=limit,
                offset=offset,
            )
        except (ProwlarrError, ValueError) as exc:
            raise ToolError(str(exc)) from exc

    return mcp


def main() -> None:
    create_server(Settings()).run()


if __name__ == "__main__":
    main()
