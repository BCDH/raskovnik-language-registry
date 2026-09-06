#!/usr/bin/env python3
"""Tests for the exception-only release gate."""

from __future__ import annotations

import importlib.util
import json
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
    def test_historical_blockers_remain_a_negative_fixture(self) -> None:
        pending = MODULE.pending_records(ROOT / "review/sessions/2026-09-06-packaging/blocked-review.tsv")
        self.assertGreater(len(pending), 0)
        with self.assertRaisesRegex(MODULE.EditorialGateError, f"total={len(pending)}"):
            MODULE.assert_release_ready(ROOT / "review/sessions/2026-09-06-packaging/blocked-review.tsv")

    def test_current_queue_exactly_reports_unapproved_candidates(self):
        candidates=json.loads((ROOT / "dist/registry-candidates.json").read_text())
        expected={(kind,row['id'] if kind=='tag-profile' else row['glottocode']) for kind,rows in [('tag-profile',candidates['profiles']),('ancestor',candidates['ancestorCandidates'])] for row in rows if row['reviewReasons'] and not row['approval']}
        pending=MODULE.pending_records(ROOT / "dist/editorial-review.tsv")
        self.assertEqual(expected,{(row['recordType'],row['id']) for row in pending})
        if expected:
            with self.assertRaises(MODULE.EditorialGateError):MODULE.assert_release_ready(ROOT / "dist/editorial-review.tsv")
        else:
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
