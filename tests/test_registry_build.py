#!/usr/bin/env python3
"""Build, validation, and round-trip contracts for the effective registry."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from registry_build import (  # noqa: E402
    MANIFEST_NS,
    TEI_NS,
    RegistryBuildError,
    build_artifacts,
    load_json,
    load_sources,
    plan_payload_sha256,
    project_registry_core,
    qname,
    resolve_tags,
    validate_generated_manifest,
    validate_generated_registry,
    validate_production_plan_provenance,
    xml_bytes,
)
from registry_sources import XML_NS  # noqa: E402


class RegistryBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan_path = ROOT / "tests/fixtures/approved-registry-plan.json"
        cls.plan = load_json(cls.plan_path)
        cls.source_lock = load_json(ROOT / "upstream/sources.json")
        cls.publication = load_json(ROOT / "registry/source-publication-metadata.json")
        cls.sources = load_sources(cls.source_lock, cls.publication, ROOT)
        cls.registry, cls.manifest = build_artifacts(
            cls.plan, cls.source_lock, cls.publication, ROOT
        )

    def build(self, plan: dict[str, object]) -> tuple[bytes, bytes]:
        return build_artifacts(plan, self.source_lock, self.publication, ROOT)

    def assert_mirror_mutation_rejected(
        self, mutator: Callable[[ET.Element], None], message: str
    ) -> None:
        registry_root = ET.fromstring(self.registry)
        mutator(registry_root)
        registry = xml_bytes(registry_root)
        manifest_root = ET.fromstring(self.manifest)
        manifest_root.set("contentSha256", hashlib.sha256(registry).hexdigest())
        manifest = xml_bytes(manifest_root)
        validate_generated_registry(registry, self.plan)
        with self.assertRaisesRegex(RegistryBuildError, message):
            validate_generated_manifest(manifest, registry, self.plan, self.sources)

    def test_build_is_byte_deterministic_and_validated_natively(self) -> None:
        second_registry, second_manifest = self.build(copy.deepcopy(self.plan))
        self.assertEqual(self.registry, second_registry)
        self.assertEqual(self.manifest, second_manifest)
        validate_generated_registry(self.registry, self.plan)
        validate_generated_manifest(self.manifest, self.registry, self.plan, self.sources)

    def test_pinned_rng_schematron_and_manifest_rng_all_accept_fixture(self) -> None:
        with tempfile.TemporaryDirectory(prefix="registry-build-validation-") as directory:
            fixture_root = Path(directory)
            registry_path = fixture_root / "registry.xml"
            manifest_path = fixture_root / "manifest.xml"
            registry_path.write_bytes(self.registry)
            manifest_path.write_bytes(self.manifest)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/validate-registry.py"),
                    "--registry",
                    str(registry_path),
                    "--manifest",
                    str(manifest_path),
                    "--plan",
                    str(self.plan_path),
                ],
                text=True,
                capture_output=True,
            )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)
        self.assertIn("registry validation passed", result.stdout)

    def test_generated_xml_round_trips_the_complete_neutral_contract(self) -> None:
        projected = project_registry_core(self.registry, self.manifest)
        self.assertEqual(self.plan["registryVersion"], projected["registryVersion"])
        self.assertEqual(self.plan["releasedAt"], projected["releasedAt"])
        self.assertEqual(
            self.plan["displayClassificationId"], projected["displayClassificationId"]
        )
        for key in (
            "classifications",
            "catalogs",
            "compatibleDictionaries",
            "nodes",
            "tagProfiles",
        ):
            self.assertEqual(self.plan[key], projected[key], key)
        self.assertEqual(
            sorted(self.plan["sourceRecords"], key=lambda item: item["id"]),
            projected["sourceRecords"],
        )

    def test_fixture_covers_required_tree_and_resolution_shapes(self) -> None:
        root = ET.fromstring(self.registry)
        namespace = {"tei": TEI_NS, "xml": XML_NS}
        self.assertIsNotNone(root.find(".//tei:languageGrp[@ident='ae']", namespace))
        self.assertIsNotNone(root.find(".//tei:languageGrp[@ident='zls-x-east']", namespace))
        self.assertIsNotNone(root.find(".//tei:language[@ident='mk']", namespace))
        self.assertIsNotNone(
            root.find(
                ".//tei:languageGrp[@ident='sla']/tei:languageGrp/tei:languageGrp/tei:language[@ident='mk']",
                namespace,
            )
        )
        self.assertEqual(["sla"], resolve_tags(self.plan, "sla", "direct"))
        self.assertEqual(["mk", "sla"], resolve_tags(self.plan, "sla", "inclusive"))
        self.assertEqual([], resolve_tags(self.plan, "zls-x-east", "direct"))

    def test_wikidata_identifier_round_trips(self) -> None:
        projected = project_registry_core(self.registry, self.manifest)
        indo_european = next(node for node in projected["nodes"] if node["id"] == "ine")
        self.assertIn(
            {"type": "Wikidata", "value": "Q19860"},
            indo_european["identifiers"],
        )

    def test_wikidata_identifier_rejects_bad_duplicate_and_conflicting_qids(self) -> None:
        invalid = copy.deepcopy(self.plan)
        ine = next(node for node in invalid["nodes"] if node["id"] == "ine")
        next(item for item in ine["identifiers"] if item["type"] == "Wikidata")["value"] = "Q01"
        with self.assertRaisesRegex(RegistryBuildError, "invalid or duplicate exact Wikidata"):
            self.build(invalid)

        duplicate = copy.deepcopy(self.plan)
        sla = next(node for node in duplicate["nodes"] if node["id"] == "sla")
        sla["identifiers"].append({"type": "Wikidata", "value": "Q19860"})
        with self.assertRaisesRegex(RegistryBuildError, "invalid or duplicate exact Wikidata"):
            self.build(duplicate)

        conflict = copy.deepcopy(self.plan)
        ine = next(node for node in conflict["nodes"] if node["id"] == "ine")
        next(item for item in ine["identifiers"] if item["type"] == "Wikidata")["value"] = "Q16315466"
        with self.assertRaisesRegex(RegistryBuildError, "conflicting or unsupported Wikidata"):
            self.build(conflict)

    def test_pinned_semantic_wikidata_item_without_standard_claims_is_accepted(self) -> None:
        plan = copy.deepcopy(self.plan)
        stage = next(node for node in plan["nodes"] if node["id"] == "ae-x-old")
        stage["identifiers"].append({"type": "Wikidata", "value": "Q35499"})
        registry, _manifest = self.build(plan)
        root = ET.fromstring(registry)
        namespace = {"tei": TEI_NS}
        item = root.find(
            ".//tei:language[@ident='ae-x-old']/tei:ident[@type='Wikidata']",
            namespace,
        )
        self.assertIsNotNone(item)
        self.assertEqual("Q35499", item.text)

    def test_nonselectable_ancestor_may_use_english_only_labels(self) -> None:
        plan = copy.deepcopy(self.plan)
        ancestor = next(node for node in plan["nodes"] if node["id"] == "zls-x-east")
        ancestor["selectable"] = False
        for language in ("sr", "de"):
            ancestor["labels"][language] = None
            ancestor["labelSources"][language] = None
        registry, manifest = self.build(plan)
        projected = project_registry_core(registry, manifest)
        node = next(item for item in projected["nodes"] if item["id"] == "zls-x-east")
        self.assertEqual(
            {"sr": None, "en": "Eastern South Slavic", "de": None},
            node["labels"],
        )

        selectable = copy.deepcopy(plan)
        next(node for node in selectable["nodes"] if node["id"] == "zls-x-east")[
            "selectable"
        ] = True
        with self.assertRaisesRegex(RegistryBuildError, "labels.sr"):
            self.build(selectable)

    def test_mixed_case_ids_and_null_abbreviation_are_lossless(self) -> None:
        root = ET.fromstring(self.registry)
        namespace = {"tei": TEI_NS, "xml": XML_NS}
        self.assertIsNotNone(root.find(".//tei:ident[@xml:id='lang-de-AT']", namespace))
        self.assertIsNotNone(root.find(".//tei:note[@xml:id='profile-de-AT']", namespace))
        label_only = root.find(
            ".//tei:name[@xml:id='src-full-name-86c6cd356bba414d']", namespace
        )
        self.assertIsNotNone(label_only)
        self.assertEqual("label-only", label_only.get("subtype"))
        projected = project_registry_core(self.registry, self.manifest)
        record = next(
            item
            for item in projected["sourceRecords"]
            if item["id"] == "src-full-name-86c6cd356bba414d"
        )
        self.assertIsNone(record["abbreviation"])
        self.assertEqual("македонском", record["sourceLabel"])

    def test_all_classification_statuses_and_compatibility_hash_shape_are_preserved(self) -> None:
        projected = project_registry_core(self.registry, self.manifest)
        self.assertEqual(
            {"reviewed", "tentative", "disputed"},
            {node["classificationStatus"] for node in projected["nodes"]},
        )
        for dictionary in projected["compatibleDictionaries"]:
            self.assertRegex(dictionary["resourceHash"], r"^sha256:[0-9a-f]{64}$")

    def test_multiple_locations_share_one_setting_desc(self) -> None:
        plan = copy.deepcopy(self.plan)
        avestan = next(node for node in plan["nodes"] if node["id"] == "ae")
        second = copy.deepcopy(avestan["locations"][0])
        second["type"] = "historical"
        avestan["locations"].append(second)
        registry, _manifest = self.build(plan)
        root = ET.fromstring(registry)
        namespace = {"tei": TEI_NS}
        avestan_element = root.find(".//tei:languageGrp[@ident='ae']", namespace)
        self.assertEqual(1, len(avestan_element.findall("tei:settingDesc", namespace)))
        self.assertEqual(2, len(avestan_element.findall("tei:settingDesc/tei:place", namespace)))

    def test_profile_without_dictionary_source_records_builds_and_round_trips(self) -> None:
        plan = copy.deepcopy(self.plan)
        profile = next(item for item in plan["tagProfiles"] if item["id"] == "de-AT")
        profile["sourceRecordIds"] = []
        plan["sourceRecords"] = [
            record
            for record in plan["sourceRecords"]
            if record["mappedTagProfileId"] != "de-AT"
        ]
        registry, manifest = self.build(plan)
        projected = project_registry_core(registry, manifest)
        projected_profile = next(
            item for item in projected["tagProfiles"] if item["id"] == "de-AT"
        )
        self.assertEqual([], projected_profile["sourceRecordIds"])

        with tempfile.TemporaryDirectory(prefix="registry-empty-profile-") as directory:
            fixture_root = Path(directory)
            registry_path = fixture_root / "registry.xml"
            manifest_path = fixture_root / "manifest.xml"
            plan_path = fixture_root / "plan.json"
            registry_path.write_bytes(registry)
            manifest_path.write_bytes(manifest)
            plan_path.write_text(
                json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/validate-registry.py"),
                    "--registry",
                    str(registry_path),
                    "--manifest",
                    str(manifest_path),
                    "--plan",
                    str(plan_path),
                ],
                text=True,
                capture_output=True,
            )
        self.assertEqual(0, result.returncode, result.stderr or result.stdout)

    def test_publication_metadata_preserves_pinned_source_fields(self) -> None:
        sources = load_sources(self.source_lock, self.publication, ROOT)
        cldr = next(source for source in sources if source["id"] == "cldr")
        pinned_cldr = next(source for source in self.source_lock["sources"] if source["id"] == "cldr")
        self.assertEqual(pinned_cldr["title"], cldr["title"])
        self.assertEqual(pinned_cldr["files"], cldr["files"])

    def test_publication_metadata_rejects_duplicate_source_ids(self) -> None:
        duplicate = copy.deepcopy(self.publication)
        duplicate["upstreamSources"].append(copy.deepcopy(duplicate["upstreamSources"][0]))
        with self.assertRaisesRegex(RegistryBuildError, "duplicate upstream publication source ID"):
            load_sources(self.source_lock, duplicate, ROOT)

        duplicate_manifest_id = copy.deepcopy(self.publication)
        duplicate_manifest_id["upstreamSources"][1]["manifestId"] = (
            duplicate_manifest_id["upstreamSources"][0]["manifestId"]
        )
        with self.assertRaisesRegex(RegistryBuildError, "source manifest IDs must be unique"):
            load_sources(self.source_lock, duplicate_manifest_id, ROOT)

    def test_publication_metadata_rejects_unexpected_fields(self) -> None:
        unexpected = copy.deepcopy(self.publication)
        unexpected["upstreamSources"][0]["notes"] = "not allowlisted"
        with self.assertRaisesRegex(RegistryBuildError, "unexpected=.*notes"):
            load_sources(self.source_lock, unexpected, ROOT)

    def test_publication_metadata_cannot_counterfeit_pinned_title(self) -> None:
        counterfeit = copy.deepcopy(self.publication)
        counterfeit["upstreamSources"][0]["title"] = "Counterfeit source title"
        with self.assertRaisesRegex(RegistryBuildError, "unexpected=.*title"):
            load_sources(self.source_lock, counterfeit, ROOT)

    def test_plan_rejects_dictionary_evidence_and_bad_compatibility_hash(self) -> None:
        evidence_plan = copy.deepcopy(self.plan)
        evidence_plan["coverage"] = {}
        with self.assertRaisesRegex(RegistryBuildError, "dictionary-evidence"):
            self.build(evidence_plan)
        hash_plan = copy.deepcopy(self.plan)
        hash_plan["compatibleDictionaries"][0]["resourceHash"] = "a" * 64
        with self.assertRaisesRegex(RegistryBuildError, "sha256:<64"):
            self.build(hash_plan)

    def test_production_path_rejects_fixture_or_stale_approval(self) -> None:
        with self.assertRaisesRegex(RegistryBuildError, "release-approved plan"):
            validate_production_plan_provenance(self.plan, ROOT)
        stale = copy.deepcopy(self.plan)
        stale["approval"] = {
            "mode": "release",
            "reviewedBy": "fixture-reviewer",
            "reviewedOn": "2026-08-31",
            "candidatesSha256": "0" * 64,
            "editorialReportSha256": "0" * 64,
            "overridesSha256": "0" * 64,
            "planPayloadSha256": "",
        }
        stale["approval"]["planPayloadSha256"] = plan_payload_sha256(stale)
        with self.assertRaisesRegex(RegistryBuildError, "approval is stale"):
            validate_production_plan_provenance(stale, ROOT)

    def test_release_approval_binds_every_output_driving_plan_field(self) -> None:
        release = copy.deepcopy(self.plan)
        release["approval"] = {
            "mode": "release",
            "reviewedBy": "fixture-reviewer",
            "reviewedOn": "2026-08-31",
            "candidatesSha256": "0" * 64,
            "editorialReportSha256": "0" * 64,
            "overridesSha256": "0" * 64,
            "planPayloadSha256": "",
        }
        release["approval"]["planPayloadSha256"] = plan_payload_sha256(release)

        extra_node = copy.deepcopy(release)
        extra_node["nodes"].append(
            {
                **copy.deepcopy(extra_node["nodes"][-1]),
                "id": "x-unreviewed-extra",
                "parentId": None,
                "directTagProfileIds": [],
                "identifiers": [],
            }
        )

        changed_profile = copy.deepcopy(release)
        node = next(item for item in changed_profile["nodes"] if item["id"] == "mk")
        profile = next(item for item in changed_profile["tagProfiles"] if item["id"] == "mk")
        node["kind"] = "variety"
        node["labels"]["en"] = "Rewritten Macedonian"
        profile["labels"]["en"] = "Rewritten Macedonian"

        changed_lineage = copy.deepcopy(release)
        node = next(item for item in changed_lineage["nodes"] if item["id"] == "zls-x-east")
        node["parentId"] = "sla"
        node["selectable"] = False

        changed_alternate = copy.deepcopy(release)
        node = next(item for item in changed_alternate["nodes"] if item["id"] == "mk")
        node["alternateLineages"][0]["pathNodeIds"] = ["ine", "sla", "mk"]

        mutations = {
            "extra node": extra_node,
            "profile labels and kind": changed_profile,
            "parentage and selectability": changed_lineage,
            "alternate lineage": changed_alternate,
        }
        for label, mutated in mutations.items():
            with self.subTest(label), self.assertRaisesRegex(
                RegistryBuildError, "effective plan payload"
            ):
                validate_production_plan_provenance(mutated, ROOT)

    def test_plan_rejects_unregistered_tag_and_incomplete_exact_iso_inventory(self) -> None:
        unregistered = copy.deepcopy(self.plan)
        node = next(item for item in unregistered["nodes"] if item["id"] == "de-AT")
        node["id"] = "de-XY"
        node["directTagProfileIds"] = ["de-XY"]
        profile = next(item for item in unregistered["tagProfiles"] if item["id"] == "de-AT")
        profile["id"] = profile["tag"] = profile["displayNodeId"] = "de-XY"
        record = next(
            item for item in unregistered["sourceRecords"] if item["mappedTagProfileId"] == "de-AT"
        )
        record["mappedTagProfileId"] = "de-XY"
        with self.assertRaisesRegex(RegistryBuildError, "unavailable region subtag"):
            self.build(unregistered)

        incomplete_iso = copy.deepcopy(self.plan)
        macedonian = next(item for item in incomplete_iso["nodes"] if item["id"] == "mk")
        macedonian["identifiers"] = [
            item for item in macedonian["identifiers"] if item["type"] != "ISO639-2B"
        ]
        with self.assertRaisesRegex(RegistryBuildError, "incomplete exact ISO inventory"):
            self.build(incomplete_iso)

    def test_native_validator_rejects_broken_profile_catalog_link(self) -> None:
        root = ET.fromstring(self.registry)
        source_label = next(
            element
            for element in root.iter(qname(TEI_NS, "name"))
            if element.get("type") == "sourceLabel"
        )
        source_label.set("ana", source_label.get("ana", "").replace("#catalog-isj-persj", "#catalog-missing"))
        with self.assertRaisesRegex(RegistryBuildError, "link one profile and one catalog"):
            validate_generated_registry(xml_bytes(root), self.plan)

    def test_native_validator_rejects_all_source_desc_manifest_drift(self) -> None:
        def source_label(root: ET.Element) -> None:
            bibl = root.find(f".//{qname(TEI_NS, 'bibl')}[@type='registrySource']")
            assert bibl is not None
            bibl.text = "Counterfeit source title"

        def classification_label(root: ET.Element) -> None:
            bibl = root.find(f".//{qname(TEI_NS, 'bibl')}[@type='classification']")
            assert bibl is not None
            title = next(
                item
                for item in bibl.findall(qname(TEI_NS, "title"))
                if item.get(qname(XML_NS, "lang")) == "en"
            )
            title.text = "Counterfeit classification"

        def classification_version(root: ET.Element) -> None:
            version = root.find(
                f".//{qname(TEI_NS, 'bibl')}[@type='classification']/{qname(TEI_NS, 'idno')}[@type='version']"
            )
            assert version is not None
            version.text = "counterfeit-version"

        def classification_source(root: ET.Element) -> None:
            reference = root.find(
                f".//{qname(TEI_NS, 'bibl')}[@type='classification']/{qname(TEI_NS, 'ref')}[@type='classificationSource']"
            )
            assert reference is not None
            reference.set("target", "#src-cldr-48-2")
            reference.text = "src-cldr-48-2"

        def catalog_dictionary(root: ET.Element) -> None:
            identifier = root.find(
                f".//{qname(TEI_NS, 'bibl')}[@type='dictionaryLanguageCatalog']/{qname(TEI_NS, 'idno')}[@type='dictionaryId']"
            )
            assert identifier is not None
            identifier.text = "COUNTERFEIT.DICT"

        def catalog_source(root: ET.Element) -> None:
            reference = root.find(
                f".//{qname(TEI_NS, 'bibl')}[@type='dictionaryLanguageCatalog']/{qname(TEI_NS, 'ref')}[@type='catalogSource']"
            )
            assert reference is not None
            reference.set("target", "#src-glottolog-5-3")
            reference.text = "src-glottolog-5-3"

        cases = {
            "source label": (source_label, "source mirror differs"),
            "classification label": (classification_label, "classification mirror differs"),
            "classification version": (classification_version, "classification mirror differs"),
            "classification source": (classification_source, "classification mirror differs"),
            "catalog dictionary": (catalog_dictionary, "catalog mirror differs"),
            "catalog source": (catalog_source, "catalog mirror differs"),
        }
        for label, (mutator, message) in cases.items():
            with self.subTest(label):
                self.assert_mirror_mutation_rejected(mutator, message)

    def test_native_validator_rejects_manifest_semantics_that_differ_from_plan(self) -> None:
        manifest_root = ET.fromstring(self.manifest)
        label = manifest_root.find(
            f"./{qname(MANIFEST_NS, 'classifications')}/{qname(MANIFEST_NS, 'classification')}/{qname(MANIFEST_NS, 'label')}"
        )
        assert label is not None
        label.text = "Counterfeit manifest classification"
        with self.assertRaisesRegex(RegistryBuildError, "classifications differ from the approved plan"):
            validate_generated_manifest(
                xml_bytes(manifest_root), self.registry, self.plan, self.sources
            )

    def test_native_validator_rejects_counterfeit_source_when_both_mirrors_agree(self) -> None:
        registry_root = ET.fromstring(self.registry)
        source_bibl = registry_root.find(
            f".//{qname(TEI_NS, 'bibl')}[@type='registrySource']"
        )
        assert source_bibl is not None
        source_id = source_bibl.get(qname(XML_NS, "id"))

        manifest_root = ET.fromstring(self.manifest)
        source = next(
            item
            for item in manifest_root.findall(
                f"./{qname(MANIFEST_NS, 'sources')}/{qname(MANIFEST_NS, 'source')}"
            )
            if item.get(qname(XML_NS, "id")) == source_id
        )
        source.set("title", "Counterfeit source title")
        source_bibl.text = ". ".join(
            value for value in (source.get("title"), source.get("version")) if value
        )
        registry = xml_bytes(registry_root)
        manifest_root.set("contentSha256", hashlib.sha256(registry).hexdigest())
        with self.assertRaisesRegex(RegistryBuildError, "pinned source contract"):
            validate_generated_manifest(
                xml_bytes(manifest_root), registry, self.plan, self.sources
            )

    def test_fixture_contains_no_dictionary_evidence_or_aggregate_fields(self) -> None:
        serialized = json.dumps(
            project_registry_core(self.registry, self.manifest), ensure_ascii=False
        )
        for forbidden in (
            "hasDirectEvidence",
            "hasInclusiveEvidence",
            "formCount",
            "entryCount",
            "coverage",
            "attested",
            "occurrences",
        ):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
