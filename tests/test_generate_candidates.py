#!/usr/bin/env python3
"""Contract tests for standards-derived registry candidates."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "generate_candidates", ROOT / "scripts/generate-candidates.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class GenerateCandidatesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = MODULE.build_candidates()
        cls.profiles = {row["id"]: row for row in cls.data["profiles"]}

    def test_inventory_is_complete(self) -> None:
        self.assertEqual(212, self.data["summary"]["tagProfiles"])
        self.assertEqual(310, self.data["summary"]["sourceRecords"])

    def test_macedonian_mapping_is_exact_and_trilingual(self) -> None:
        profile = self.profiles["mk"]
        self.assertEqual("mace1250", profile["glottolog"]["glottocode"])
        self.assertEqual("exact", profile["glottolog"]["relationship"])
        self.assertEqual("Macedonian", profile["preferredLabels"]["en"])
        self.assertEqual("македонски", profile["preferredLabels"]["sr"])
        self.assertEqual("Mazedonisch", profile["preferredLabels"]["de"])
        self.assertEqual([], profile["reviewReasons"])

    def test_private_stage_is_never_silently_approved(self) -> None:
        profile = self.profiles["ae-x-old"]
        self.assertEqual("historical-stage", profile["kindCandidate"])
        self.assertEqual("broader", profile["glottolog"]["relationship"])
        self.assertIn("private-use-code", profile["reviewReasons"])
        self.assertIn("non-cldr-german-label", profile["reviewReasons"])

    def test_slavic_collection_is_one_candidate_profile(self) -> None:
        profile = self.profiles["sla"]
        self.assertEqual("family", profile["kindCandidate"])
        self.assertEqual("slav1255", profile["glottolog"]["glottocode"])
        self.assertEqual("exact", profile["glottolog"]["relationship"])
        self.assertIn("collection-classification", profile["reviewReasons"])
        self.assertEqual("approved", profile["approval"]["status"])

    def test_reviewed_uncoded_ancestor_gets_its_canonical_code(self) -> None:
        profile = self.profiles["mk"]
        eastern_south_slavic = next(
            node for node in profile["lineage"] if node["glottocode"] == "east2269"
        )
        self.assertEqual("zls-x-east", eastern_south_slavic["canonicalCode"])

    def test_outputs_contain_no_dictionary_evidence(self) -> None:
        serialized = __import__("json").dumps(self.data, ensure_ascii=False)
        for forbidden in ("formCount", "entryCount", "coverage", "attested"):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
