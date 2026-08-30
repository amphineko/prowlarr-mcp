from __future__ import annotations

import json
import unittest

import httpx
from pydantic import SecretStr

from prowlarr_mcp.client import ProwlarrClient
from prowlarr_mcp.config import Settings
from prowlarr_mcp.errors import (
    ProwlarrAuthenticationError,
    ProwlarrConnectionError,
    ProwlarrResponseError,
)
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


def indexer_payload() -> dict[str, object]:
    return {
        "id": 7,
        "name": "Example Indexer",
        "enable": True,
        "protocol": "torrent",
        "privacy": "private",
        "priority": 25,
        "supportsSearch": True,
        "supportsPagination": False,
        "capabilities": {
            "supportsRawSearch": True,
            "searchParams": [{"name": "q"}],
            "tvSearchParams": [{"name": "season"}],
            "categories": [{"id": 5000, "name": "TV"}],
        },
        "fields": [{"name": "apiKey", "value": "upstream-secret"}],
    }


def category_payload() -> dict[str, object]:
    return {
        "id": 5000,
        "name": "TV",
        "description": "Television",
        "subCategories": [{"id": 5070, "name": "TV/Anime"}],
    }


def download_client_payload() -> dict[str, object]:
    return {
        "id": 3,
        "name": "Example Download Client",
        "enable": True,
        "protocol": "torrent",
        "priority": 1,
        "supportsCategories": True,
        "categories": [
            {"clientCategory": "anime", "categories": [5000, 5070]},
        ],
        "fields": [
            {"name": "host", "value": "download-client.internal"},
            {"name": "password", "value": "upstream-secret"},
        ],
    }


def health_payload() -> dict[str, object]:
    return {
        "id": 1,
        "source": "IndexerStatusCheck",
        "type": "warning",
        "message": "Some indexers are unavailable",
        "wikiUrl": "https://wiki.servarr.com/prowlarr/system",
    }


def indexer_status_payload() -> dict[str, object]:
    return {
        "id": 9,
        "indexerId": 7,
        "disabledTill": "2026-08-30T17:00:00Z",
        "mostRecentFailure": "2026-08-30T16:00:00Z",
        "initialFailure": "2026-08-29T12:00:00Z",
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

    async def test_lists_indexers(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                request.url,
                httpx.URL("http://prowlarr.test/base/api/v1/indexer"),
            )
            return httpx.Response(200, json=[indexer_payload()])

        client = ProwlarrClient(settings(), transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)

        indexers = await client.list_indexers()

        self.assertEqual(len(indexers), 1)
        self.assertEqual(indexers[0].id, 7)
        categories = indexers[0].capabilities.categories
        self.assertIsNotNone(categories)
        if categories is None:
            self.fail("indexer response must preserve capability categories")
        self.assertEqual(categories[0].id, 5000)
        self.assertFalse(hasattr(indexers[0], "fields"))

    async def test_lists_categories(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                request.url,
                httpx.URL("http://prowlarr.test/base/api/v1/indexer/categories"),
            )
            return httpx.Response(200, json=[category_payload()])

        client = ProwlarrClient(settings(), transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)

        categories = await client.list_categories()

        self.assertEqual(len(categories), 1)
        subcategories = categories[0].sub_categories
        self.assertIsNotNone(subcategories)
        if subcategories is None:
            self.fail("category response must preserve subcategories")
        self.assertEqual(subcategories[0].id, 5070)

    async def test_lists_download_clients(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                request.url,
                httpx.URL("http://prowlarr.test/base/api/v1/downloadclient"),
            )
            return httpx.Response(200, json=[download_client_payload()])

        client = ProwlarrClient(settings(), transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)

        download_clients = await client.list_download_clients()

        self.assertEqual(len(download_clients), 1)
        self.assertEqual(download_clients[0].id, 3)
        self.assertEqual(download_clients[0].categories[0].categories, [5000, 5070])
        self.assertFalse(hasattr(download_clients[0], "fields"))

    async def test_submits_release_to_selected_download_client(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertEqual(
                request.url,
                httpx.URL("http://prowlarr.test/base/api/v1/search"),
            )
            self.assertEqual(request.headers["X-Api-Key"], "secret-key")
            self.assertEqual(
                json.loads(request.content),
                {
                    "indexerId": 7,
                    "guid": "release-guid",
                    "downloadClientId": 3,
                },
            )
            return httpx.Response(
                200,
                json={
                    "indexerId": 7,
                    "guid": "release-guid",
                    "downloadClientId": 3,
                },
            )

        client = ProwlarrClient(settings(), transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)

        submitted = await client.grab_release(
            indexer_id=7,
            guid="release-guid",
            download_client_id=3,
        )

        self.assertEqual(submitted.indexer_id, 7)
        self.assertEqual(submitted.guid, "release-guid")
        self.assertEqual(submitted.download_client_id, 3)

    async def test_submission_omits_default_download_client(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                json.loads(request.content),
                {"indexerId": 7, "guid": "release-guid"},
            )
            return httpx.Response(
                200,
                json={"indexerId": 7, "guid": "release-guid"},
            )

        client = ProwlarrClient(settings(), transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)

        submitted = await client.grab_release(
            indexer_id=7,
            guid="release-guid",
            download_client_id=None,
        )

        self.assertIsNone(submitted.download_client_id)

    async def test_gets_health_checks(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                request.url,
                httpx.URL("http://prowlarr.test/base/api/v1/health"),
            )
            return httpx.Response(200, json=[health_payload()])

        client = ProwlarrClient(settings(), transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)

        checks = await client.get_health()

        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0].source, "IndexerStatusCheck")
        self.assertEqual(checks[0].type, "warning")

    async def test_gets_blocked_indexer_status(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(
                request.url,
                httpx.URL("http://prowlarr.test/base/api/v1/indexerstatus"),
            )
            return httpx.Response(200, json=[indexer_status_payload()])

        client = ProwlarrClient(settings(), transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)

        statuses = await client.get_indexer_status()

        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0].indexer_id, 7)
        self.assertIsNotNone(statuses[0].disabled_till)

    async def test_invalid_indexer_response_is_reported(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            malformed = indexer_payload()
            del malformed["id"]
            return httpx.Response(200, json=[malformed])

        client = ProwlarrClient(settings(), transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)

        with self.assertRaisesRegex(ProwlarrResponseError, "invalid indexer"):
            await client.list_indexers()

    async def test_invalid_category_response_is_reported(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[{"name": "Missing ID"}])

        client = ProwlarrClient(settings(), transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)

        with self.assertRaisesRegex(ProwlarrResponseError, "invalid category"):
            await client.list_categories()

    async def test_invalid_download_client_response_is_reported(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[{"name": "Missing ID"}])

        client = ProwlarrClient(settings(), transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)

        with self.assertRaisesRegex(ProwlarrResponseError, "invalid download client"):
            await client.list_download_clients()

    async def test_invalid_submission_response_is_reported(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"guid": "missing-indexer-id"})

        client = ProwlarrClient(settings(), transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)

        with self.assertRaisesRegex(
            ProwlarrResponseError, "invalid release submission"
        ):
            await client.grab_release(
                indexer_id=7,
                guid="release-guid",
                download_client_id=None,
            )

    async def test_invalid_diagnostic_responses_are_reported(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/health"):
                return httpx.Response(200, json=[{"type": "unknown-severity"}])
            return httpx.Response(200, json=[{"disabledTill": None}])

        client = ProwlarrClient(settings(), transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)

        with self.assertRaisesRegex(ProwlarrResponseError, "invalid health"):
            await client.get_health()
        with self.assertRaisesRegex(ProwlarrResponseError, "invalid indexer status"):
            await client.get_indexer_status()

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
            return httpx.Response(
                500,
                json={"message": "sensitive upstream diagnostics"},
            )

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
        self.assertEqual(raised.exception.status_code, 500)
        self.assertIsNone(raised.exception.detail)

    async def test_client_error_includes_only_safe_error_model_message(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                404,
                json={
                    "message": (
                        "Release at https://internal.example/release for secret-key "
                        "has expired"
                    ),
                    "description": "stack trace containing secret-key",
                    "content": {"diagnostics": "unsafe content"},
                },
            )

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

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(
            raised.exception.detail,
            "Release at [URL] for [redacted] has expired",
        )
        self.assertEqual(
            str(raised.exception),
            "Prowlarr search failed with HTTP 404: "
            "Release at [URL] for [redacted] has expired",
        )
        self.assertNotIn("stack trace", str(raised.exception))
        self.assertNotIn("internal.example", str(raised.exception))
        self.assertNotIn("unsafe content", str(raised.exception))

    async def test_problem_details_are_sanitized_and_bounded(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json={
                    "title": "One or more validation errors occurred.",
                    "status": 400,
                    "traceId": "unsafe-trace-id",
                    "errors": {
                        "limit": [
                            "Invalid secret-key at https://internal.example/value\u001b",
                            "Invalid path /home/example/private/file",
                        ],
                        "offset": ["x" * 400],
                    },
                },
            )

        client = ProwlarrClient(settings(), transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)

        with self.assertRaises(ProwlarrResponseError) as raised:
            await client.list_indexers()

        rendered = str(raised.exception)
        self.assertLessEqual(len(raised.exception.detail or ""), 300)
        self.assertIn("[redacted]", rendered)
        self.assertIn("[URL]", rendered)
        self.assertIn("[path]", rendered)
        self.assertNotIn("secret-key", rendered)
        self.assertNotIn("internal.example", rendered)
        self.assertNotIn("unsafe-trace-id", rendered)
        self.assertNotIn("\u001b", rendered)

    async def test_fluent_validation_errors_are_reported(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                json=[
                    {
                        "propertyName": "categories",
                        "errorMessage": "Categories must be provided",
                        "severity": "error",
                    }
                ],
            )

        client = ProwlarrClient(settings(), transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)

        with self.assertRaises(ProwlarrResponseError) as raised:
            await client.list_categories()

        self.assertEqual(raised.exception.detail, "Categories must be provided")

    async def test_non_json_client_error_body_is_not_reported(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                text="unsafe proxy diagnostics",
                headers={"Content-Type": "text/html"},
            )

        client = ProwlarrClient(settings(), transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.close)

        with self.assertRaises(ProwlarrResponseError) as raised:
            await client.list_categories()

        self.assertEqual(
            str(raised.exception),
            "Prowlarr category discovery failed with HTTP 400",
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
