from __future__ import annotations

import shlex
import subprocess
import sys
import unittest
from pathlib import Path

from click.testing import CliRunner

from prowlarr_mcp.scripts.mcp_client import main, parse_arguments, parse_command

PROJECT_ROOT = Path(__file__).parent.parent
MCP_CLIENT = PROJECT_ROOT / "src" / "prowlarr_mcp" / "scripts" / "mcp_client.py"


class McpClientScriptTest(unittest.TestCase):
    def test_parse_command_preserves_quoted_arguments(self) -> None:
        command, arguments = parse_command('uv run server --name "two words"')

        self.assertEqual(command, "uv")
        self.assertEqual(arguments, ["run", "server", "--name", "two words"])

    def test_parse_arguments_requires_json_object(self) -> None:
        self.assertEqual(
            parse_arguments('{"query": "yani neko"}'), {"query": "yani neko"}
        )

        with self.assertRaisesRegex(TypeError, "JSON object"):
            parse_arguments('["not", "an", "object"]')

    def test_parse_arguments_reports_invalid_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "not valid JSON"):
            parse_arguments("{")

    def test_click_rejects_non_positive_timeout(self) -> None:
        result = CliRunner().invoke(
            main,
            [
                "--command",
                "uv run prowlarr-mcp",
                "--method",
                "search_releases",
                "--timeout",
                "0",
            ],
        )

        self.assertEqual(result.exit_code, 2)
        self.assertIn("x>0", result.output)

    def test_server_startup_failure_is_a_clean_click_error(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(MCP_CLIENT),
                "--command",
                shlex.join([sys.executable, "-c", "pass"]),
                "--method",
                "search_releases",
                "--timeout",
                "1",
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1)
        self.assertIn("Error:", output)
        self.assertNotIn("Traceback", output)
        self.assertNotIn("/home/", output)

    def test_client_timeout_is_a_clean_click_error(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(MCP_CLIENT),
                "--command",
                shlex.join([sys.executable, "-c", "import time; time.sleep(10)"]),
                "--method",
                "search_releases",
                "--timeout",
                "0.2",
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1)
        self.assertIn("Error:", output)
        self.assertNotIn("Traceback", output)
        self.assertNotIn("/home/", output)
