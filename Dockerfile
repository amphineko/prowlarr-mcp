# syntax=docker/dockerfile:1@sha256:ecfaec9ed6d810b56388c508f4121597bfbba70d41a6dfeee4d8cad5f295fc32

FROM python:3.12-slim-bookworm@sha256:0f5b26b9518d002b6173fd61daad821fa340635ebfec5bba471013f9ca114579 AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY --from=astral/uv:0.11.3@sha256:90bbb3c16635e9627f49eec6539f956d70746c409209041800a0280b93152823 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --locked --no-dev --no-editable


FROM python:3.12-slim-bookworm@sha256:0f5b26b9518d002b6173fd61daad821fa340635ebfec5bba471013f9ca114579 AS runtime

LABEL org.opencontainers.image.source="https://github.com/amphineko/prowlarr-mcp" \
      org.opencontainers.image.description="An MCP server for Prowlarr"

ENV HOME=/tmp \
    PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system --gid 10001 prowlarr-mcp \
    && useradd --system --uid 10001 --gid prowlarr-mcp \
        --home-dir /nonexistent --shell /usr/sbin/nologin prowlarr-mcp

WORKDIR /app

COPY --from=builder --chown=10001:10001 /app/.venv /app/.venv

USER 10001:10001

ENTRYPOINT ["prowlarr-mcp"]
