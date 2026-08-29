from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from pydantic import TypeAdapter, ValidationError

from prowlarr_mcp.errors import (
    ProwlarrAuthenticationError,
    ProwlarrConnectionError,
    ProwlarrResponseError,
    response_error,
)
from prowlarr_mcp.models import (
    ApiDownloadClient,
    ApiIndexer,
    ApiIndexerCategory,
    ApiRelease,
    SearchType,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from prowlarr_mcp.config import Settings


_RELEASE_LIST = TypeAdapter(list[ApiRelease])
_INDEXER_LIST = TypeAdapter(list[ApiIndexer])
_CATEGORY_LIST = TypeAdapter(list[ApiIndexerCategory])
_DOWNLOAD_CLIENT_LIST = TypeAdapter(list[ApiDownloadClient])


class ProwlarrClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=f"{settings.url}/",
            headers={
                "Accept": "application/json",
                "X-Api-Key": settings.api_key.get_secret_value(),
            },
            timeout=settings.timeout_seconds,
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def search_releases(
        self,
        *,
        query: str,
        search_type: SearchType,
        indexer_ids: Sequence[int],
        categories: Sequence[int],
        limit: int,
        offset: int,
    ) -> list[ApiRelease]:
        params: list[tuple[str, str | int | float | bool | None]] = [
            ("query", query),
            ("type", search_type.value),
            ("limit", limit),
            ("offset", offset),
        ]
        params.extend(("indexerIds", indexer_id) for indexer_id in indexer_ids)
        params.extend(("categories", category) for category in categories)

        response = await self._get(
            "api/v1/search",
            operation="search",
            params=params,
        )

        try:
            return _RELEASE_LIST.validate_json(response.content)
        except ValidationError as exc:
            raise ProwlarrResponseError(
                "Prowlarr returned an invalid search response"
            ) from exc

    async def list_indexers(self) -> list[ApiIndexer]:
        response = await self._get(
            "api/v1/indexer",
            operation="indexer discovery",
        )
        try:
            return _INDEXER_LIST.validate_json(response.content)
        except ValidationError as exc:
            raise ProwlarrResponseError(
                "Prowlarr returned an invalid indexer response"
            ) from exc

    async def list_categories(self) -> list[ApiIndexerCategory]:
        response = await self._get(
            "api/v1/indexer/categories",
            operation="category discovery",
        )
        try:
            return _CATEGORY_LIST.validate_json(response.content)
        except ValidationError as exc:
            raise ProwlarrResponseError(
                "Prowlarr returned an invalid category response"
            ) from exc

    async def list_download_clients(self) -> list[ApiDownloadClient]:
        response = await self._get(
            "api/v1/downloadclient",
            operation="download client discovery",
        )
        try:
            return _DOWNLOAD_CLIENT_LIST.validate_json(response.content)
        except ValidationError as exc:
            raise ProwlarrResponseError(
                "Prowlarr returned an invalid download client response"
            ) from exc

    async def _get(
        self,
        path: str,
        *,
        operation: str,
        params: list[tuple[str, str | int | float | bool | None]] | None = None,
    ) -> httpx.Response:
        try:
            response = await self._client.get(path, params=params)
        except httpx.RequestError as exc:
            raise ProwlarrConnectionError(
                "Could not complete the request to Prowlarr"
            ) from exc

        if response.status_code in {401, 403}:
            raise ProwlarrAuthenticationError(
                "Prowlarr rejected the configured API key"
            )
        if response.is_error:
            raise response_error(
                response,
                operation=operation,
                api_key=self._client.headers.get("X-Api-Key", ""),
            )
        return response
