from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
from datetime import timedelta
from pathlib import Path

import click
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network
from testcontainers.core.wait_strategies import HttpWaitStrategy

from prowlarr_mcp.models import HealthResults

CONFIG_FIXTURE = Path(__file__).parent / "fixtures" / "prowlarr-config.xml"


def fixture_api_key() -> str:
    api_key = ET.parse(CONFIG_FIXTURE).getroot().findtext("ApiKey")
    if not api_key:
        raise RuntimeError("Prowlarr test config does not contain an API key")
    return api_key


def is_health_response(body: str) -> bool:
    try:
        return isinstance(json.loads(body), list)
    except json.JSONDecodeError:
        return False


async def get_health(*, image: str, network_name: str, api_key: str) -> HealthResults:
    environment = dict(os.environ)
    environment["PROWLARR_API_KEY"] = api_key
    transport = StdioTransport(
        command="docker",
        args=[
            "run",
            "--rm",
            "--interactive",
            "--network",
            network_name,
            "--env",
            "PROWLARR_API_KEY",
            "--env",
            "PROWLARR_URL=http://prowlarr:9696",
            image,
        ],
        env=environment,
        log_file=Path(os.devnull),
        keep_alive=False,
    )
    async with Client(transport, timeout=60, init_timeout=60) as client:
        result = await client.call_tool(
            "get_health", {}, timeout=60, raise_on_error=False
        )

    if result.is_error:
        raise RuntimeError("get_health returned an MCP tool error")
    if result.structured_content is None:
        raise RuntimeError("get_health did not return structured content")
    return HealthResults.model_validate(result.structured_content)


@click.command()
@click.option("--mcp-image", required=True, help="MCP image to test.")
@click.option("--prowlarr-image", required=True, help="Prowlarr image to test against.")
@click.option(
    "--startup-timeout",
    type=click.FloatRange(min=0, min_open=True),
    default=90.0,
    show_default=True,
)
def main(mcp_image: str, prowlarr_image: str, startup_timeout: float) -> None:
    """Run the MCP image against a fresh, real Prowlarr container."""
    api_key = fixture_api_key()
    wait_strategy = (
        HttpWaitStrategy(9696, "/api/v1/health")
        .with_header("X-Api-Key", api_key)
        .for_response_predicate(is_health_response)
        .with_startup_timeout(timedelta(seconds=startup_timeout))
        .with_poll_interval(0.5)
    )

    try:
        with tempfile.TemporaryDirectory(prefix="prowlarr-mcp-e2e-") as config:
            config_dir = Path(config)
            shutil.copyfile(CONFIG_FIXTURE, config_dir / "config.xml")

            with Network() as network:
                prowlarr = (
                    DockerContainer(prowlarr_image)
                    .with_network(network)
                    .with_network_aliases("prowlarr")
                    .with_volume_mapping(config_dir, "/config", mode="rw")
                    .with_exposed_ports(9696)
                    .with_env("PUID", str(os.getuid()))
                    .with_env("PGID", str(os.getgid()))
                    .with_env("TZ", "Etc/UTC")
                    .waiting_for(wait_strategy)
                )
                with prowlarr:
                    health = asyncio.run(
                        get_health(
                            image=mcp_image,
                            network_name=network.name,
                            api_key=api_key,
                        )
                    )

        if health.total != len(health.checks):
            raise RuntimeError("MCP health total does not match its check count")
        click.echo(health.model_dump_json(indent=2))
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc


if __name__ == "__main__":
    main()
