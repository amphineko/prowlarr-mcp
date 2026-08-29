from __future__ import annotations

import unittest

import httpx

from prowlarr_mcp.errors import ProwlarrResponseError, response_error


class ResponseErrorTest(unittest.TestCase):
    def error(self, response: httpx.Response) -> ProwlarrResponseError:
        return response_error(
            response,
            operation="search",
        )

    def test_reports_error_model_message(self) -> None:
        error = self.error(
            httpx.Response(
                404,
                json={
                    "message": "Indexer does not exist",
                    "description": "ignored stack trace",
                    "content": {"ignored": True},
                },
            )
        )

        self.assertEqual(error.status_code, 404)
        self.assertEqual(error.detail, "Indexer does not exist")
        self.assertEqual(
            str(error),
            "Prowlarr search failed with HTTP 404: Indexer does not exist",
        )

    def test_reports_problem_details_errors(self) -> None:
        error = self.error(
            httpx.Response(
                400,
                json={
                    "title": "One or more validation errors occurred.",
                    "traceId": "ignored-trace-id",
                    "errors": {
                        "limit": ["Limit is invalid", "Limit is invalid"],
                        "offset": ["Offset is invalid", "Another error"],
                    },
                },
            )
        )

        self.assertEqual(
            error.detail,
            "Limit is invalid; Offset is invalid; Another error",
        )

    def test_uses_problem_details_title_without_field_errors(self) -> None:
        error = self.error(
            httpx.Response(
                400,
                json={"title": "Request is invalid", "errors": {}},
            )
        )

        self.assertEqual(error.detail, "Request is invalid")

    def test_reports_fluent_validation_failures(self) -> None:
        error = self.error(
            httpx.Response(
                400,
                json=[
                    {
                        "propertyName": "categories",
                        "errorMessage": "Categories must be provided",
                    }
                ],
            )
        )

        self.assertEqual(error.detail, "Categories must be provided")

    def test_suppresses_unrecognized_or_unsafe_responses(self) -> None:
        responses = (
            httpx.Response(500, json={"message": "internal exception"}),
            httpx.Response(400, text="proxy error"),
            httpx.Response(400, json={"unknown": "shape"}),
        )

        for response in responses:
            with self.subTest(status=response.status_code):
                error = self.error(response)
                self.assertIsNone(error.detail)
                self.assertEqual(
                    str(error),
                    f"Prowlarr search failed with HTTP {response.status_code}",
                )
