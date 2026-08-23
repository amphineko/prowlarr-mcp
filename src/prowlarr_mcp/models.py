from __future__ import annotations

from datetime import datetime  # noqa: TC003 - Pydantic resolves this at runtime.
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class SearchType(StrEnum):
    SEARCH = "search"
    TV = "tvsearch"
    MOVIE = "movie"
    MUSIC = "music"
    BOOK = "book"


class DownloadProtocol(StrEnum):
    UNKNOWN = "unknown"
    USENET = "usenet"
    TORRENT = "torrent"


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
    )


class ApiCategory(ApiModel):
    id: int
    name: str | None = None


class ApiRelease(ApiModel):
    guid: str
    indexer_id: int
    indexer: str | None = None
    title: str
    protocol: DownloadProtocol = DownloadProtocol.UNKNOWN
    size: int = 0
    publish_date: datetime
    seeders: int | None = None
    leechers: int | None = None
    grabs: int | None = None
    categories: list[ApiCategory] = Field(default_factory=list)
    info_hash: str | None = None
    info_url: str | None = None


class Category(BaseModel):
    id: int
    name: str | None = None


class ReleaseSummary(BaseModel):
    """Stable, compact release representation returned to MCP clients."""

    indexer_id: int
    guid: str
    indexer: str | None
    title: str
    protocol: DownloadProtocol
    size_bytes: int
    publish_date: datetime
    seeders: int | None
    leechers: int | None
    grabs: int | None
    categories: list[Category]
    info_hash: str | None
    info_url: str | None


class SearchResults(BaseModel):
    query: str
    search_type: SearchType
    limit: int
    offset: int
    returned: int
    truncated: bool
    releases: list[ReleaseSummary]
