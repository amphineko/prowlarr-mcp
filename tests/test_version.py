from __future__ import annotations

import unittest
from importlib.metadata import version

from prowlarr_mcp import __version__


class VersionTest(unittest.TestCase):
    def test_runtime_version_matches_package_metadata(self) -> None:
        self.assertEqual(__version__, version("prowlarr-mcp"))
