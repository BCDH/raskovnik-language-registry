#!/usr/bin/env python3
"""Unit tests for pinned registry-source parsing."""

from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from registry_sources import (  # noqa: E402
    canonical_language_tag,
    glottolog_lineage,
    parse_cldr_german,
    parse_effective_persj_catalog,
    parse_glottolog,
    parse_iana_registry,
    parse_iso639_3,
    parse_wikidata_evidence,
    RegistrySourceError,
    stable_source_id,
    technical_id,
    validate_registered_tag,
)


class RegistrySourcesTest(unittest.TestCase):
    def test_active_persj_keeps_serbo_croatian_separate_from_serbian(self) -> None:
        import json

        manifest = json.loads((ROOT / "upstream/sources.json").read_text())
        source = next(item for item in manifest["sources"] if item["id"] == "persj-language-catalog")
        profiles, _ = parse_effective_persj_catalog(ROOT / source["files"][0]["path"])
        self.assertEqual({"српско-хрватски"}, set(profiles["sh"].serbian_names))
        self.assertNotIn("српско-хрватски", profiles["sr"].serbian_names)
        self.assertEqual({"с.-х."}, {record.label for record in profiles["sh"].source_records})
        self.assertEqual("registered", profiles["sh"].status)

    def test_source_ids_do_not_depend_on_input_order(self) -> None:
        self.assertEqual(
            stable_source_id("base", "мак."),
            stable_source_id("base", "мак."),
        )
        self.assertNotEqual(
            stable_source_id("base", "мак."),
            stable_source_id("extension", "мак."),
        )

    def test_public_persj_snapshot_contains_mappings_but_no_counts(self) -> None:
        path = ROOT / "upstream/persj/6101bcb/effective-language-catalog.xml"
        profiles, source_records = parse_effective_persj_catalog(path)
        self.assertEqual(214, len(profiles))
        self.assertEqual(311, len(source_records))
        self.assertEqual(72, sum(profile.status == "private" for profile in profiles.values()))
        self.assertIn("ae-x-old", profiles)
        self.assertIn("ira-x-middle", profiles)
        self.assertIn("lt-x-old", profiles)
        self.assertEqual(
            {"староавестијски"}, set(profiles["ae-x-old"].serbian_names)
        )
        self.assertEqual({"старословенски"}, set(profiles["cu-x-old"].serbian_names))
        self.assertEqual({"црквенословенски"}, set(profiles["cu-x-church"].serbian_names))
        self.assertIn("cu-x-bul", profiles)
        self.assertEqual(3, len(profiles["cu-x-srp"].source_records))
        raw = path.read_text(encoding="utf-8")
        self.assertNotIn("occurrences", raw)
        self.assertNotIn("count", raw.casefold())

    def test_iana_validates_public_and_registered_base_private_tags(self) -> None:
        file_date, records = parse_iana_registry(
            ROOT / "upstream/iana/2026-08-08/language-subtag-registry"
        )
        self.assertEqual("2026-08-08", file_date)
        for tag in ("mk", "sr-ekavsk", "oc-provenc", "cu-Glag-x-hrv", "ae-x-old"):
            validate_registered_tag(tag, records)

    def test_iso_crosswalk_and_glottolog_lineage(self) -> None:
        _by_id, by_part1, _by_part2 = parse_iso639_3(
            ROOT / "upstream/iso-639-3/2026-07-22/iso-639-3.tab"
        )
        self.assertEqual("mkd", by_part1["mk"].identifier)
        glottolog, by_iso = parse_glottolog(
            ROOT / "upstream/glottolog/5.3/languoid.csv"
        )
        self.assertEqual("mace1250", by_iso["mkd"].glottocode)
        lineage = glottolog_lineage(by_iso["mkd"], glottolog)
        self.assertEqual("Indo-European", lineage[0].name)
        self.assertEqual("Macedonian", lineage[-1].name)

    def test_cldr_supplies_german_language_names(self) -> None:
        languages, territories, _variants = parse_cldr_german(
            ROOT / "upstream/cldr/48.2/de.xml"
        )
        self.assertEqual("Mazedonisch", languages["mk"])
        self.assertEqual("Österreich", territories["AT"])

    def test_canonical_tags(self) -> None:
        self.assertEqual("cu-Glag-x-hrv", canonical_language_tag("cu-Glag-x-hrv"))
        self.assertEqual("sr-x-zeta-sjen", canonical_language_tag("sr-x-zeta-sjen"))
        self.assertEqual("lang-de-AT", technical_id("de-AT"))
        self.assertEqual("lang-cu-Glag-x-hrv", technical_id("cu-Glag-x-hrv"))

    def test_wikidata_snapshot_rejects_category_entities(self) -> None:
        payload = {
            "schemaVersion": "raskovnik-wikidata-language-evidence-v1",
            "items": [
                {
                    "qid": "Q123",
                    "lastRevisionId": 1,
                    "lastRevisionTimestamp": "2026-09-01T00:00:00Z",
                    "labels": {"sr": None, "en": "Category", "de": None},
                    "descriptions": {"sr": None, "en": None, "de": None},
                    "claims": {"P1394": [], "P220": [], "P31": ["Q4167836"], "P279": []},
                    "sitelinks": {"sr": None, "en": None, "de": None},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wikidata.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(RegistrySourceError, "non-semantic"):
                parse_wikidata_evidence(path)

    def test_old_czech_wikidata_claim_is_pinned(self) -> None:
        items, by_glottocode, _by_iso, by_ietf = parse_wikidata_evidence(
            ROOT / "upstream/wikidata/2026-09-01/language-items.json"
        )
        self.assertEqual("Q16315466", by_glottocode["oldc1253"].qid)
        self.assertEqual("Alttschechisch", items["Q16315466"].labels["de"])
        self.assertEqual("Q9072", by_ietf["et"].qid)


if __name__ == "__main__":
    unittest.main()
