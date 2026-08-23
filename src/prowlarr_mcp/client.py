from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from pydantic import TypeAdapter, ValidationError

from prowlarr_mcp.models import ApiRelease, SearchType

if TYPE_CHECKING:
    from collections.abc import Sequence

    from prowlarr_mcp.config import Settings


class ProwlarrError(Exception):
    """Base error for failures while communicating with Prowlarr."""


class ProwlarrAuthenticationError(ProwlarrError):
    """Prowlarr rejected the configured API key."""


class ProwlarrResponseError(ProwlarrError):
    """Prowlarr returned an unsuccessful or invalid response."""


class ProwlarrConnectionError(ProwlarrError):
    """Prowlarr could not be reached within the configured timeout."""


_RELEASE_LIST = TypeAdapter(list[ApiRelease])


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

        try:
            response = await self._client.get("api/v1/search", params=params)
        except httpx.RequestError as exc:
            raise ProwlarrConnectionError(
                "Could not complete the request to Prowlarr"
            ) from exc

        if response.status_code in {401, 403}:
            raise ProwlarrAuthenticationError(
                "Prowlarr rejected the configured API key"
            )
        if response.is_error:
            raise ProwlarrResponseError(
                f"Prowlarr search failed with HTTP {response.status_code}"
            )

        try:
            return _RELEASE_LIST.validate_json(response.content)
        except ValidationError as exc:
            raise ProwlarrResponseError(
                "Prowlarr returned an invalid search response"
            ) from exc
