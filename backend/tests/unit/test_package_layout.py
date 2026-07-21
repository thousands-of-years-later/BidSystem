"""Tests for the installable backend package layout."""

from unittest import TestCase

import bid_system


class PackageLayoutTests(TestCase):
    """Verify the backend package can be resolved from the configured src path."""

    def test_bid_system_package_is_importable(self) -> None:
        """The configured src layout exposes the backend package."""
        self.assertEqual(bid_system.__version__, "0.1.0")
