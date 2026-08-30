# prowlarr-mcp

An MCP server for [Prowlarr](https://github.com/Prowlarr/Prowlarr).

## Setup

```sh
cd prowlarr-mcp
uv sync
cp .env.example .env
```

Set `PROWLARR_API_KEY` in `.env`. The API key is available in Prowlarr under
Settings → General → Security.

Configuration:

| Variable | Default | Description |
| --- | --- | --- |
| `PROWLARR_URL` | `http://localhost:9696` | Prowlarr base URL, including any URL base path |
| `PROWLARR_API_KEY` | required | Prowlarr API key |
| `PROWLARR_TIMEOUT_SECONDS` | `60` | HTTP timeout, greater than 0 and at most 300 seconds |
| `PROWLARR_MAX_RESULTS` | `100` | Hard upper bound accepted by `limit` |

## Run

```sh
uv run prowlarr-mcp
```

Example Codex/OpenCode-style stdio configuration:

```json
{
  "command": "uv",
  "args": [
    "--directory",
    "/path/to/prowlarr-mcp",
    "run",
    "prowlarr-mcp"
  ]
}
```

## Tools

`list_indexers` lists configured indexers and their safe, search-relevant
capabilities. It omits disabled indexers by default; pass `enabled_only=false`
to include them. Each result includes supported search types and category IDs,
without provider configuration fields or credentials.

`list_categories` returns Prowlarr's hierarchical search category taxonomy.
Use these category IDs with `search_releases`. Category ID `0` is valid in
Prowlarr's taxonomy and is accepted by the search tool.

`list_download_clients` lists configured download clients and omits disabled
clients by default. It returns only submission-relevant fields and numeric
category IDs; provider configuration, client category names, hosts, and
credentials are excluded.

`grab_release` submits a release returned by `search_releases` to a configured
download client. Pass the release's `indexer_id` and `guid`, plus an optional
`download_client_id` from `list_download_clients`. Omitting the client ID lets
Prowlarr select its configured default. Search results are cached by Prowlarr
for about 30 minutes; search again if submission reports that the release has
expired from the cache.

`search_releases` accepts:

- `query`: text query; an empty string requests recent releases.
- `search_type`: `search`, `tvsearch`, `movie`, `music`, or `book`.
- `indexer_ids`: optional Prowlarr indexer IDs.
- `categories`: optional Newznab category IDs.
- `limit`: number of results, default 20 and capped by configuration.
- `offset`: non-negative result offset.

The response is intentionally smaller than Prowlarr's full `ReleaseResource`,
but retains `indexer_id` and `guid` for a future download-submission workflow.
Prowlarr may apply `limit` independently to several indexers, so the MCP server
also enforces it on the combined response. `truncated` means that the MCP server
discarded part of the response it received; it is not a `has_more` pagination
indicator and cannot prove whether Prowlarr has additional results.

## Error handling

For Prowlarr 4xx responses, the server reports bounded, sanitized details from
recognized JSON error formats. It ignores stack traces, diagnostic content,
trace IDs, URLs, filesystem paths, API keys, and unknown response shapes.
Authentication errors, non-JSON bodies, and 5xx responses use generic messages
with an HTTP status code.

## Roadmap

- [x] **v0.1:** Search releases through configured Prowlarr indexers.
- [x] **v0.2:** Discover search and download capabilities, and submit a
  selected release to a configured download client.
- [ ] Inspect Prowlarr health, indexer status, and search history.

## Testing with the MCP client

The repository includes a generic stdio client for launching the server and
calling one tool:

```sh
uv run src/prowlarr_mcp/scripts/mcp_client.py \
  --command "uv run prowlarr-mcp" \
  --method "search_releases" \
  --arguments '{"query": "yani neko"}'
```

Use `--cwd` when the server command must run from a different directory, and
`--timeout` to override the default 60-second tool-call timeout. The script
prints structured tool output as JSON and exits non-zero for invalid input,
connection failures, or MCP tool errors.

## Development

```sh
uv run ruff format --check .
uv run ruff check .
uv run pyrefly check
uv run python -m unittest discover -s tests
```
