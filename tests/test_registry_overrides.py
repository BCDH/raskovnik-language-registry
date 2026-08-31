#!/usr/bin/env python3
"""Tests for the explicit editorial approval boundary."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from registry_overrides import RegistryOverrideError, parse_overrides  # noqa: E402


class RegistryOverridesTest(unittest.TestCase):
    def test_reviewed_design_decisions_are_explicit(self) -> None:
        overrides = parse_overrides(ROOT / "registry/raskovnik-overrides.xml")
        self.assertEqual("2026.8.31-1", overrides.version)
        self.assertEqual("slav1255", overrides.nodes["sla"].glottocode)
        self.assertEqual("family", overrides.nodes["sla"].kind)
        self.assertEqual("Altavestisch", overrides.nodes["ae-x-old"].names["de"].value)
        self.assertEqual("sla", overrides.nodes["zls-x-east"].parent)

    def test_pending_decision_fails_the_release_gate(self) -> None:
        source = (ROOT / "registry/raskovnik-overrides.xml").read_text(encoding="utf-8")
        pending = source.replace('reviewStatus="approved"', 'reviewStatus="pending"', 1)
        with tempfile.TemporaryDirectory(prefix="registry-overrides-") as directory:
            path = Path(directory) / "pending.xml"
            path.write_text(pending, encoding="utf-8")
            with self.assertRaisesRegex(RegistryOverrideError, "pending override blocks release"):
                parse_overrides(path)


if __name__ == "__main__":
    unittest.main()
