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
    async def test_server_exposes_only_read_only_search(self) -> None:
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
            self.assertEqual([tool.name for tool in tools], ["search_releases"])
            schema = tools[0].inputSchema["properties"]
            self.assertEqual(schema["limit"]["minimum"], 1)
            self.assertEqual(schema["limit"]["maximum"], 1000)
            self.assertEqual(schema["offset"]["minimum"], 0)
            self.assertEqual(
                schema["indexer_ids"]["anyOf"][0]["items"]["exclusiveMinimum"],
                0,
            )
            annotations = tools[0].annotations
            self.assertIsNotNone(annotations)
            if annotations is None:
                self.fail("search_releases must declare tool annotations")
            self.assertTrue(annotations.readOnlyHint)

            result = await client.call_tool("search_releases", {"query": "anime"})
            self.assertFalse(result.is_error)
            structured = result.structured_content
            self.assertIsNotNone(structured)
            if structured is None:
                self.fail("search_releases must return structured content")
            self.assertEqual(structured["returned"], 0)
            self.assertFalse(structured["truncated"])
            self.assertEqual(structured["releases"], [])

            invalid = await client.call_tool(
                "search_releases",
                {"limit": 0},
                raise_on_error=False,
            )
            self.assertTrue(invalid.is_error)

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
            return httpx.Response(500, text="sensitive upstream diagnostics")

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
