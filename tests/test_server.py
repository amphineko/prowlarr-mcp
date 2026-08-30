from __future__ import annotations

import unittest
from typing import override

import httpx
from fastmcp import Client
from pydantic import SecretStr

from prowlarr_mcp.config import Settings
from prowlarr_mcp.server import create_server


class TrackingTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.closed = False

    @override
    async def handle_async_request(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        return httpx.Response(200, json=[])

    @override
    async def aclose(self) -> None:
        self.closed = True


class McpServerTest(unittest.IsolatedAsyncioTestCase):
    async def test_server_exposes_tools_with_explicit_behavior(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[])

        server = create_server(
            Settings(
                url="http://prowlarr.test",
                api_key=SecretStr("secret-key"),
            ),
            transport=httpx.MockTransport(handler),
        )

        async with Client(server) as client:
            tools = await client.list_tools()
            tools_by_name = {tool.name: tool for tool in tools}
            self.assertEqual(
                set(tools_by_name),
                {
                    "search_releases",
                    "list_indexers",
                    "list_categories",
                    "list_download_clients",
                    "grab_release",
                    "get_health",
                    "get_indexer_status",
                },
            )
            schema = tools_by_name["search_releases"].inputSchema["properties"]
            self.assertEqual(schema["limit"]["minimum"], 1)
            self.assertEqual(schema["limit"]["maximum"], 1000)
            self.assertEqual(schema["offset"]["minimum"], 0)
            self.assertEqual(
                schema["indexer_ids"]["anyOf"][0]["items"]["exclusiveMinimum"],
                0,
            )
            self.assertEqual(
                schema["categories"]["anyOf"][0]["items"]["minimum"],
                0,
            )
            self.assertTrue(
                tools_by_name["list_indexers"].inputSchema["properties"][
                    "enabled_only"
                ]["default"]
            )
            self.assertTrue(
                tools_by_name["list_download_clients"].inputSchema["properties"][
                    "enabled_only"
                ]["default"]
            )
            grab_schema = tools_by_name["grab_release"].inputSchema["properties"]
            self.assertEqual(grab_schema["indexer_id"]["exclusiveMinimum"], 0)
            self.assertEqual(grab_schema["guid"]["minLength"], 1)
            self.assertEqual(
                grab_schema["download_client_id"]["anyOf"][0]["exclusiveMinimum"],
                0,
            )
            for tool in tools:
                annotations = tool.annotations
                self.assertIsNotNone(annotations)
                if annotations is None:
                    self.fail(f"{tool.name} must declare tool annotations")
                self.assertFalse(annotations.destructiveHint)
                if tool.name == "grab_release":
                    self.assertFalse(annotations.readOnlyHint)
                    self.assertFalse(annotations.idempotentHint)
                else:
                    self.assertTrue(annotations.readOnlyHint)
                    self.assertTrue(annotations.idempotentHint)

            result = await client.call_tool("search_releases", {"query": "anime"})
            self.assertFalse(result.is_error)
            structured = result.structured_content
            self.assertIsNotNone(structured)
            if structured is None:
                self.fail("search_releases must return structured content")
            self.assertEqual(structured["returned"], 0)
            self.assertFalse(structured["truncated"])
            self.assertEqual(structured["releases"], [])

            indexers = await client.call_tool("list_indexers", {})
            self.assertFalse(indexers.is_error)
            self.assertEqual(indexers.structured_content, {"total": 0, "indexers": []})

            categories = await client.call_tool("list_categories", {})
            self.assertFalse(categories.is_error)
            self.assertEqual(
                categories.structured_content,
                {"total": 0, "categories": []},
            )

            download_clients = await client.call_tool("list_download_clients", {})
            self.assertFalse(download_clients.is_error)
            self.assertEqual(
                download_clients.structured_content,
                {"total": 0, "download_clients": []},
            )

            health = await client.call_tool("get_health", {})
            self.assertFalse(health.is_error)
            self.assertEqual(
                health.structured_content,
                {"total": 0, "checks": []},
            )

            indexer_status = await client.call_tool("get_indexer_status", {})
            self.assertFalse(indexer_status.is_error)
            self.assertEqual(
                indexer_status.structured_content,
                {"total": 0, "statuses": []},
            )

            invalid = await client.call_tool(
                "search_releases",
                {"limit": 0},
                raise_on_error=False,
            )
            self.assertTrue(invalid.is_error)

            invalid_grab = await client.call_tool(
                "grab_release",
                {"indexer_id": 0, "guid": ""},
                raise_on_error=False,
            )
            self.assertTrue(invalid_grab.is_error)

    async def test_lifespan_closes_http_transport(self) -> None:
        transport = TrackingTransport()
        server = create_server(
            Settings(
                url="http://prowlarr.test",
                api_key=SecretStr("secret-key"),
            ),
            transport=transport,
        )

        async with Client(server):
            self.assertFalse(transport.closed)

        self.assertTrue(transport.closed)

    async def test_upstream_error_is_a_safe_tool_error(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                500,
                json={"message": "sensitive upstream diagnostics"},
            )

        server = create_server(
            Settings(
                url="http://prowlarr.test",
                api_key=SecretStr("secret-key"),
            ),
            transport=httpx.MockTransport(handler),
        )

        async with Client(server) as client:
            result = await client.call_tool(
                "search_releases",
                {},
                raise_on_error=False,
            )

        self.assertTrue(result.is_error)
        rendered = " ".join(getattr(content, "text", "") for content in result.content)
        self.assertIn("HTTP 500", rendered)
        self.assertNotIn("sensitive upstream diagnostics", rendered)
        self.assertNotIn("secret-key", rendered)

    async def test_safe_upstream_detail_reaches_tool_error(self) -> None:
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                404,
                json={
                    "message": "Release cache entry has expired",
                    "description": "stack trace containing secret-key",
                },
            )

        server = create_server(
            Settings(
                url="http://prowlarr.test",
                api_key=SecretStr("secret-key"),
            ),
            transport=httpx.MockTransport(handler),
        )

        async with Client(server) as client:
            result = await client.call_tool(
                "search_releases",
                {},
                raise_on_error=False,
            )

        self.assertTrue(result.is_error)
        rendered = " ".join(getattr(content, "text", "") for content in result.content)
        self.assertIn("HTTP 404: Release cache entry has expired", rendered)
        self.assertNotIn("stack trace", rendered)
        self.assertNotIn("secret-key", rendered)
