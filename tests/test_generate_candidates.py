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

    def test_ossetian_split_stays_distinct_and_pending(self) -> None:
        iron = self.profiles["os"]
        generic = self.profiles["ira-x-ossetic"]
        self.assertEqual(["иронски"], iron["serbianCandidates"])
        self.assertEqual("Iron-Ossetisch", iron["preferredLabels"]["de"])
        self.assertEqual("iron1242", iron["glottolog"]["glottocode"])
        self.assertEqual("Q2585922", iron["wikidataQidCandidate"])
        self.assertEqual(["осетски"], generic["serbianCandidates"])
        self.assertEqual("Ossetian", generic["preferredLabels"]["en"])
        self.assertEqual("Q33968", generic["wikidataQidCandidate"])
        self.assertIsNone(generic["glottolog"])
        self.assertEqual([], generic["lineage"])
        for profile in [iron, generic]:
            self.assertIsNone(profile["approval"])
            self.assertIn("non-cldr-german-label", profile["reviewReasons"])
            self.assertEqual({"sr": [], "en": [], "de": []}, profile["aliasCandidates"])
        self.assertIn("private-use-code", generic["reviewReasons"])
        self.assertIn("wikidata-scope-review", generic["reviewReasons"])

    def test_inventory_is_complete(self) -> None:
        self.assertEqual(214, self.data["summary"]["tagProfiles"])
        self.assertEqual(311, self.data["summary"]["sourceRecords"])

    def test_macedonian_mapping_is_exact_and_trilingual(self) -> None:
        profile = self.profiles["mk"]
        self.assertEqual("mace1250", profile["glottolog"]["glottocode"])
        self.assertEqual("exact", profile["glottolog"]["relationship"])
        self.assertEqual("Macedonian", profile["preferredLabels"]["en"])
        self.assertEqual("македонски", profile["preferredLabels"]["sr"])
        self.assertEqual("Mazedonisch", profile["preferredLabels"]["de"])
        self.assertEqual([], profile["reviewReasons"])

    def test_macrolanguage_and_structured_claim_bridges_are_not_lost(self) -> None:
        estonian = self.profiles["et"]
        self.assertEqual("exact", estonian["glottolog"]["relationship"])
        self.assertEqual("esto1258", estonian["glottolog"]["glottocode"])
        self.assertEqual("Q9072", estonian["wikidataQidCandidate"])
        self.assertNotIn("no-exact-glottolog-alignment", estonian["reviewReasons"])

        digor = self.profiles["osd"]
        self.assertEqual("exact", digor["glottolog"]["relationship"])
        self.assertEqual("digo1242", digor["glottolog"]["glottocode"])
        self.assertEqual("Q3027861", digor["wikidataQidCandidate"])

        indic = self.profiles["inc"]
        self.assertEqual("exact", indic["glottolog"]["relationship"])
        self.assertEqual("indo1321", indic["glottolog"]["glottocode"])
        self.assertEqual("Q33577", indic["wikidataQidCandidate"])

    def test_exact_ietf_items_survive_without_a_coextensive_glottolog_node(self) -> None:
        self.assertEqual("Q9168", self.profiles["fa"]["wikidataQidCandidate"])
        self.assertEqual("Q749834", self.profiles["xsc"]["wikidataQidCandidate"])
        for tag, qid in (
            ("de-AT", "Q306626"),
            ("en-US", "Q7976"),
            ("oc-provenc", "Q241243"),
            ("sr-ekavsk", "Q2548798"),
            ("sr-ijekavsk", "Q1289605"),
        ):
            self.assertEqual(qid, self.profiles[tag]["wikidataQidCandidate"])

    def test_private_stage_is_never_silently_approved(self) -> None:
        profile = self.profiles["ae-x-old"]
        self.assertEqual("historical-stage", profile["kindCandidate"])
        self.assertEqual("broader", profile["glottolog"]["relationship"])
        self.assertIn("private-use-code", profile["reviewReasons"])
        self.assertIn("non-cldr-german-label", profile["reviewReasons"])

    def test_middle_high_german_uses_registered_code_without_alias(self) -> None:
        self.assertNotIn("de-x-middle", self.profiles)
        profile = self.profiles["gmh"]
        self.assertEqual("exact", profile["glottolog"]["relationship"])
        self.assertEqual("midd1343", profile["glottolog"]["glottocode"])
        self.assertNotIn("de-x-middle", repr(profile))

    def test_shughni_is_direct_evidence_and_its_ancestors_are_classification_only(self) -> None:
        profile = self.profiles["sgh"]
        self.assertEqual("exact", profile["glottolog"]["relationship"])
        self.assertEqual("shug1248", profile["glottolog"]["glottocode"])
        lineage = {node["name"]: node for node in profile["lineage"]}
        self.assertEqual("sgh", lineage["Shughni"]["canonicalCode"])
        self.assertTrue(lineage["Shughni-Yazgulami"]["canonicalCode"].startswith("und-x-glot-"))
        self.assertTrue(lineage["Shughnic"]["canonicalCode"].startswith("und-x-glot-"))

    def test_church_slavonic_stages_and_recensions_are_distinct(self) -> None:
        expected = {
            "cu-x-old": ("historical-stage", "cu", "Q35499"),
            "cu-x-church": ("historical-stage", "cu", None),
            "cu-x-rus": ("variety", "cu-x-church", None),
            "cu-x-srp": ("variety", "cu-x-church", "Q3507864"),
            "cu-x-bul": ("variety", "cu-x-church", None),
            "cu-Glag-x-hrv": ("variety", "cu-x-church", None),
        }
        for tag, (kind, parent, qid) in expected.items():
            profile = self.profiles[tag]
            self.assertEqual(kind, profile["kindCandidate"])
            self.assertEqual(parent, profile["parentCandidate"])
            self.assertEqual("broader", profile["glottolog"]["relationship"])
            self.assertEqual("chur1257", profile["glottolog"]["glottocode"])
            self.assertEqual(qid, profile["wikidataQidCandidate"])
            self.assertEqual("approved", profile["approval"]["status"])

        serbian_sources = self.profiles["cu-x-srp"]["serbianCandidates"]
        self.assertEqual(
            [
                "српскословенски",
                "српскословенски (српска редакција цсл. језика)",
            ],
            serbian_sources,
        )
        source_ids = self.profiles["cu-x-srp"]["sourceRecordIds"]
        self.assertEqual(3, len(source_ids))

    def test_cu_is_a_selectable_evidence_free_standards_umbrella(self) -> None:
        umbrella = next(
            row
            for row in self.data["ancestorCandidates"]
            if row["canonicalCodeCandidate"] == "cu"
        )
        self.assertTrue(umbrella["selectableCandidate"])
        self.assertEqual("language", umbrella["kindCandidate"])
        self.assertEqual("chur1257", umbrella["glottocode"])
        self.assertEqual("Q33251", umbrella["wikidataQidCandidate"])
        self.assertEqual("chu", umbrella["iso639"]["part3"])
        self.assertIn("ISO 639 umbrella", umbrella["preferredLabels"]["en"])
        self.assertEqual([], umbrella["reviewReasons"])
        self.assertNotIn("cu", self.profiles)

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

    def test_uncoded_ancestors_receive_deterministic_nonselectable_codes(self) -> None:
        ancestors = self.data["ancestorCandidates"]
        self.assertTrue(ancestors)
        self.assertTrue(all(row["canonicalCodeCandidate"] for row in ancestors))
        uncoded = next(row for row in ancestors if row["glottocode"] == "alba1268")
        self.assertEqual("und-x-glot-alba1268", uncoded["canonicalCodeCandidate"])
        reviewed = next(row for row in ancestors if row["glottocode"] == "east2269")
        self.assertEqual("zls-x-east", reviewed["canonicalCodeCandidate"])
        self.assertEqual(0, self.data["summary"]["ancestorExceptions"])

    def test_outputs_contain_no_dictionary_evidence(self) -> None:
        serialized = __import__("json").dumps(self.data, ensure_ascii=False)
        for forbidden in ("formCount", "entryCount", "coverage", "attested"):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
