from __future__ import annotations

import unittest

import httpx
from fastmcp import Client
from fastmcp.client.transports import FastMCPTransport
from pydantic import SecretStr

from prowlarr_mcp.config import Settings
from prowlarr_mcp.models import SearchResults, SearchType
from prowlarr_mcp.server import create_server


def release_payload(*, guid: str, title: str) -> dict[str, object]:
    return {
        "guid": guid,
        "indexerId": 7,
        "indexer": "Example Indexer",
        "title": title,
        "protocol": "torrent",
        "size": 123456,
        "publishDate": "2026-08-23T12:00:00Z",
        "seeders": 42,
        "leechers": 3,
        "grabs": 9,
        "categories": [{"id": 5070, "name": "TV/Anime"}],
        "infoHash": "ABC123",
        "infoUrl": "https://indexer.example/release",
    }


class SearchE2ETest(unittest.IsolatedAsyncioTestCase):
    async def test_search_round_trip_through_mcp_and_prowlarr_api(self) -> None:
        async def prowlarr_handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.path, "/base/api/v1/search")
            self.assertEqual(request.headers["X-Api-Key"], "secret-key")
            self.assertEqual(
                request.url.params.multi_items(),
                [
                    ("query", "yani neko"),
                    ("type", "tvsearch"),
                    ("limit", "1"),
                    ("offset", "2"),
                    ("indexerIds", "7"),
                    ("indexerIds", "8"),
                    ("categories", "5070"),
                ],
            )
            return httpx.Response(
                200,
                json=[
                    release_payload(guid="release-1", title="First Release"),
                    release_payload(guid="release-2", title="Second Release"),
                ],
            )

        server = create_server(
            Settings(
                url="http://prowlarr.test/base",
                api_key=SecretStr("secret-key"),
            ),
            transport=httpx.MockTransport(prowlarr_handler),
        )

        async with Client(FastMCPTransport(server)) as client:
            result = await client.call_tool(
                "search_releases",
                {
                    "query": "yani neko",
                    "search_type": "tvsearch",
                    "indexer_ids": [7, 8],
                    "categories": [5070],
                    "limit": 1,
                    "offset": 2,
                },
            )

        self.assertFalse(result.is_error)
        structured = result.structured_content
        self.assertIsNotNone(structured)
        if structured is None:
            self.fail("search_releases must return structured content")
        output = SearchResults.model_validate(structured)
        self.assertEqual(output.query, "yani neko")
        self.assertEqual(output.search_type, SearchType.TV)
        self.assertEqual(output.returned, 1)
        self.assertTrue(output.truncated)
        self.assertEqual(len(output.releases), 1)
        self.assertEqual(output.releases[0].guid, "release-1")
        self.assertEqual(output.releases[0].title, "First Release")
        self.assertEqual(output.releases[0].size_bytes, 123456)
        self.assertEqual(output.releases[0].categories[0].id, 5070)
        self.assertEqual(output.releases[0].categories[0].name, "TV/Anime")
