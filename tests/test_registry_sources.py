#!/usr/bin/env python3
"""Unit tests for pinned registry-source parsing."""

from __future__ import annotations

import sys
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
    stable_source_id,
    technical_id,
    validate_registered_tag,
)


class RegistrySourcesTest(unittest.TestCase):
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
        path = ROOT / "upstream/persj/670dac4/effective-language-catalog.xml"
        profiles, source_records = parse_effective_persj_catalog(path)
        self.assertEqual(212, len(profiles))
        self.assertEqual(310, len(source_records))
        self.assertEqual(69, sum(profile.status == "private" for profile in profiles.values()))
        self.assertIn("ae-x-old", profiles)
        self.assertIn("ira-x-middle", profiles)
        self.assertIn("lt-x-old", profiles)
        self.assertEqual(
            {"староавестијски"}, set(profiles["ae-x-old"].serbian_names)
        )
        raw = path.read_text(encoding="utf-8")
        self.assertNotIn("occurrences", raw)
        self.assertNotIn("count", raw.casefold())

    def test_iana_validates_public_and_registered_base_private_tags(self) -> None:
        file_date, records = parse_iana_registry(
            ROOT / "upstream/iana/2026-08-08/language-subtag-registry"
        )
        self.assertEqual("2026-08-08", file_date)
        for tag in ("mk", "sr-ekavsk", "oc-provenc", "cu-Glag-x-hr", "ae-x-old"):
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
        self.assertEqual("cu-Glag-x-hr", canonical_language_tag("cu-Glag-x-hr"))
        self.assertEqual("sr-x-zeta-sjen", canonical_language_tag("sr-x-zeta-sjen"))
        self.assertEqual("lang-de-AT", technical_id("de-AT"))
        self.assertEqual("lang-cu-Glag-x-hr", technical_id("cu-Glag-x-hr"))


if __name__ == "__main__":
    unittest.main()
