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


class IndexerPrivacy(StrEnum):
    PUBLIC = "public"
    SEMI_PRIVATE = "semiPrivate"
    PRIVATE = "private"


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
    )


class ApiCategory(ApiModel):
    id: int
    name: str | None = None


class ApiIndexerCategory(ApiModel):
    id: int
    name: str | None = None
    description: str | None = None
    sub_categories: list[ApiIndexerCategory] | None = None


class ApiIndexerCapabilities(ApiModel):
    limits_max: int | None = None
    limits_default: int | None = None
    categories: list[ApiIndexerCategory] | None = None
    supports_raw_search: bool = False
    search_params: list[object] | None = None
    tv_search_params: list[object] | None = None
    movie_search_params: list[object] | None = None
    music_search_params: list[object] | None = None
    book_search_params: list[object] | None = None


class ApiIndexer(ApiModel):
    id: int
    name: str
    enable: bool = False
    protocol: DownloadProtocol = DownloadProtocol.UNKNOWN
    privacy: IndexerPrivacy | None = None
    priority: int = 25
    supports_search: bool = False
    supports_pagination: bool = False
    capabilities: ApiIndexerCapabilities = Field(default_factory=ApiIndexerCapabilities)


class ApiDownloadClientCategory(ApiModel):
    categories: list[int] | None = None


class ApiDownloadClient(ApiModel):
    id: int
    name: str
    enable: bool = False
    protocol: DownloadProtocol = DownloadProtocol.UNKNOWN
    priority: int = 1
    categories: list[ApiDownloadClientCategory] = Field(default_factory=list)
    supports_categories: bool = False


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


class SearchCategory(BaseModel):
    id: int
    name: str | None
    subcategories: list[SearchCategory]


class IndexerSummary(BaseModel):
    id: int
    name: str
    enabled: bool
    protocol: DownloadProtocol
    privacy: IndexerPrivacy | None
    priority: int
    supports_search: bool
    supports_pagination: bool
    search_types: list[SearchType]
    category_ids: list[int]


class IndexerResults(BaseModel):
    total: int
    indexers: list[IndexerSummary]


class CategoryResults(BaseModel):
    total: int
    categories: list[SearchCategory]


class DownloadClientSummary(BaseModel):
    id: int
    name: str
    enabled: bool
    protocol: DownloadProtocol
    priority: int
    supports_categories: bool
    category_ids: list[int]


class DownloadClientResults(BaseModel):
    total: int
    download_clients: list[DownloadClientSummary]


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
