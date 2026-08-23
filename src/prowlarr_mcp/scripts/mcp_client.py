from __future__ import annotations

import asyncio
import json
import os
import shlex
from pathlib import Path
from typing import TYPE_CHECKING

import click
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from mcp.shared.exceptions import McpError

if TYPE_CHECKING:
    from fastmcp.client.client import CallToolResult


def parse_command(value: str) -> tuple[str, list[str]]:
    parts = shlex.split(value)
    if not parts:
        raise ValueError("--command must not be empty")
    return parts[0], parts[1:]


def parse_arguments(value: str) -> dict[str, object]:
    try:
        arguments = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"--arguments is not valid JSON: {exc.msg}") from exc
    if not isinstance(arguments, dict):
        raise TypeError("--arguments must decode to a JSON object")
    return arguments


def print_result(result: CallToolResult) -> None:
    if result.structured_content is not None:
        payload: object = result.structured_content
    else:
        payload = [
            block.model_dump(mode="json", by_alias=True, exclude_none=True)
            for block in result.content
        ]
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))


async def call_tool(
    *,
    command: str,
    method: str,
    arguments: str,
    cwd: Path | None,
    timeout: float,
) -> int:
    executable, command_args = parse_command(command)
    parsed_arguments = parse_arguments(arguments)
    transport = StdioTransport(
        command=executable,
        args=command_args,
        cwd=str(cwd) if cwd is not None else None,
        log_file=Path(os.devnull),
        keep_alive=False,
    )
    async with Client(
        transport,
        timeout=timeout,
        init_timeout=timeout,
    ) as client:
        result = await client.call_tool(
            method,
            parsed_arguments,
            timeout=timeout,
            raise_on_error=False,
        )
    print_result(result)
    return 1 if result.is_error else 0


@click.command()
@click.option(
    "--command",
    required=True,
    help="Command used to launch the MCP server, parsed without a shell.",
)
@click.option("--method", required=True, help="MCP tool name to call.")
@click.option("--arguments", default="{}", help="Tool arguments as a JSON object.")
@click.option(
    "--cwd",
    type=click.Path(
        exists=True,
        file_okay=False,
        path_type=Path,
    ),
    help="Optional working directory for the MCP server process.",
)
@click.option(
    "--timeout",
    type=click.FloatRange(min=0, min_open=True),
    default=60.0,
    show_default=True,
    help="Tool-call timeout in seconds.",
)
def main(
    command: str,
    method: str,
    arguments: str,
    cwd: Path | None,
    timeout: float,
) -> None:
    """Call one tool on an MCP server launched over stdio."""
    try:
        exit_code = asyncio.run(
            call_tool(
                command=command,
                method=method,
                arguments=arguments,
                cwd=cwd,
                timeout=timeout,
            )
        )
    except (McpError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    if exit_code:
        raise click.exceptions.Exit(exit_code)


if __name__ == "__main__":
    main()
