from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import Field, TypeAdapter, ValidationError

from prowlarr_mcp.models import ApiModel

if TYPE_CHECKING:
    import httpx


class _ErrorModel(ApiModel):
    message: str | None = None


class _ProblemDetails(ApiModel):
    title: str | None = None
    errors: dict[str, list[str]] = Field(default_factory=dict)


class _ValidationFailure(ApiModel):
    error_message: str | None = None


class ProwlarrError(Exception):
    """Base error for failures while communicating with Prowlarr."""


class ProwlarrAuthenticationError(ProwlarrError):
    """Prowlarr rejected the configured API key."""


class ProwlarrResponseError(ProwlarrError):
    """Prowlarr returned an unsuccessful or invalid response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        detail: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        rendered = f"{message}: {detail}" if detail else message
        super().__init__(rendered)


class ProwlarrConnectionError(ProwlarrError):
    """Prowlarr could not be reached within the configured timeout."""


_ERROR_MODEL = TypeAdapter(_ErrorModel)
_PROBLEM_DETAILS = TypeAdapter(_ProblemDetails)
_VALIDATION_FAILURES = TypeAdapter(list[_ValidationFailure])
_MAX_ERROR_DETAILS = 3
_ERROR_DETAIL_LIMIT = 300
_URL_PATTERN = re.compile(r"\b(?:https?|ftp)://\S+", re.IGNORECASE)
_WINDOWS_PATH_PATTERN = re.compile(r"\b[A-Za-z]:\\(?:[^\\\s]+\\)*[^\\\s]*")
_UNIX_PATH_PATTERN = re.compile(r"(?<![\w:])/(?:[^/\s]+/)+[^/\s]*")


def _parse_error_details(response: httpx.Response) -> list[str]:
    if not 400 <= response.status_code < 500:
        return []
    media_type = (
        response.headers.get("content-type", "").partition(";")[0].strip().lower()
    )
    if media_type != "application/json" and not media_type.endswith("+json"):
        return []

    candidates: list[str] = []
    try:
        error = _ERROR_MODEL.validate_json(response.content)
    except ValidationError:
        pass
    else:
        if error.message:
            candidates.append(error.message)

    if not candidates:
        try:
            problem = _PROBLEM_DETAILS.validate_json(response.content)
        except ValidationError:
            pass
        else:
            candidates.extend(
                message for messages in problem.errors.values() for message in messages
            )
            if not candidates and problem.title:
                candidates.append(problem.title)

    if not candidates:
        try:
            failures = _VALIDATION_FAILURES.validate_json(response.content)
        except ValidationError:
            pass
        else:
            candidates.extend(
                failure.error_message for failure in failures if failure.error_message
            )

    details: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in details:
            details.append(candidate)
        if len(details) == _MAX_ERROR_DETAILS:
            break
    return details


def _safe_error_detail(response: httpx.Response, *, api_key: str) -> str | None:
    detail = "; ".join(_parse_error_details(response))
    if not detail:
        return None
    detail = " ".join(detail.split())
    detail = "".join(character for character in detail if character.isprintable())
    if api_key:
        detail = detail.replace(api_key, "[redacted]")
    detail = _URL_PATTERN.sub("[URL]", detail)
    detail = _WINDOWS_PATH_PATTERN.sub("[path]", detail)
    detail = _UNIX_PATH_PATTERN.sub("[path]", detail)
    if len(detail) > _ERROR_DETAIL_LIMIT:
        return f"{detail[: _ERROR_DETAIL_LIMIT - 3].rstrip()}..."
    return detail or None


def response_error(
    response: httpx.Response,
    *,
    operation: str,
    api_key: str,
) -> ProwlarrResponseError:
    """Convert an unsuccessful HTTP response into a Prowlarr domain error."""
    return ProwlarrResponseError(
        f"Prowlarr {operation} failed with HTTP {response.status_code}",
        status_code=response.status_code,
        detail=_safe_error_detail(response, api_key=api_key),
    )
