from __future__ import annotations

import json
import unittest

import httpx
from pydantic import SecretStr

from prowlarr_mcp.client import (
    ProwlarrAuthenticationError,
    ProwlarrClient,
    ProwlarrConnectionError,
    ProwlarrResponseError,
)
from prowlarr_mcp.config import Settings
from prowlarr_mcp.models import DownloadProtocol, SearchType


def settings() -> Settings:
    return Settings(
        url="http://prowlarr.test/base",
        api_key=SecretStr("secret-key"),
    )


def release_payload() -> dict[str, object]:
    return {
        "guid": "release-guid",
        "indexerId": 7,
        "indexer": "Example",
        "title": "Example Release",
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


def failing_transport(
    error_type: type[httpx.RequestError],
) -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise error_type("unsafe internal details", request=request)

    return httpx.MockTransport(handler)


class ProwlarrClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_search_sends_header_and_repeated_filters(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                request.url,
                httpx.URL(
                    "http://prowlarr.test/base/api/v1/search"
                    "?query=anime&type=search&limit=20&offset=0"
                    "&indexerIds=7&indexerIds=8&categories=5070"
                ),
            )
            self.assertEqual(request.headers["X-Api-Key"], "secret-key")
            return httpx.Response(200, json=[release_payload()])

        client = ProwlarrClient(settings(), transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)

        releases = await client.search_releases(
            query="anime",
            search_type=SearchType.SEARCH,
            indexer_ids=[7, 8],
            categories=[5070],
            limit=20,
            offset=0,
        )

        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0].protocol, DownloadProtocol.TORRENT)
        self.assertEqual(releases[0].guid, "release-guid")

    async def test_authentication_error_does_not_include_api_key(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(401)

        client = ProwlarrClient(settings(), transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)

        with self.assertRaises(ProwlarrAuthenticationError) as raised:
            await client.search_releases(
                query="",
                search_type=SearchType.SEARCH,
                indexer_ids=[],
                categories=[],
                limit=20,
                offset=0,
            )

        self.assertNotIn("secret-key", str(raised.exception))

    async def test_forbidden_is_an_authentication_error(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(403)

        client = ProwlarrClient(settings(), transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)

        with self.assertRaises(ProwlarrAuthenticationError):
            await client.search_releases(
                query="",
                search_type=SearchType.SEARCH,
                indexer_ids=[],
                categories=[],
                limit=20,
                offset=0,
            )

    async def test_server_error_is_reported_without_response_body(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="sensitive upstream diagnostics")

        client = ProwlarrClient(settings(), transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)

        with self.assertRaises(ProwlarrResponseError) as raised:
            await client.search_releases(
                query="",
                search_type=SearchType.SEARCH,
                indexer_ids=[],
                categories=[],
                limit=20,
                offset=0,
            )

        self.assertEqual(
            str(raised.exception),
            "Prowlarr search failed with HTTP 500",
        )

    async def test_request_errors_use_safe_consistent_message(self) -> None:
        request_error_types = (
            httpx.ConnectError,
            httpx.ReadTimeout,
            httpx.RemoteProtocolError,
        )

        for error_type in request_error_types:
            with self.subTest(error_type=error_type.__name__):
                client = ProwlarrClient(
                    settings(),
                    transport=failing_transport(error_type),
                )
                self.addAsyncCleanup(client.close)

                with self.assertRaises(ProwlarrConnectionError) as raised:
                    await client.search_releases(
                        query="",
                        search_type=SearchType.SEARCH,
                        indexer_ids=[],
                        categories=[],
                        limit=20,
                        offset=0,
                    )

                self.assertEqual(
                    str(raised.exception),
                    "Could not complete the request to Prowlarr",
                )
                self.assertNotIn("unsafe internal details", str(raised.exception))

    async def test_invalid_json_shape_is_reported(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=json.dumps({"not": "a list"}).encode(),
            )

        client = ProwlarrClient(settings(), transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)

        with self.assertRaises(ProwlarrResponseError):
            await client.search_releases(
                query="",
                search_type=SearchType.SEARCH,
                indexer_ids=[],
                categories=[],
                limit=20,
                offset=0,
            )

    async def test_malformed_release_is_reported(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            malformed_release = release_payload()
            del malformed_release["guid"]
            return httpx.Response(200, json=[malformed_release])

        client = ProwlarrClient(settings(), transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)

        with self.assertRaises(ProwlarrResponseError):
            await client.search_releases(
                query="",
                search_type=SearchType.SEARCH,
                indexer_ids=[],
                categories=[],
                limit=20,
                offset=0,
            )

    async def test_settings_api_key_is_secret(self) -> None:
        configured = settings()
        rendered = repr(configured)
        self.assertNotIn(
            configured.api_key.get_secret_value(),
            rendered,
        )
