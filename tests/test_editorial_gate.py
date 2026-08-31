#!/usr/bin/env python3
"""Tests for the exception-only release gate."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "check_editorial_gate", ROOT / "scripts/check-editorial-gate.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class EditorialGateTest(unittest.TestCase):
    def test_current_queue_is_explicitly_blocking(self) -> None:
        pending = MODULE.pending_records(ROOT / "dist/editorial-review.tsv")
        self.assertEqual(285, len(pending))
        with self.assertRaisesRegex(MODULE.EditorialGateError, "total=285"):
            MODULE.assert_release_ready(ROOT / "dist/editorial-review.tsv")

    def test_header_only_report_passes(self) -> None:
        source = (ROOT / "dist/editorial-review.tsv").read_text(encoding="utf-8")
        header = source.splitlines()[0] + "\n"
        with tempfile.TemporaryDirectory(prefix="registry-editorial-gate-") as directory:
            path = Path(directory) / "review.tsv"
            path.write_text(header, encoding="utf-8")
            MODULE.assert_release_ready(path)


if __name__ == "__main__":
    unittest.main()
