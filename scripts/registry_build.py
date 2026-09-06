#!/usr/bin/env python3
"""Deterministic compiler and semantic validator for the effective registry."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET

from registry_sources import (
    XML_NS,
    RegistrySourceError,
    canonical_language_tag,
    normalized,
    parse_glottolog,
    parse_effective_persj_catalog,
    parse_iana_registry,
    parse_iso639_3,
    parse_wikidata_evidence,
    sha256,
    technical_id,
    validate_registered_tag,
)


TEI_NS = "http://www.tei-c.org/ns/1.0"
MANIFEST_NS = "https://raskovnik.org/ns/language-registry/manifest"
PLAN_SCHEMA = "raskovnik-effective-registry-plan-v1"
PUBLICATION_SCHEMA = "raskovnik-registry-source-publication-metadata-v1"
SOURCE_LOCK_SCHEMA = "raskovnik-language-registry-sources-v1"
LEX0_VERSION = "0.9.6-dev"
LEX0_REVISION = "f6d51f29d1d2227c012dafcef20bec0708938505"
LEX0_SHA256 = "5ff670bcbc608f2c26af304860a241a56e9b15fdf9e3e37361e504d1edc519ed"
NODE_KINDS = frozenset(
    {
        "family",
        "language",
        "variety",
        "historical-stage",
        "reconstructed-language",
        "collective",
    }
)
CLASSIFICATION_STATUSES = frozenset({"reviewed", "tentative", "disputed"})
LOCATION_TYPES = frozenset({"representative", "historical", "editorial"})
SOURCE_RECORD_KINDS = frozenset(
    {"language-label", "compound-language-label"}
)
EXTERNAL_IDENTIFIER_TYPES = frozenset(
    {
        "Glottolog",
        "ISO639-1",
        "ISO639-2B",
        "ISO639-2T",
        "ISO639-3",
        "ISO639-5",
        "Wikidata",
    }
)
LANGUAGES = ("sr", "en", "de")
FORBIDDEN_PLAN_KEYS = frozenset(
    {
        "attested",
        "coverage",
        "entryCount",
        "formCount",
        "hasDirectEvidence",
        "hasInclusiveEvidence",
        "occurrences",
    }
)
SHA256_RE = re.compile(r"[0-9a-f]{64}")
XML_ID_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")
QID_RE = re.compile(r"Q[1-9][0-9]*")

ET.register_namespace("", TEI_NS)
ET.register_namespace("m", MANIFEST_NS)


class RegistryBuildError(RuntimeError):
    """Raised when a build input or generated registry violates its contract."""


def qname(namespace: str, local_name: str) -> str:
    return f"{{{namespace}}}{local_name}"


def _reject_duplicate_keys(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise RegistryBuildError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except RegistryBuildError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RegistryBuildError(f"cannot read JSON input {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RegistryBuildError(f"JSON root must be an object: {path}")
    return value


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def plan_payload_sha256(plan: dict[str, Any]) -> str:
    """Hash every output-driving plan field while excluding its approval envelope."""
    payload = {key: value for key, value in plan.items() if key != "approval"}
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _require_exact_keys(value: dict[str, Any], expected: set[str], context: str) -> None:
    actual = set(value)
    if actual != expected:
        raise RegistryBuildError(
            f"{context} keys differ: missing={sorted(expected - actual)!r} unexpected={sorted(actual - expected)!r}"
        )


def _require_string(value: Any, context: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not value or value != value.strip() or normalized(value) != value:
        raise RegistryBuildError(f"{context} must be a nonempty trimmed NFC string")
    return value


def _require_xml_id(value: Any, context: str) -> str:
    result = _require_string(value, context)
    assert isinstance(result, str)
    if XML_ID_RE.fullmatch(result) is None:
        raise RegistryBuildError(f"{context} must be a valid XML identifier")
    return result


def _require_boolean(value: Any, context: str) -> bool:
    if not isinstance(value, bool):
        raise RegistryBuildError(f"{context} must be boolean")
    return value


def _require_array(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise RegistryBuildError(f"{context} must be an array")
    return value


def _validate_labels(value: Any, context: str, *, nullable_values: bool = False) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RegistryBuildError(f"{context} must be an object")
    _require_exact_keys(value, set(LANGUAGES), context)
    for language in LANGUAGES:
        _require_string(value[language], f"{context}.{language}", nullable=nullable_values)
    return value


def _validate_aliases(value: Any, context: str) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        raise RegistryBuildError(f"{context} must be an object")
    _require_exact_keys(value, set(LANGUAGES), context)
    for language in LANGUAGES:
        aliases = _require_array(value[language], f"{context}.{language}")
        values: list[str] = []
        for index, alias in enumerate(aliases):
            alias_context = f"{context}.{language}[{index}]"
            if not isinstance(alias, dict):
                raise RegistryBuildError(f"{alias_context} must be an object")
            _require_exact_keys(alias, {"value", "sourceId"}, alias_context)
            alias_value = _require_string(alias["value"], f"{alias_context}.value")
            _require_xml_id(alias["sourceId"], f"{alias_context}.sourceId")
            assert isinstance(alias_value, str)
            values.append(alias_value)
        if values != sorted(set(values), key=lambda item: (item.casefold(), item)):
            raise RegistryBuildError(f"{context}.{language} must be unique and lexically sorted")
    return value


def _walk_keys(value: Any, context: str = "plan") -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_PLAN_KEYS.intersection(value)
        if forbidden:
            raise RegistryBuildError(f"{context} contains dictionary-evidence keys {sorted(forbidden)!r}")
        for key, child in value.items():
            _walk_keys(child, f"{context}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_keys(child, f"{context}[{index}]")


def name_id(code: str, language: str, role: str, index: int | None = None) -> str:
    suffix = f"-{index + 1}" if index is not None else ""
    return f"name-{code}-{language}-{role}{suffix}"


def validate_plan(
    plan: dict[str, Any],
    source_ids: set[str],
    standards: tuple[
        dict[Any, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ]
    | None = None,
    *, iso_scope_exceptions: frozenset = frozenset(),
) -> None:
    _walk_keys(plan)
    _require_exact_keys(
        plan,
        {
            "schemaVersion",
            "approval",
            "registryVersion",
            "releasedAt",
            "displayClassificationId",
            "classifications",
            "catalogs",
            "compatibleDictionaries",
            "nodes",
            "tagProfiles",
            "sourceRecords",
        },
        "plan",
    )
    if plan["schemaVersion"] != PLAN_SCHEMA:
        raise RegistryBuildError(f"unsupported plan schema {plan['schemaVersion']!r}")
    approval = plan["approval"]
    if not isinstance(approval, dict):
        raise RegistryBuildError("plan.approval must be an object")
    _require_exact_keys(
        approval,
        {
            "mode",
            "reviewedBy",
            "reviewedOn",
            "candidatesSha256",
            "editorialReportSha256",
            "overridesSha256",
            "planPayloadSha256",
        },
        "plan.approval",
    )
    if approval["mode"] not in {"fixture", "release"}:
        raise RegistryBuildError("plan.approval.mode must be fixture or release")
    _require_string(approval["reviewedBy"], "plan.approval.reviewedBy")
    reviewed_on = _require_string(approval["reviewedOn"], "plan.approval.reviewedOn")
    if not isinstance(reviewed_on, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", reviewed_on) is None:
        raise RegistryBuildError("plan.approval.reviewedOn must be an ISO date")
    for key in (
        "candidatesSha256",
        "editorialReportSha256",
        "overridesSha256",
        "planPayloadSha256",
    ):
        digest = approval[key]
        if approval["mode"] == "release":
            if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
                raise RegistryBuildError(f"release plan approval requires {key}")
        elif digest is not None:
            raise RegistryBuildError(f"fixture plan approval must leave {key} null")
    _require_string(plan["registryVersion"], "plan.registryVersion")
    released_at = _require_string(plan["releasedAt"], "plan.releasedAt")
    assert isinstance(released_at, str)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", released_at) is None:
        raise RegistryBuildError("plan.releasedAt must be a UTC second-resolution timestamp")

    classifications: dict[str, dict[str, Any]] = {}
    for index, classification in enumerate(_require_array(plan["classifications"], "plan.classifications")):
        context = f"plan.classifications[{index}]"
        if not isinstance(classification, dict):
            raise RegistryBuildError(f"{context} must be an object")
        _require_exact_keys(classification, {"id", "labels", "version", "sourceIds"}, context)
        identifier = _require_xml_id(classification["id"], f"{context}.id")
        if identifier in classifications:
            raise RegistryBuildError(f"duplicate classification {identifier!r}")
        _validate_labels(classification["labels"], f"{context}.labels")
        _require_string(classification["version"], f"{context}.version", nullable=True)
        references = _require_array(classification["sourceIds"], f"{context}.sourceIds")
        if not references or references != sorted(set(references)):
            raise RegistryBuildError(f"{context}.sourceIds must be nonempty, unique, and sorted")
        for reference in references:
            if reference not in source_ids:
                raise RegistryBuildError(f"{context} references unknown source {reference!r}")
        classifications[identifier] = classification
    if not classifications:
        raise RegistryBuildError("at least one classification is required")
    display_classification = _require_xml_id(
        plan["displayClassificationId"], "plan.displayClassificationId"
    )
    if display_classification not in classifications:
        raise RegistryBuildError("display classification does not resolve")

    catalogs: dict[str, dict[str, Any]] = {}
    catalog_dictionary_ids: set[str] = set()
    for index, catalog in enumerate(_require_array(plan["catalogs"], "plan.catalogs")):
        context = f"plan.catalogs[{index}]"
        if not isinstance(catalog, dict):
            raise RegistryBuildError(f"{context} must be an object")
        _require_exact_keys(catalog, {"id", "dictionaryId", "sourceId"}, context)
        identifier = _require_xml_id(catalog["id"], f"{context}.id")
        dictionary_id = _require_string(catalog["dictionaryId"], f"{context}.dictionaryId")
        if identifier in catalogs or dictionary_id in catalog_dictionary_ids:
            raise RegistryBuildError("catalog IDs and dictionary IDs must each be unique")
        if catalog["sourceId"] not in source_ids:
            raise RegistryBuildError(f"{context} references unknown source")
        catalogs[identifier] = catalog
        assert isinstance(dictionary_id, str)
        catalog_dictionary_ids.add(dictionary_id)

    compatibilities = _require_array(plan["compatibleDictionaries"], "plan.compatibleDictionaries")
    compatibility_ids: list[str] = []
    for index, item in enumerate(compatibilities):
        context = f"plan.compatibleDictionaries[{index}]"
        if not isinstance(item, dict):
            raise RegistryBuildError(f"{context} must be an object")
        _require_exact_keys(item, {"id", "resourceHash"}, context)
        identifier = _require_string(item["id"], f"{context}.id")
        resource_hash = _require_string(item["resourceHash"], f"{context}.resourceHash")
        assert isinstance(identifier, str) and isinstance(resource_hash, str)
        if not resource_hash.startswith("sha256:") or SHA256_RE.fullmatch(resource_hash[7:]) is None:
            raise RegistryBuildError(f"{context}.resourceHash must use sha256:<64 lowercase hex>")
        compatibility_ids.append(identifier)
    if compatibility_ids != sorted(set(compatibility_ids)):
        raise RegistryBuildError("compatible dictionaries must be unique and lexically sorted")

    nodes: dict[str, dict[str, Any]] = {}
    node_order: list[str] = []
    seen_wikidata_qids: set[str] = set()
    for index, node in enumerate(_require_array(plan["nodes"], "plan.nodes")):
        context = f"plan.nodes[{index}]"
        if not isinstance(node, dict):
            raise RegistryBuildError(f"{context} must be an object")
        _require_exact_keys(
            node,
            {
                "id",
                "parentId",
                "kind",
                "selectable",
                "classificationNote",
                "classificationStatus",
                "labels",
                "labelSources",
                "aliases",
                "identifiers",
                "locations",
                "alternateLineages",
                "directTagProfileIds",
            },
            context,
        )
        raw_identifier = _require_string(node["id"], f"{context}.id")
        assert isinstance(raw_identifier, str)
        identifier = canonical_language_tag(raw_identifier)
        if identifier in nodes:
            raise RegistryBuildError(f"duplicate canonical node code {identifier!r}")
        if identifier.startswith("x-rask-") or "-x-rask-" in identifier:
            raise RegistryBuildError(f"parallel x-rask identifier is forbidden: {identifier!r}")
        parent = node["parentId"]
        if parent is not None:
            parent = canonical_language_tag(parent)
            if parent not in nodes:
                raise RegistryBuildError(f"{context}.parentId must reference an earlier node")
        kind = node["kind"]
        if kind not in NODE_KINDS:
            raise RegistryBuildError(f"{context}.kind is not controlled")
        selectable = _require_boolean(node["selectable"], f"{context}.selectable")
        if node["classificationStatus"] not in CLASSIFICATION_STATUSES:
            raise RegistryBuildError(f"{context}.classificationStatus is not controlled")
        if node["classificationNote"] is not None:
            _validate_labels(
                node["classificationNote"],
                f"{context}.classificationNote",
                nullable_values=True,
            )
            if all(node["classificationNote"][language] is None for language in LANGUAGES):
                raise RegistryBuildError(f"{context}.classificationNote must contain a localized value")
        _validate_labels(
            node["labels"], f"{context}.labels", nullable_values=not selectable
        )
        if node["labels"]["en"] is None:
            raise RegistryBuildError(f"{context}.labels.en is required for every node")
        label_sources = node["labelSources"]
        if not isinstance(label_sources, dict):
            raise RegistryBuildError(f"{context}.labelSources must be an object")
        _require_exact_keys(label_sources, set(LANGUAGES), f"{context}.labelSources")
        for language in LANGUAGES:
            label = node["labels"][language]
            source_id = label_sources[language]
            if label is None:
                if selectable or source_id is not None:
                    raise RegistryBuildError(
                        f"{context}.labelSources.{language} must be null exactly when its nonselectable label is null"
                    )
            elif source_id not in source_ids:
                raise RegistryBuildError(f"{context}.labelSources.{language} does not resolve")
        _validate_aliases(node["aliases"], f"{context}.aliases")
        for language in LANGUAGES:
            for alias in node["aliases"][language]:
                if alias["sourceId"] not in source_ids:
                    raise RegistryBuildError(f"{context}.aliases.{language} has unresolved provenance")

        seen_identifier_types: set[str] = set()
        glottocode: str | None = None
        for identifier_index, external in enumerate(_require_array(node["identifiers"], f"{context}.identifiers")):
            identifier_context = f"{context}.identifiers[{identifier_index}]"
            if not isinstance(external, dict):
                raise RegistryBuildError(f"{identifier_context} must be an object")
            _require_exact_keys(external, {"type", "value"}, identifier_context)
            external_type = external["type"]
            value = _require_string(external["value"], f"{identifier_context}.value")
            if external_type not in EXTERNAL_IDENTIFIER_TYPES or external_type in seen_identifier_types:
                raise RegistryBuildError(f"invalid or duplicate identifier type in {identifier_context}")
            seen_identifier_types.add(external_type)
            if external_type == "Glottolog":
                assert isinstance(value, str)
                if re.fullmatch(r"[a-z0-9]{8}", value) is None:
                    raise RegistryBuildError(f"invalid Glottocode in {identifier_context}")
                glottocode = value
            elif external_type == "Wikidata":
                assert isinstance(value, str)
                if QID_RE.fullmatch(value) is None or value in seen_wikidata_qids:
                    raise RegistryBuildError(
                        f"invalid or duplicate exact Wikidata QID in {identifier_context}"
                    )
                seen_wikidata_qids.add(value)

        for location_index, location in enumerate(_require_array(node["locations"], f"{context}.locations")):
            location_context = f"{context}.locations[{location_index}]"
            if not isinstance(location, dict):
                raise RegistryBuildError(f"{location_context} must be an object")
            _require_exact_keys(
                location,
                {"type", "latitude", "longitude", "sourceId", "sourceNodeId"},
                location_context,
            )
            if location["type"] not in LOCATION_TYPES:
                raise RegistryBuildError(f"{location_context}.type is not controlled")
            latitude, longitude = location["latitude"], location["longitude"]
            if isinstance(latitude, bool) or not isinstance(latitude, (int, float)) or not -90 <= latitude <= 90:
                raise RegistryBuildError(f"{location_context}.latitude is outside WGS84 bounds")
            if isinstance(longitude, bool) or not isinstance(longitude, (int, float)) or not -180 <= longitude <= 180:
                raise RegistryBuildError(f"{location_context}.longitude is outside WGS84 bounds")
            if location["sourceId"] not in source_ids:
                raise RegistryBuildError(f"{location_context} references unknown source")
            source_node = _require_string(location["sourceNodeId"], f"{location_context}.sourceNodeId")
            if location["sourceId"] == "src-glottolog-5-3" and source_node != glottocode:
                raise RegistryBuildError(f"{location_context} must retain the node Glottocode")
        if kind in {"family", "collective"} and node["locations"]:
            raise RegistryBuildError(f"semantic {kind} node {identifier!r} cannot carry a point")
        if identifier == "mk" and glottocode == "mace1250":
            points = {(item["latitude"], item["longitude"]) for item in node["locations"]}
            if (41.5957, 21.7932) not in points:
                raise RegistryBuildError("Macedonian mace1250 must retain the pinned Glottolog point")

        for alternate_index, alternate in enumerate(
            _require_array(node["alternateLineages"], f"{context}.alternateLineages")
        ):
            alternate_context = f"{context}.alternateLineages[{alternate_index}]"
            if not isinstance(alternate, dict):
                raise RegistryBuildError(f"{alternate_context} must be an object")
            _require_exact_keys(
                alternate,
                {"classificationId", "pathNodeIds", "status", "sourceId"},
                alternate_context,
            )
            if alternate["classificationId"] not in classifications:
                raise RegistryBuildError(f"{alternate_context} references unknown classification")
            if alternate["status"] not in CLASSIFICATION_STATUSES:
                raise RegistryBuildError(f"{alternate_context}.status is not controlled")
            if alternate["sourceId"] not in source_ids:
                raise RegistryBuildError(f"{alternate_context} references unknown source")
            path = _require_array(alternate["pathNodeIds"], f"{alternate_context}.pathNodeIds")
            if not path:
                raise RegistryBuildError(f"{alternate_context}.pathNodeIds must be nonempty")

        profiles = _require_array(node["directTagProfileIds"], f"{context}.directTagProfileIds")
        if profiles != sorted(set(profiles)):
            raise RegistryBuildError(f"{context}.directTagProfileIds must be unique and sorted")
        nodes[identifier] = node
        node_order.append(identifier)

    if not nodes:
        raise RegistryBuildError("at least one registry node is required")
    children: dict[str | None, list[str]] = defaultdict(list)
    for identifier in node_order:
        children[nodes[identifier]["parentId"]].append(identifier)
    preorder: list[str] = []

    def visit(identifier: str) -> None:
        preorder.append(identifier)
        for child in children.get(identifier, []):
            visit(child)

    for root_identifier in children[None]:
        visit(root_identifier)
    if preorder != node_order:
        raise RegistryBuildError("plan.nodes must be in complete display preorder")

    for identifier, node in nodes.items():
        for alternate in node["alternateLineages"]:
            for path_identifier in alternate["pathNodeIds"]:
                if path_identifier not in nodes:
                    raise RegistryBuildError(
                        f"alternate lineage on {identifier!r} references unknown node {path_identifier!r}"
                    )

    profiles: dict[str, dict[str, Any]] = {}
    for index, profile in enumerate(_require_array(plan["tagProfiles"], "plan.tagProfiles")):
        context = f"plan.tagProfiles[{index}]"
        if not isinstance(profile, dict):
            raise RegistryBuildError(f"{context} must be an object")
        _require_exact_keys(profile, {"id", "tag", "displayNodeId", "labels", "sourceRecordIds"}, context)
        identifier = canonical_language_tag(profile["id"])
        tag = canonical_language_tag(profile["tag"])
        display = canonical_language_tag(profile["displayNodeId"])
        if identifier != tag or identifier != display:
            raise RegistryBuildError(f"{context} identity, tag, and display node must be the same canonical code")
        if identifier in profiles or display not in nodes:
            raise RegistryBuildError(f"duplicate or orphaned tag profile {identifier!r}")
        if not nodes[display]["selectable"]:
            raise RegistryBuildError(f"tag profile {identifier!r} maps to a nonselectable node")
        _validate_labels(profile["labels"], f"{context}.labels")
        if profile["labels"] != nodes[display]["labels"]:
            raise RegistryBuildError(f"tag profile {identifier!r} labels must equal its display node labels")
        records = _require_array(profile["sourceRecordIds"], f"{context}.sourceRecordIds")
        if records != sorted(set(records)):
            raise RegistryBuildError(f"{context}.sourceRecordIds must be unique and sorted")
        profiles[identifier] = profile
    if list(profiles) != sorted(profiles):
        raise RegistryBuildError("tag profiles must be lexically ordered by canonical code")

    profile_owners: dict[str, str] = {}
    for node_identifier, node in nodes.items():
        for profile_identifier in node["directTagProfileIds"]:
            if profile_identifier not in profiles:
                raise RegistryBuildError(f"node {node_identifier!r} references unknown tag profile")
            if profile_identifier in profile_owners:
                raise RegistryBuildError(f"tag profile {profile_identifier!r} has multiple display nodes")
            if profile_identifier != node_identifier:
                raise RegistryBuildError(f"direct profile {profile_identifier!r} must equal its node code")
            profile_owners[profile_identifier] = node_identifier
    if set(profile_owners) != set(profiles):
        raise RegistryBuildError("every tag profile must occur in exactly one node")

    records: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(_require_array(plan["sourceRecords"], "plan.sourceRecords")):
        context = f"plan.sourceRecords[{index}]"
        if not isinstance(record, dict):
            raise RegistryBuildError(f"{context} must be an object")
        _require_exact_keys(
            record,
            {
                "id",
                "kind",
                "labels",
                "abbreviation",
                "mappedTagProfileId",
                "note",
                "sourceId",
                "catalogId",
                "sourceLabel",
            },
            context,
        )
        identifier = _require_xml_id(record["id"], f"{context}.id")
        if identifier in records or record["kind"] not in SOURCE_RECORD_KINDS:
            raise RegistryBuildError(f"duplicate or invalid source record {identifier!r}")
        _validate_labels(record["labels"], f"{context}.labels")
        _require_string(record["abbreviation"], f"{context}.abbreviation", nullable=True)
        source_label = _require_string(record["sourceLabel"], f"{context}.sourceLabel")
        if record["abbreviation"] is not None and record["abbreviation"] != source_label:
            raise RegistryBuildError(f"{context}.abbreviation must equal its literal source label")
        if record["mappedTagProfileId"] not in profiles:
            raise RegistryBuildError(f"source record {identifier!r} references unknown tag profile")
        if record["sourceId"] not in source_ids:
            raise RegistryBuildError(f"source record {identifier!r} references unknown provenance source")
        if record["catalogId"] not in catalogs:
            raise RegistryBuildError(f"source record {identifier!r} references unknown dictionary catalog")
        if catalogs[record["catalogId"]]["sourceId"] != record["sourceId"]:
            raise RegistryBuildError(f"source record {identifier!r} provenance differs from its catalog source")
        if record["note"] is not None:
            _validate_labels(record["note"], f"{context}.note", nullable_values=True)
            if all(record["note"][language] is None for language in LANGUAGES):
                raise RegistryBuildError(f"{context}.note must contain at least one localized value")
        records[identifier] = record

    for profile_identifier, profile in profiles.items():
        actual = sorted(
            identifier
            for identifier, record in records.items()
            if record["mappedTagProfileId"] == profile_identifier
        )
        if profile["sourceRecordIds"] != actual:
            raise RegistryBuildError(f"tag/source inverse differs for {profile_identifier!r}")
    referenced_records = {
        record_identifier
        for profile in profiles.values()
        for record_identifier in profile["sourceRecordIds"]
    }
    if referenced_records != set(records):
        raise RegistryBuildError("every source record must occur in exactly one tag profile inverse")

    if standards is not None:
        iana, glottolog, iso_by_id, wikidata, wikidata_by_glottocode, wikidata_by_iso, wikidata_by_ietf = standards
        seen_glottocodes: set[str] = set()
        for identifier, node in nodes.items():
            try:
                validate_registered_tag(identifier, iana)
            except RegistrySourceError as exc:
                raise RegistryBuildError(str(exc)) from exc
            external = {item["type"]: item["value"] for item in node["identifiers"]}
            glottocode = external.get("Glottolog")
            if glottocode is not None:
                if glottocode not in glottolog or glottocode in seen_glottocodes:
                    raise RegistryBuildError(f"unknown or duplicate exact Glottocode {glottocode!r}")
                seen_glottocodes.add(glottocode)
                glottolog_iso = glottolog[glottocode].iso639_3
                if (identifier, glottocode, glottolog_iso) in iso_scope_exceptions and external.get("ISO639-3") is not None:
                    raise RegistryBuildError(f"node {identifier!r} promotes a reviewed narrower ISO reference to exact")
                if (glottolog_iso in iso_by_id and external.get("ISO639-3") != glottolog_iso
                    and (identifier, glottocode, glottolog_iso) not in iso_scope_exceptions):
                    raise RegistryBuildError(f"node {identifier!r} has an incomplete Glottolog/ISO exact inventory")
            iso3 = external.get("ISO639-3")
            if iso3 is not None:
                iso = iso_by_id.get(iso3)
                if iso is None:
                    raise RegistryBuildError(f"node {identifier!r} has unknown ISO639-3 identifier")
                expected = {
                    key: value
                    for key, value in {
                        "ISO639-1": iso.part1,
                        "ISO639-2B": iso.part2b,
                        "ISO639-2T": iso.part2t,
                        "ISO639-3": iso.identifier,
                    }.items()
                    if value is not None
                }
                actual = {key: value for key, value in external.items() if key.startswith("ISO639-") and key != "ISO639-5"}
                if actual != expected:
                    raise RegistryBuildError(f"node {identifier!r} has an incomplete exact ISO inventory")
                if "-" not in identifier and iso.part1 is not None and identifier != iso.part1:
                    raise RegistryBuildError(f"node {identifier!r} does not use the shortest exact standard code")
            wikidata_qid = external.get("Wikidata")
            if wikidata_qid is not None:
                wikidata_item = wikidata.get(wikidata_qid)
                if wikidata_item is None:
                    raise RegistryBuildError(
                        f"node {identifier!r} has a Wikidata assignment absent from the pinned snapshot"
                    )
                glottolog_item = wikidata_by_glottocode.get(glottocode) if glottocode else None
                iso_item = wikidata_by_iso.get(iso3) if iso3 else None
                ietf_item = wikidata_by_ietf.get(identifier.casefold())
                # An exact Glottolog node disambiguates a broader Wikidata
                # IETF/ISO item (notably Iron versus generic Ossetian).
                expected_qids = ({glottolog_item.qid} if glottolog_item is not None else {
                    item.qid for item in (iso_item, ietf_item) if item is not None
                })
                if len(expected_qids) > 1 or (
                    expected_qids and wikidata_qid not in expected_qids
                ):
                    raise RegistryBuildError(
                        f"node {identifier!r} has a conflicting or unsupported Wikidata assignment"
                    )
                if wikidata_item.ietf_tags and "-x-" not in identifier and identifier.casefold() not in {
                    value.casefold() for value in wikidata_item.ietf_tags
                }:
                    raise RegistryBuildError(
                        f"node {identifier!r} conflicts with its Wikidata IETF language-tag claim"
                    )
                if glottocode and wikidata_item.glottocodes and glottocode not in wikidata_item.glottocodes:
                    raise RegistryBuildError(
                        f"node {identifier!r} conflicts with its Wikidata Glottolog claim"
                    )
                if iso3 and wikidata_item.iso639_3 and iso3 not in wikidata_item.iso639_3:
                    raise RegistryBuildError(
                        f"node {identifier!r} conflicts with its Wikidata ISO 639-3 claim"
                    )


def validate_production_plan_provenance(plan: dict[str, Any], root: Path) -> None:
    """Bind a release plan to the closed queue and standards-derived candidate inventory."""
    approval = plan.get("approval")
    if not isinstance(approval, dict) or approval.get("mode") != "release":
        raise RegistryBuildError("production generation requires a release-approved plan")
    if approval.get("planPayloadSha256") != plan_payload_sha256(plan):
        raise RegistryBuildError("release approval is stale for the effective plan payload")
    approved_inputs = {
        "candidatesSha256": root / "dist/registry-candidates.json",
        "editorialReportSha256": root / "dist/editorial-review.tsv",
        "overridesSha256": root / "registry/raskovnik-overrides.xml",
    }
    for field, path in approved_inputs.items():
        actual = sha256(path)
        if approval.get(field) != actual:
            raise RegistryBuildError(f"release approval is stale for {path.relative_to(root)}")

    candidates = load_json(root / "dist/registry-candidates.json")
    if candidates.get("schema") != "language-registry-candidates-v1":
        raise RegistryBuildError("production plan references an unsupported candidate inventory")
    if candidates.get("summary", {}).get("profileExceptions") != 0 or candidates.get("summary", {}).get("ancestorExceptions") != 0:
        raise RegistryBuildError("production candidate inventory still contains unapproved exceptions")
    candidate_profiles = {row["id"]: row for row in candidates["profiles"]}
    plan_profiles = {row["id"]: row for row in plan["tagProfiles"]}
    if set(plan_profiles) != set(candidate_profiles):
        raise RegistryBuildError("release plan tag profiles differ from the approved candidate inventory")
    plan_nodes = {row["id"]: row for row in plan["nodes"]}
    for identifier, candidate in candidate_profiles.items():
        node = plan_nodes.get(identifier)
        profile = plan_profiles[identifier]
        if node is None or node["directTagProfileIds"] != [identifier]:
            raise RegistryBuildError(f"release plan lacks the canonical display/profile node {identifier!r}")
        if node["kind"] != candidate["kindCandidate"] or node["selectable"] != candidate["selectableCandidate"]:
            raise RegistryBuildError(f"release plan kind or selectability differs for {identifier!r}")
        if candidate.get("parentCandidate") is not None and node["parentId"] != candidate["parentCandidate"]:
            raise RegistryBuildError(f"release plan parent differs for {identifier!r}")
        if node["labels"] != candidate["preferredLabels"] or profile["labels"] != candidate["preferredLabels"]:
            raise RegistryBuildError(f"release plan preferred labels differ for {identifier!r}")
        expected_alias_values = {
            language: [item["value"] for item in candidate.get("aliasCandidates", {}).get(language, [])]
            for language in LANGUAGES
        }
        actual_alias_values = {
            language: [item["value"] for item in node["aliases"][language]]
            for language in LANGUAGES
        }
        if any(expected_alias_values[language] for language in LANGUAGES) and actual_alias_values != expected_alias_values:
            raise RegistryBuildError(f"release plan reviewed aliases differ for {identifier!r}")
        if profile["sourceRecordIds"] != sorted(candidate["sourceRecordIds"]):
            raise RegistryBuildError(f"release plan source-record inverse differs for {identifier!r}")
        if candidate["reviewReasons"] and (
            candidate["approval"] is None or candidate["approval"].get("status") != "approved"
        ):
            raise RegistryBuildError(f"release plan contains unapproved profile exception {identifier!r}")
        expected_identifiers: dict[str, str] = {}
        if candidate["glottolog"] and candidate["glottolog"]["relationship"] == "exact":
            expected_identifiers["Glottolog"] = candidate["glottolog"]["glottocode"]
        if candidate["id"] == candidate["iana"]["primary"]:
            iso = candidate["iso639"]
            if iso is not None:
                expected_identifiers.update(
                    {
                        key: value
                        for key, value in {
                            "ISO639-1": iso["part1"],
                            "ISO639-2B": iso["part2B"],
                            "ISO639-2T": iso["part2T"],
                            "ISO639-3": iso["part3"],
                        }.items()
                        if value is not None
                    }
                )
            if candidate["iana"]["scope"] == "collection":
                expected_identifiers["ISO639-5"] = identifier
        if candidate.get("wikidataQidCandidate") is not None:
            expected_identifiers["Wikidata"] = candidate["wikidataQidCandidate"]
        actual_identifiers = {item["type"]: item["value"] for item in node["identifiers"]}
        if actual_identifiers != expected_identifiers:
            raise RegistryBuildError(f"release plan exact identifier inventory differs for {identifier!r}")

    for ancestor in candidates["ancestorCandidates"]:
        code = ancestor["canonicalCodeCandidate"]
        if code is None:
            raise RegistryBuildError(f"ancestor {ancestor['glottocode']!r} still lacks a canonical code")
        if ancestor["reviewReasons"] and (
            ancestor["approval"] is None or ancestor["approval"].get("status") != "approved"
        ):
            raise RegistryBuildError(f"ancestor {ancestor['glottocode']!r} remains unapproved")
        node = plan_nodes.get(code)
        if node is None:
            raise RegistryBuildError(f"release plan omits approved ancestor {ancestor['glottocode']!r}")
        expected_identifiers = {"Glottolog": ancestor["glottocode"]}
        iso = ancestor.get("iso639")
        if iso is not None:
            expected_identifiers.update(
                {
                    key: value
                    for key, value in {
                        "ISO639-1": iso["part1"],
                        "ISO639-2B": iso["part2B"],
                        "ISO639-2T": iso["part2T"],
                        "ISO639-3": iso["part3"],
                    }.items()
                    if value is not None
                }
            )
        if ancestor.get("ianaScope") == "collection":
            expected_identifiers["ISO639-5"] = code
        if ancestor.get("wikidataQidCandidate") is not None:
            expected_identifiers["Wikidata"] = ancestor["wikidataQidCandidate"]
        if {item["type"]: item["value"] for item in node["identifiers"]} != expected_identifiers:
            raise RegistryBuildError(f"release plan identifiers differ for ancestor {ancestor['glottocode']!r}")
        if node["kind"] != ancestor["kindCandidate"] or node["selectable"] != ancestor["selectableCandidate"]:
            raise RegistryBuildError(f"release plan kind or selectability differs for ancestor {ancestor['glottocode']!r}")
        if ancestor.get("parentCandidate") is not None and node["parentId"] != ancestor["parentCandidate"]:
            raise RegistryBuildError(f"release plan parent differs for ancestor {ancestor['glottocode']!r}")
        if ancestor["approval"] is not None and node["labels"] != ancestor["preferredLabels"]:
            raise RegistryBuildError(f"release plan labels differ for ancestor {ancestor['glottocode']!r}")

    _profiles, catalog_records = parse_effective_persj_catalog(
        root / "upstream/persj" / candidates["sources"]["persjCommit"][:7] / "effective-language-catalog.xml"
    )
    plan_catalog = next(
        (catalog for catalog in plan["catalogs"] if catalog["dictionaryId"] == "ISJ.PERSJ"),
        None,
    )
    if plan_catalog is None:
        raise RegistryBuildError("release plan lacks the ISJ.PERSJ source-record catalog")
    approved_records = {record.identifier: record for record in catalog_records}
    plan_records = {
        record["id"]: record
        for record in plan["sourceRecords"]
        if record["catalogId"] == plan_catalog["id"]
    }
    if set(plan_records) != set(approved_records):
        raise RegistryBuildError("release plan source records differ from the count-free approved catalog")
    for identifier, source_record in approved_records.items():
        record = plan_records[identifier]
        expected_kind = (
            "compound-language-label" if source_record.kind == "compound" else "language-label"
        )
        expected_abbreviation = None if source_record.kind == "full-name" else source_record.label
        if (
            record["mappedTagProfileId"] != source_record.tag
            or record["sourceLabel"] != source_record.label
            or record["kind"] != expected_kind
            or record["abbreviation"] != expected_abbreviation
            or record["labels"]["sr"] != source_record.meaning_sr
        ):
            raise RegistryBuildError(f"release plan changes approved source-record meaning {identifier!r}")


def load_sources(source_lock: dict[str, Any], publication: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    _require_exact_keys(source_lock, {"schemaVersion", "sources"}, "source lock")
    if source_lock["schemaVersion"] != SOURCE_LOCK_SCHEMA:
        raise RegistryBuildError("unsupported pinned-source lock schema")
    _require_exact_keys(publication, {"schemaVersion", "upstreamSources", "projectSources"}, "publication metadata")
    if publication["schemaVersion"] != PUBLICATION_SCHEMA:
        raise RegistryBuildError("unsupported source-publication metadata schema")

    upstream_metadata: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(
        _require_array(publication["upstreamSources"], "publication metadata.upstreamSources")
    ):
        context = f"publication metadata.upstreamSources[{index}]"
        if not isinstance(item, dict):
            raise RegistryBuildError(f"{context} must be an object")
        _require_exact_keys(
            item,
            {"id", "manifestId", "licenceName", "licenceUrl", "attribution"},
            context,
        )
        source_id = _require_string(item["id"], f"{context}.id")
        assert isinstance(source_id, str)
        if source_id in upstream_metadata:
            raise RegistryBuildError(f"duplicate upstream publication source ID {source_id!r}")
        _require_xml_id(item["manifestId"], f"{context}.manifestId")
        _require_string(item["attribution"], f"{context}.attribution")
        licence_name = _require_string(item["licenceName"], f"{context}.licenceName", nullable=True)
        licence_url = _require_string(item["licenceUrl"], f"{context}.licenceUrl", nullable=True)
        if (licence_name is None) != (licence_url is None):
            raise RegistryBuildError(f"{context} licence name and URL must both be present or both be null")
        upstream_metadata[source_id] = item

    sources: list[dict[str, Any]] = []
    lock_ids: set[str] = set()
    for index, source in enumerate(_require_array(source_lock["sources"], "source lock.sources")):
        context = f"source lock.sources[{index}]"
        if not isinstance(source, dict):
            raise RegistryBuildError(f"{context} must be an object")
        source_id = _require_string(source.get("id"), f"{context}.id")
        assert isinstance(source_id, str)
        if source_id in lock_ids:
            raise RegistryBuildError(f"duplicate pinned source ID {source_id!r}")
        lock_ids.add(source_id)
        metadata = upstream_metadata.get(source_id)
        if metadata is None:
            raise RegistryBuildError(f"publication metadata missing pinned source {source_id!r}")
        for file_record in source["files"]:
            path = root / file_record["path"]
            if not path.is_file() or path.stat().st_size != file_record["bytes"] or sha256(path) != file_record["sha256"]:
                raise RegistryBuildError(f"pinned source drift while building: {file_record['path']}")
        sources.append(
            {
                "id": source_id,
                "manifestId": metadata["manifestId"],
                "title": source["title"],
                "version": source["version"],
                "revision": source["revision"],
                "url": source["url"],
                "files": source["files"],
                "licenceName": metadata["licenceName"],
                "licenceUrl": metadata["licenceUrl"],
                "attribution": metadata["attribution"],
            }
        )
    if set(upstream_metadata) != lock_ids:
        raise RegistryBuildError("publication metadata and pinned-source lock inventories differ")

    project_ids: set[str] = set()
    for index, project_source in enumerate(
        _require_array(publication["projectSources"], "publication metadata.projectSources")
    ):
        context = f"publication metadata.projectSources[{index}]"
        if not isinstance(project_source, dict):
            raise RegistryBuildError(f"{context} must be an object")
        _require_exact_keys(
            project_source,
            {"id", "manifestId", "title", "url", "licenceName", "licenceUrl", "attribution"},
            context,
        )
        project_id = _require_string(project_source["id"], f"{context}.id")
        assert isinstance(project_id, str)
        if project_id in project_ids:
            raise RegistryBuildError(f"duplicate project publication source ID {project_id!r}")
        if project_id in lock_ids:
            raise RegistryBuildError(f"project and upstream publication source IDs overlap at {project_id!r}")
        project_ids.add(project_id)
        _require_xml_id(project_source["manifestId"], f"{context}.manifestId")
        for field in ("title", "url", "attribution"):
            _require_string(project_source[field], f"{context}.{field}")
        licence_name = _require_string(
            project_source["licenceName"], f"{context}.licenceName", nullable=True
        )
        licence_url = _require_string(
            project_source["licenceUrl"], f"{context}.licenceUrl", nullable=True
        )
        if (licence_name is None) != (licence_url is None):
            raise RegistryBuildError(f"{context} licence name and URL must both be present or both be null")
        sources.append(
            {
                "id": project_id,
                "manifestId": project_source["manifestId"],
                "title": project_source["title"],
                "url": project_source["url"],
                "licenceName": project_source["licenceName"],
                "licenceUrl": project_source["licenceUrl"],
                "attribution": project_source["attribution"],
                "version": None,
                "revision": None,
                "files": [],
            }
        )
    manifest_ids = [source["manifestId"] for source in sources]
    if len(manifest_ids) != len(set(manifest_ids)) or any(XML_ID_RE.fullmatch(item) is None for item in manifest_ids):
        raise RegistryBuildError("source manifest IDs must be unique XML identifiers")
    return sorted(sources, key=lambda source: source["manifestId"])


def _subelement(parent: ET.Element, local_name: str, text: str | None = None, **attributes: str) -> ET.Element:
    element = ET.SubElement(parent, qname(TEI_NS, local_name), attributes)
    if text is not None:
        element.text = text
    return element


def _manifest_subelement(parent: ET.Element, local_name: str, text: str | None = None, **attributes: str) -> ET.Element:
    element = ET.SubElement(parent, qname(MANIFEST_NS, local_name), attributes)
    if text is not None:
        element.text = text
    return element


def _format_coordinate(value: int | float) -> str:
    return format(value, ".12g")


def build_registry_tree(
    plan: dict[str, Any],
    sources: list[dict[str, Any]],
    standards: tuple[
        dict[Any, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ],
    *, iso_scope_exceptions: frozenset = frozenset(),
) -> ET.Element:
    source_by_id = {source["manifestId"]: source for source in sources}
    validate_plan(plan, set(source_by_id), standards, iso_scope_exceptions=iso_scope_exceptions)
    root = ET.Element(qname(TEI_NS, "TEI"), {"type": "lex-0"})
    header = _subelement(root, "teiHeader")
    file_desc = _subelement(header, "fileDesc")
    title_stmt = _subelement(file_desc, "titleStmt")
    _subelement(title_stmt, "title", "Raskovnik language registry")
    publication_stmt = _subelement(file_desc, "publicationStmt")
    _subelement(publication_stmt, "publisher", "Belgrade Center for Digital Humanities")
    availability = _subelement(publication_stmt, "availability", status="free")
    _subelement(
        availability,
        "p",
        "The public registry contains language classification, labels, mappings, and provenance but no dictionary evidence or aggregates.",
    )
    source_desc = _subelement(file_desc, "sourceDesc")
    source_list = _subelement(source_desc, "listBibl", type="registrySources")
    for source in sources:
        bits = [source["title"]]
        if source.get("version"):
            bits.append(str(source["version"]))
        _subelement(
            source_list,
            "bibl",
            ". ".join(bits),
            **{qname(XML_NS, "id"): source["manifestId"], "type": "registrySource"},
        )
    classification_list = _subelement(source_desc, "listBibl", type="registryClassifications")
    for classification in plan["classifications"]:
        bibl = _subelement(
            classification_list,
            "bibl",
            **{qname(XML_NS, "id"): classification["id"], "type": "classification"},
        )
        for language in LANGUAGES:
            _subelement(
                bibl,
                "title",
                classification["labels"][language],
                **{qname(XML_NS, "lang"): language, "type": "classificationName"},
            )
        if classification["version"] is not None:
            _subelement(bibl, "idno", classification["version"], type="version")
        for source_id in classification["sourceIds"]:
            _subelement(bibl, "ref", source_id, type="classificationSource", target=f"#{source_id}")
    catalog_list = _subelement(source_desc, "listBibl", type="dictionaryLanguageCatalogs")
    for catalog in plan["catalogs"]:
        bibl = _subelement(
            catalog_list,
            "bibl",
            **{qname(XML_NS, "id"): catalog["id"], "type": "dictionaryLanguageCatalog"},
        )
        _subelement(bibl, "idno", catalog["dictionaryId"], type="dictionaryId")
        _subelement(
            bibl,
            "ref",
            catalog["sourceId"],
            type="catalogSource",
            target=f"#{catalog['sourceId']}",
        )

    profile_desc = _subelement(header, "profileDesc")
    lang_usage = _subelement(profile_desc, "langUsage")
    nodes = {node["id"]: node for node in plan["nodes"]}
    children: dict[str | None, list[str]] = defaultdict(list)
    for node in plan["nodes"]:
        children[node["parentId"]].append(node["id"])
    profiles = {profile["id"]: profile for profile in plan["tagProfiles"]}
    records = {record["id"]: record for record in plan["sourceRecords"]}

    def append_node(parent: ET.Element, identifier: str) -> None:
        node = nodes[identifier]
        has_children = bool(children.get(identifier))
        element_name = "languageGrp" if has_children else "language"
        attributes = {
            "ident": identifier,
            "type": node["kind"],
        }
        if element_name == "language":
            attributes["role"] = "objectLanguage"
        element = _subelement(parent, element_name, **attributes)
        _subelement(
            element,
            "ident",
            identifier,
            type="BCP47",
            **{qname(XML_NS, "id"): technical_id(identifier)},
        )
        for external in node["identifiers"]:
            _subelement(element, "ident", external["value"], type=external["type"])
        for language in LANGUAGES:
            if node["labels"][language] is not None:
                _subelement(
                    element,
                    "name",
                    node["labels"][language],
                    type="languageName",
                    role="languageReferenceName",
                    source=f"#{node['labelSources'][language]}",
                    **{
                        qname(XML_NS, "id"): name_id(identifier, language, "preferred"),
                        qname(XML_NS, "lang"): language,
                    },
                )
            for alias_index, alias in enumerate(node["aliases"][language]):
                _subelement(
                    element,
                    "name",
                    alias["value"],
                    type="languageName",
                    role="languageAlias",
                    source=f"#{alias['sourceId']}",
                    **{
                        qname(XML_NS, "id"): name_id(identifier, language, "alias", alias_index),
                        qname(XML_NS, "lang"): language,
                    },
                )
        _subelement(
            element,
            "note",
            "This node may be selected." if node["selectable"] else "This structural node is not selectable.",
            type="selectionStatus",
            subtype="selectable" if node["selectable"] else "nonselectable",
            source="#src-raskovnik-review",
        )
        _subelement(
            element,
            "note",
            f"Classification status: {node['classificationStatus']}.",
            type="classificationStatus",
            subtype=node["classificationStatus"],
            source="#src-raskovnik-review",
        )
        if node["classificationNote"] is not None:
            for language in LANGUAGES:
                note = node["classificationNote"][language]
                if note is not None:
                    _subelement(
                        element,
                        "note",
                        note,
                        type="classificationNote",
                        source="#src-raskovnik-review",
                        **{qname(XML_NS, "lang"): language},
                    )
        for profile_id in node["directTagProfileIds"]:
            _subelement(
                element,
                "note",
                profile_id,
                type="tagProfile",
                subtype="direct",
                source="#src-raskovnik-review",
                **{qname(XML_NS, "id"): f"profile-{profile_id}"},
            )
            profile = profiles[profile_id]
            for record_id in profile["sourceRecordIds"]:
                record = records[record_id]
                _subelement(
                    element,
                    "name",
                    record["sourceLabel"],
                    type="sourceLabel",
                    role=record["kind"],
                    subtype="abbreviation" if record["abbreviation"] is not None else "label-only",
                    source=f"#{record['sourceId']}",
                    ana=f"#profile-{profile_id} #{record['catalogId']}",
                    **{
                        qname(XML_NS, "id"): record_id,
                        qname(XML_NS, "lang"): "sr",
                    },
                )
                for language in LANGUAGES:
                    _subelement(
                        element,
                        "name",
                        record["labels"][language],
                        type="sourceRecordLabel",
                        role="sourceRecordName",
                        corresp=f"#{record_id}",
                        source=f"#{record['sourceId']}",
                        **{
                            qname(XML_NS, "id"): f"{record_id}-label-{language}",
                            qname(XML_NS, "lang"): language,
                        },
                    )
                if record["note"] is not None:
                    for language in LANGUAGES:
                        note = record["note"][language]
                        if note is not None:
                            _subelement(
                                element,
                                "note",
                                note,
                                type="sourceRecordNote",
                                corresp=f"#{record_id}",
                                source=f"#{record['sourceId']}",
                                **{qname(XML_NS, "lang"): language},
                            )
        for alternate in node["alternateLineages"]:
            note = _subelement(
                element,
                "note",
                type="alternateClassification",
                subtype=alternate["status"],
                source=f"#{alternate['sourceId']}",
                ana=f"#{alternate['classificationId']}",
            )
            for path_node in alternate["pathNodeIds"]:
                _subelement(
                    note,
                    "ref",
                    nodes[path_node]["labels"]["en"],
                    type="alternatePathNode",
                    target=f"#{technical_id(path_node)}",
                )
        setting_desc = _subelement(element, "settingDesc") if node["locations"] else None
        for location in node["locations"]:
            assert setting_desc is not None
            place = _subelement(setting_desc, "place")
            location_element = _subelement(
                place,
                "location",
                type=location["type"],
                source=f"#{location['sourceId']}",
            )
            _subelement(
                location_element,
                "geo",
                f"{_format_coordinate(location['latitude'])} {_format_coordinate(location['longitude'])}",
            )
            _subelement(place, "idno", location["sourceNodeId"], type="sourceNode")
        for child in children.get(identifier, []):
            append_node(element, child)

    for root_identifier in children[None]:
        append_node(lang_usage, root_identifier)
    revision_desc = _subelement(header, "revisionDesc", status="published")
    _subelement(
        revision_desc,
        "change",
        f"Published Raskovnik language registry {plan['registryVersion']}.",
        type="registryVersion",
        n=plan["registryVersion"],
        when=plan["releasedAt"],
    )
    text = _subelement(root, "text")
    body = _subelement(text, "body")
    _subelement(body, "p", "This TEI Lex-0 document is the authoritative public Raskovnik language registry.")
    return root


def xml_bytes(root: ET.Element) -> bytes:
    # Other XML tooling shares ElementTree namespace state in the test/import process.
    ET.register_namespace("", TEI_NS)
    ET.register_namespace("m", MANIFEST_NS)
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True, short_empty_elements=True) + b"\n"


def build_manifest_tree(
    plan: dict[str, Any], sources: list[dict[str, Any]], registry_bytes: bytes
) -> ET.Element:
    plan_hash = hashlib.sha256(canonical_json_bytes(plan)).hexdigest()
    content_hash = hashlib.sha256(registry_bytes).hexdigest()
    root = ET.Element(
        qname(MANIFEST_NS, "registryManifest"),
        {
            "formatVersion": "1",
            "registryVersion": plan["registryVersion"],
            "builtAt": plan["releasedAt"],
            "contentSha256": content_hash,
            "planSha256": plan_hash,
            "displayClassificationId": plan["displayClassificationId"],
        },
    )
    lex0_source = next(source for source in sources if source["id"] == "lex-0")
    lex0_file = next(file for file in lex0_source["files"] if file["path"].endswith(".rng"))
    if (
        lex0_source["version"] != LEX0_VERSION
        or lex0_source["revision"] != LEX0_REVISION
        or lex0_file["sha256"] != LEX0_SHA256
    ):
        raise RegistryBuildError("pinned Lex-0 schema identity differs from the reviewed contract")
    _manifest_subelement(
        root,
        "schema",
        id="tei-lex-0",
        version=LEX0_VERSION,
        revision=LEX0_REVISION,
        sha256=LEX0_SHA256,
    )
    source_container = _manifest_subelement(root, "sources")
    for source in sources:
        attributes = {
            qname(XML_NS, "id"): source["manifestId"],
            "upstreamId": source["id"],
            "title": source["title"],
            "url": source["url"],
        }
        if source.get("version") is not None:
            attributes["version"] = str(source["version"])
        if source.get("revision") is not None:
            attributes["revision"] = str(source["revision"])
        source_element = _manifest_subelement(source_container, "source", **attributes)
        if source["licenceName"] is not None:
            _manifest_subelement(
                source_element,
                "licence",
                name=source["licenceName"],
                url=source["licenceUrl"],
            )
        _manifest_subelement(source_element, "attribution", source["attribution"])
        for file_record in source["files"]:
            _manifest_subelement(
                source_element,
                "file",
                path=file_record["path"],
                bytes=str(file_record["bytes"]),
                sha256=file_record["sha256"],
            )
    classifications = _manifest_subelement(root, "classifications")
    for classification in plan["classifications"]:
        attributes = {qname(XML_NS, "id"): classification["id"]}
        if classification["version"] is not None:
            attributes["version"] = classification["version"]
        classification_element = _manifest_subelement(classifications, "classification", **attributes)
        for language in LANGUAGES:
            _manifest_subelement(
                classification_element,
                "label",
                classification["labels"][language],
                **{qname(XML_NS, "lang"): language},
            )
        for source_id in classification["sourceIds"]:
            _manifest_subelement(classification_element, "source", ref=f"#{source_id}")
    catalogs = _manifest_subelement(root, "catalogs")
    for catalog in plan["catalogs"]:
        catalog_element = _manifest_subelement(
            catalogs,
            "catalog",
            **{qname(XML_NS, "id"): catalog["id"], "dictionaryId": catalog["dictionaryId"]},
        )
        _manifest_subelement(catalog_element, "source", ref=f"#{catalog['sourceId']}")
    compatibility = _manifest_subelement(root, "compatibility")
    for dictionary in plan["compatibleDictionaries"]:
        _manifest_subelement(
            compatibility,
            "dictionary",
            id=dictionary["id"],
            resourceHash=dictionary["resourceHash"],
        )
    return root


def build_artifacts(
    plan: dict[str, Any], source_lock: dict[str, Any], publication: dict[str, Any], root: Path
) -> tuple[bytes, bytes]:
    from registry_overrides import approved_iso_scope_exceptions
    scope_exceptions = approved_iso_scope_exceptions(root)
    sources = load_sources(source_lock, publication, root)
    _iana_date, iana = parse_iana_registry(
        root / "upstream/iana/2026-08-08/language-subtag-registry"
    )
    glottolog, _glottolog_by_iso = parse_glottolog(
        root / "upstream/glottolog/5.3/languoid.csv"
    )
    iso_by_id, _iso_by_part1, _iso_by_part2 = parse_iso639_3(
        root / "upstream/iso-639-3/2026-07-22/iso-639-3.tab"
    )
    wikidata, wikidata_by_glottocode, wikidata_by_iso, wikidata_by_ietf = parse_wikidata_evidence(
        root / "upstream/wikidata/2026-09-06/language-items.json"
    )
    registry = xml_bytes(
        build_registry_tree(
            plan,
            sources,
            (
                iana,
                glottolog,
                iso_by_id,
                wikidata,
                wikidata_by_glottocode,
                wikidata_by_iso,
                wikidata_by_ietf,
            ),
            iso_scope_exceptions=scope_exceptions,
        )
    )
    manifest = xml_bytes(build_manifest_tree(plan, sources, registry))
    return registry, manifest


def resolve_tags(plan: dict[str, Any], node_id: str, scope: str) -> list[str]:
    nodes = {node["id"]: node for node in plan["nodes"]}
    if node_id not in nodes or scope not in {"direct", "inclusive"}:
        raise RegistryBuildError("unknown resolution node or scope")
    selected = {node_id}
    if scope == "inclusive":
        changed = True
        while changed:
            changed = False
            for identifier, node in nodes.items():
                if node["parentId"] in selected and identifier not in selected:
                    selected.add(identifier)
                    changed = True
    return sorted(
        profile_id
        for identifier in selected
        for profile_id in nodes[identifier]["directTagProfileIds"]
    )


def project_registry_core(registry_bytes: bytes, manifest_bytes: bytes) -> dict[str, Any]:
    """Reconstruct the dictionary-neutral runtime contract from generated XML only."""
    registry = ET.fromstring(registry_bytes)
    manifest = ET.fromstring(manifest_bytes)
    source_elements = manifest.findall(
        f"./{qname(MANIFEST_NS, 'sources')}/{qname(MANIFEST_NS, 'source')}"
    )
    sources = [
        {
            "id": element.get(qname(XML_NS, "id")),
            "title": element.get("title"),
            "version": element.get("version"),
            "url": element.get("url"),
        }
        for element in source_elements
    ]
    classification_elements = manifest.findall(
        f"./{qname(MANIFEST_NS, 'classifications')}/{qname(MANIFEST_NS, 'classification')}"
    )
    classifications = []
    for element in classification_elements:
        labels = {
            label.get(qname(XML_NS, "lang")): normalized(label.text or "")
            for label in element.findall(qname(MANIFEST_NS, "label"))
        }
        classifications.append(
            {
                "id": element.get(qname(XML_NS, "id")),
                "labels": labels,
                "version": element.get("version"),
                "sourceIds": [
                    source.get("ref", "").removeprefix("#")
                    for source in element.findall(qname(MANIFEST_NS, "source"))
                ],
            }
        )
    catalog_elements = manifest.findall(
        f"./{qname(MANIFEST_NS, 'catalogs')}/{qname(MANIFEST_NS, 'catalog')}"
    )
    catalogs = [
        {
            "id": element.get(qname(XML_NS, "id")),
            "dictionaryId": element.get("dictionaryId"),
            "sourceId": element.find(qname(MANIFEST_NS, "source")).get("ref", "").removeprefix("#"),
        }
        for element in catalog_elements
    ]
    compatibility_elements = manifest.findall(
        f"./{qname(MANIFEST_NS, 'compatibility')}/{qname(MANIFEST_NS, 'dictionary')}"
    )
    compatible_dictionaries = [
        {"id": element.get("id"), "resourceHash": element.get("resourceHash")}
        for element in compatibility_elements
    ]

    lang_usage = registry.find(
        f"./{qname(TEI_NS, 'teiHeader')}/{qname(TEI_NS, 'profileDesc')}/{qname(TEI_NS, 'langUsage')}"
    )
    if lang_usage is None:
        raise RegistryBuildError("cannot project a registry without langUsage")
    nodes: list[dict[str, Any]] = []
    tag_profiles: list[dict[str, Any]] = []
    source_records: list[dict[str, Any]] = []

    def direct_children(element: ET.Element, local_name: str) -> list[ET.Element]:
        return element.findall(qname(TEI_NS, local_name))

    def visit(element: ET.Element, parent_id: str | None) -> None:
        identifier = element.get("ident", "")
        preferred_names = [
            name
            for name in direct_children(element, "name")
            if name.get("type") == "languageName" and name.get("role") == "languageReferenceName"
        ]
        labels_by_language = {
            name.get(qname(XML_NS, "lang")): normalized(name.text or "")
            for name in preferred_names
        }
        label_sources_by_language = {
            name.get(qname(XML_NS, "lang")): name.get("source", "").removeprefix("#")
            for name in preferred_names
        }
        labels = {language: labels_by_language.get(language) for language in LANGUAGES}
        label_sources = {
            language: label_sources_by_language.get(language) for language in LANGUAGES
        }
        aliases: dict[str, list[dict[str, str]]] = {language: [] for language in LANGUAGES}
        for name in direct_children(element, "name"):
            if name.get("type") == "languageName" and name.get("role") == "languageAlias":
                language = name.get(qname(XML_NS, "lang"), "")
                aliases[language].append(
                    {
                        "value": normalized(name.text or ""),
                        "sourceId": name.get("source", "").removeprefix("#"),
                    }
                )
        identifiers = [
            {"type": item.get("type"), "value": normalized(item.text or "")}
            for item in direct_children(element, "ident")
            if item.get("type") != "BCP47"
        ]
        selection = next(
            note for note in direct_children(element, "note") if note.get("type") == "selectionStatus"
        )
        classification_status = next(
            note for note in direct_children(element, "note") if note.get("type") == "classificationStatus"
        )
        classification_notes = {
            note.get(qname(XML_NS, "lang")): normalized(note.text or "")
            for note in direct_children(element, "note")
            if note.get("type") == "classificationNote"
        }
        classification_note = (
            {language: classification_notes.get(language) for language in LANGUAGES}
            if classification_notes
            else None
        )
        alternate_lineages = []
        for note in direct_children(element, "note"):
            if note.get("type") != "alternateClassification":
                continue
            alternate_lineages.append(
                {
                    "classificationId": note.get("ana", "").removeprefix("#"),
                    "pathNodeIds": [
                        ref.get("target", "").removeprefix("#lang-")
                        for ref in direct_children(note, "ref")
                        if ref.get("type") == "alternatePathNode"
                    ],
                    "status": note.get("subtype"),
                    "sourceId": note.get("source", "").removeprefix("#"),
                }
            )
        locations = []
        for setting in direct_children(element, "settingDesc"):
            for place in direct_children(setting, "place"):
                source_node = next(
                    (
                        normalized(item.text or "")
                        for item in direct_children(place, "idno")
                        if item.get("type") == "sourceNode"
                    ),
                    "",
                )
                for location in direct_children(place, "location"):
                    latitude, longitude = map(
                        float,
                        normalized(location.find(qname(TEI_NS, "geo")).text or "").split(),
                    )
                    locations.append(
                        {
                            "type": location.get("type"),
                            "latitude": latitude,
                            "longitude": longitude,
                            "sourceId": location.get("source", "").removeprefix("#"),
                            "sourceNodeId": source_node,
                        }
                    )
        profile_notes = [
            note
            for note in direct_children(element, "note")
            if note.get("type") == "tagProfile" and note.get("subtype") == "direct"
        ]
        direct_profile_ids = sorted(normalized(note.text or "") for note in profile_notes)
        nodes.append(
            {
                "id": identifier,
                "parentId": parent_id,
                "kind": element.get("type"),
                "selectable": selection.get("subtype") == "selectable",
                "classificationStatus": classification_status.get("subtype"),
                "classificationNote": classification_note,
                "labels": labels,
                "labelSources": label_sources,
                "aliases": aliases,
                "identifiers": identifiers,
                "locations": locations,
                "alternateLineages": alternate_lineages,
                "directTagProfileIds": direct_profile_ids,
            }
        )
        source_labels = [
            name for name in direct_children(element, "name") if name.get("type") == "sourceLabel"
        ]
        for profile_id in direct_profile_ids:
            marker_id = f"profile-{profile_id}"
            owned = [
                name
                for name in source_labels
                if f"#{marker_id}" in name.get("ana", "").split()
            ]
            tag_profiles.append(
                {
                    "id": profile_id,
                    "tag": profile_id,
                    "displayNodeId": identifier,
                    "labels": labels,
                    "sourceRecordIds": sorted(
                        name.get(qname(XML_NS, "id"), "") for name in owned
                    ),
                }
            )
        for source_label in source_labels:
            record_id = source_label.get(qname(XML_NS, "id"), "")
            ana_tokens = source_label.get("ana", "").split()
            profile_ids = [token.removeprefix("#profile-") for token in ana_tokens if token.startswith("#profile-")]
            catalog_ids = [token.removeprefix("#") for token in ana_tokens if token.startswith("#catalog-")]
            localized_labels = {
                name.get(qname(XML_NS, "lang")): normalized(name.text or "")
                for name in direct_children(element, "name")
                if name.get("type") == "sourceRecordLabel" and name.get("corresp") == f"#{record_id}"
            }
            localized_notes = {
                note.get(qname(XML_NS, "lang")): normalized(note.text or "")
                for note in direct_children(element, "note")
                if note.get("type") == "sourceRecordNote" and note.get("corresp") == f"#{record_id}"
            }
            source_records.append(
                {
                    "id": record_id,
                    "kind": source_label.get("role"),
                    "labels": localized_labels,
                    "sourceLabel": normalized(source_label.text or ""),
                    "abbreviation": (
                        normalized(source_label.text or "")
                        if source_label.get("subtype") == "abbreviation"
                        else None
                    ),
                    "mappedTagProfileId": profile_ids[0] if len(profile_ids) == 1 else None,
                    "catalogId": catalog_ids[0] if len(catalog_ids) == 1 else None,
                    "sourceId": source_label.get("source", "").removeprefix("#"),
                    "note": (
                        {language: localized_notes.get(language) for language in LANGUAGES}
                        if localized_notes
                        else None
                    ),
                }
            )
        for child in list(element):
            if child.tag in {qname(TEI_NS, "language"), qname(TEI_NS, "languageGrp")}:
                visit(child, identifier)

    for child in list(lang_usage):
        if child.tag in {qname(TEI_NS, "language"), qname(TEI_NS, "languageGrp")}:
            visit(child, None)
    return {
        "registryVersion": manifest.get("registryVersion"),
        "releasedAt": manifest.get("builtAt"),
        "displayClassificationId": manifest.get("displayClassificationId"),
        "sources": sources,
        "classifications": classifications,
        "catalogs": catalogs,
        "compatibleDictionaries": compatible_dictionaries,
        "nodes": nodes,
        "tagProfiles": sorted(tag_profiles, key=lambda item: item["id"]),
        "sourceRecords": sorted(source_records, key=lambda item: item["id"]),
    }


def _manifest_classification_records(manifest: ET.Element) -> list[dict[str, Any]]:
    return [
        {
            "id": element.get(qname(XML_NS, "id")),
            "labels": {
                label.get(qname(XML_NS, "lang")): normalized(label.text or "")
                for label in element.findall(qname(MANIFEST_NS, "label"))
            },
            "version": element.get("version"),
            "sourceIds": [
                source.get("ref", "").removeprefix("#")
                for source in element.findall(qname(MANIFEST_NS, "source"))
            ],
        }
        for element in manifest.findall(
            f"./{qname(MANIFEST_NS, 'classifications')}/{qname(MANIFEST_NS, 'classification')}"
        )
    ]


def _manifest_source_records(manifest: ET.Element) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for element in manifest.findall(
        f"./{qname(MANIFEST_NS, 'sources')}/{qname(MANIFEST_NS, 'source')}"
    ):
        licences = element.findall(qname(MANIFEST_NS, "licence"))
        attributions = element.findall(qname(MANIFEST_NS, "attribution"))
        if len(licences) > 1 or len(attributions) != 1:
            raise RegistryBuildError("manifest source licence or attribution cardinality is invalid")
        records.append(
            {
                "id": element.get(qname(XML_NS, "id")),
                "upstreamId": element.get("upstreamId"),
                "title": element.get("title"),
                "version": element.get("version"),
                "revision": element.get("revision"),
                "url": element.get("url"),
                "licenceName": licences[0].get("name") if len(licences) == 1 else None,
                "licenceUrl": licences[0].get("url") if len(licences) == 1 else None,
                "attribution": (
                    normalized(attributions[0].text or "")
                    if len(attributions) == 1
                    else None
                ),
                "files": [
                    {
                        "path": file_record.get("path"),
                        "bytes": int(file_record.get("bytes", "-1")),
                        "sha256": file_record.get("sha256"),
                    }
                    for file_record in element.findall(qname(MANIFEST_NS, "file"))
                ],
            }
        )
    return records


def _manifest_catalog_records(manifest: ET.Element) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for element in manifest.findall(
        f"./{qname(MANIFEST_NS, 'catalogs')}/{qname(MANIFEST_NS, 'catalog')}"
    ):
        sources = element.findall(qname(MANIFEST_NS, "source"))
        records.append(
            {
                "id": element.get(qname(XML_NS, "id")),
                "dictionaryId": element.get("dictionaryId"),
                "sourceId": (
                    sources[0].get("ref", "").removeprefix("#")
                    if len(sources) == 1
                    else None
                ),
            }
        )
    return records


def _manifest_compatibility_records(manifest: ET.Element) -> list[dict[str, Any]]:
    return [
        {"id": element.get("id"), "resourceHash": element.get("resourceHash")}
        for element in manifest.findall(
            f"./{qname(MANIFEST_NS, 'compatibility')}/{qname(MANIFEST_NS, 'dictionary')}"
        )
    ]


def _source_desc_list(registry: ET.Element, list_type: str) -> ET.Element:
    source_desc = registry.find(
        f"./{qname(TEI_NS, 'teiHeader')}/{qname(TEI_NS, 'fileDesc')}/{qname(TEI_NS, 'sourceDesc')}"
    )
    if source_desc is None:
        raise RegistryBuildError("registry sourceDesc is missing")
    matches = [
        element
        for element in source_desc.findall(qname(TEI_NS, "listBibl"))
        if element.get("type") == list_type
    ]
    if len(matches) != 1:
        raise RegistryBuildError(f"registry sourceDesc must contain exactly one {list_type!r} list")
    return matches[0]


def _validate_source_desc_mirrors(registry: ET.Element, manifest: ET.Element) -> None:
    source_list = _source_desc_list(registry, "registrySources")
    source_bibls = list(source_list)
    if any(
        bibl.tag != qname(TEI_NS, "bibl")
        or bibl.get("type") != "registrySource"
        or len(list(bibl)) != 0
        for bibl in source_bibls
    ):
        raise RegistryBuildError("registry sourceDesc source mirror has an unexpected shape")
    tei_sources = [
        (bibl.get(qname(XML_NS, "id")), normalized(bibl.text or ""))
        for bibl in source_bibls
    ]
    manifest_sources = [
        (
            source.get(qname(XML_NS, "id")),
            ". ".join(
                value
                for value in (source.get("title", ""), source.get("version"))
                if value
            ),
        )
        for source in manifest.findall(
            f"./{qname(MANIFEST_NS, 'sources')}/{qname(MANIFEST_NS, 'source')}"
        )
    ]
    if tei_sources != manifest_sources:
        raise RegistryBuildError("registry sourceDesc source mirror differs from the manifest")

    classification_list = _source_desc_list(registry, "registryClassifications")
    classification_bibls = list(classification_list)
    if any(
        bibl.tag != qname(TEI_NS, "bibl") or bibl.get("type") != "classification"
        for bibl in classification_bibls
    ):
        raise RegistryBuildError("registry sourceDesc classification mirror has an unexpected shape")
    manifest_classifications = _manifest_classification_records(manifest)
    if len(classification_bibls) != len(manifest_classifications):
        raise RegistryBuildError("registry sourceDesc classification mirror differs from the manifest")
    for bibl, classification in zip(classification_bibls, manifest_classifications):
        allowed_children = {
            (qname(TEI_NS, "title"), "classificationName"),
            (qname(TEI_NS, "idno"), "version"),
            (qname(TEI_NS, "ref"), "classificationSource"),
        }
        if any((child.tag, child.get("type")) not in allowed_children for child in list(bibl)):
            raise RegistryBuildError("registry sourceDesc classification mirror has an unexpected shape")
        labels = [
            (title.get(qname(XML_NS, "lang")), normalized(title.text or ""))
            for title in bibl.findall(qname(TEI_NS, "title"))
            if title.get("type") == "classificationName"
        ]
        versions = [
            normalized(version.text or "")
            for version in bibl.findall(qname(TEI_NS, "idno"))
            if version.get("type") == "version"
        ]
        sources = [
            (reference.get("target"), normalized(reference.text or ""))
            for reference in bibl.findall(qname(TEI_NS, "ref"))
            if reference.get("type") == "classificationSource"
        ]
        expected_labels = [
            (language, classification["labels"].get(language, ""))
            for language in LANGUAGES
        ]
        expected_versions = (
            [] if classification["version"] is None else [classification["version"]]
        )
        expected_sources = [
            (f"#{source_id}", source_id) for source_id in classification["sourceIds"]
        ]
        if (
            bibl.get(qname(XML_NS, "id")) != classification["id"]
            or labels != expected_labels
            or versions != expected_versions
            or sources != expected_sources
        ):
            raise RegistryBuildError("registry sourceDesc classification mirror differs from the manifest")

    catalog_list = _source_desc_list(registry, "dictionaryLanguageCatalogs")
    catalog_bibls = list(catalog_list)
    if any(
        bibl.tag != qname(TEI_NS, "bibl")
        or bibl.get("type") != "dictionaryLanguageCatalog"
        for bibl in catalog_bibls
    ):
        raise RegistryBuildError("registry sourceDesc catalog mirror has an unexpected shape")
    manifest_catalogs = _manifest_catalog_records(manifest)
    if len(catalog_bibls) != len(manifest_catalogs):
        raise RegistryBuildError("registry sourceDesc catalog mirror differs from the manifest")
    for bibl, catalog in zip(catalog_bibls, manifest_catalogs):
        allowed_children = {
            (qname(TEI_NS, "idno"), "dictionaryId"),
            (qname(TEI_NS, "ref"), "catalogSource"),
        }
        if any((child.tag, child.get("type")) not in allowed_children for child in list(bibl)):
            raise RegistryBuildError("registry sourceDesc catalog mirror has an unexpected shape")
        dictionary_ids = [
            normalized(identifier.text or "")
            for identifier in bibl.findall(qname(TEI_NS, "idno"))
            if identifier.get("type") == "dictionaryId"
        ]
        sources = [
            (reference.get("target"), normalized(reference.text or ""))
            for reference in bibl.findall(qname(TEI_NS, "ref"))
            if reference.get("type") == "catalogSource"
        ]
        if (
            bibl.get(qname(XML_NS, "id")) != catalog["id"]
            or dictionary_ids != [catalog["dictionaryId"]]
            or sources != [(f"#{catalog['sourceId']}", catalog["sourceId"])]
        ):
            raise RegistryBuildError("registry sourceDesc catalog mirror differs from the manifest")


def validate_generated_registry(registry_bytes: bytes, plan: dict[str, Any]) -> None:
    try:
        root = ET.fromstring(registry_bytes)
    except ET.ParseError as exc:
        raise RegistryBuildError(f"generated registry is not well-formed: {exc}") from exc
    if root.tag != qname(TEI_NS, "TEI") or root.get("type") != "lex-0":
        raise RegistryBuildError("registry root must be TEI type=lex-0")
    if root.find(f"./{qname(TEI_NS, 'teiHeader')}/{qname(TEI_NS, 'profileDesc')}/{qname(TEI_NS, 'langUsage')}") is None:
        raise RegistryBuildError("registry display tree is not under profileDesc/langUsage")
    if root.find(f"./{qname(TEI_NS, 'text')}/{qname(TEI_NS, 'body')}/{qname(TEI_NS, 'p')}") is None:
        raise RegistryBuildError("registry requires explanatory text/body content")
    version_changes = root.findall(
        f"./{qname(TEI_NS, 'teiHeader')}/{qname(TEI_NS, 'revisionDesc')}/{qname(TEI_NS, 'change')}[@type='registryVersion']"
    )
    if (
        len(version_changes) != 1
        or version_changes[0].get("n") != plan["registryVersion"]
        or version_changes[0].get("when") != plan["releasedAt"]
    ):
        raise RegistryBuildError("registry must embed exactly one matching registry version change")
    for forbidden in ("taxonomy", "category", "xenoData"):
        if root.find(f".//{qname(TEI_NS, forbidden)}") is not None:
            raise RegistryBuildError(f"forbidden TEI element in registry: {forbidden}")
    nodes = root.findall(f".//{qname(TEI_NS, 'languageGrp')}") + root.findall(
        f".//{qname(TEI_NS, 'language')}"
    )
    canonical_codes: set[str] = set()
    xml_ids: set[str] = set()
    for element in root.iter():
        identifier = element.get(qname(XML_NS, "id"))
        if identifier:
            if identifier in xml_ids:
                raise RegistryBuildError(f"duplicate xml:id {identifier!r}")
            xml_ids.add(identifier)
    for node in nodes:
        identifier = canonical_language_tag(node.get("ident", ""))
        if identifier in canonical_codes:
            raise RegistryBuildError(f"duplicate canonical node {identifier!r}")
        canonical_codes.add(identifier)
        bcp47 = [child for child in node.findall(qname(TEI_NS, "ident")) if child.get("type") == "BCP47"]
        if len(bcp47) != 1 or normalized(bcp47[0].text or "") != identifier:
            raise RegistryBuildError(f"node {identifier!r} must contain one matching BCP47 identifier")
        if bcp47[0].get(qname(XML_NS, "id")) != technical_id(identifier):
            raise RegistryBuildError(f"node {identifier!r} has a nonderived technical xml:id")
        if node.tag == qname(TEI_NS, "language") and node.get("role") != "objectLanguage":
            raise RegistryBuildError(f"leaf language {identifier!r} must have role=objectLanguage")
        if node.tag == qname(TEI_NS, "languageGrp") and node.get("role") is not None:
            raise RegistryBuildError(f"language group {identifier!r} cannot carry role")
        direct_child_nodes = [
            child
            for child in list(node)
            if child.tag in {qname(TEI_NS, "language"), qname(TEI_NS, "languageGrp")}
        ]
        if bool(direct_child_nodes) != (node.tag == qname(TEI_NS, "languageGrp")):
            raise RegistryBuildError(f"node {identifier!r} physical element does not match child presence")
        preferred = [
            child
            for child in node.findall(qname(TEI_NS, "name"))
            if child.get("type") == "languageName" and child.get("role") == "languageReferenceName"
        ]
        preferred_languages = [child.get(qname(XML_NS, "lang")) for child in preferred]
        selectable = node.find(qname(TEI_NS, "note") + "[@type='selectionStatus']").get("subtype") == "selectable"
        required_languages = set(LANGUAGES) if selectable else {"en"}
        if (len(preferred_languages) != len(set(preferred_languages))
                or not required_languages <= set(preferred_languages) <= set(LANGUAGES)
                or any(not normalized(child.text or "") for child in preferred)):
            raise RegistryBuildError(f"node {identifier!r} lacks valid preferred labels")
        status_notes = [
            child
            for child in node.findall(qname(TEI_NS, "note"))
            if child.get("type") == "classificationStatus"
        ]
        if len(status_notes) != 1 or status_notes[0].get("subtype") not in CLASSIFICATION_STATUSES:
            raise RegistryBuildError(f"node {identifier!r} lacks one controlled classification status")
        if len(node.findall(qname(TEI_NS, "settingDesc"))) > 1:
            raise RegistryBuildError(f"node {identifier!r} must consolidate locations in one settingDesc")
        profile_notes = [
            child
            for child in node.findall(qname(TEI_NS, "note"))
            if child.get("type") == "tagProfile" and child.get("subtype") == "direct"
        ]
        for profile in profile_notes:
            profile_code = normalized(profile.text or "")
            if profile_code != identifier or profile.get(qname(XML_NS, "id")) != f"profile-{profile_code}":
                raise RegistryBuildError(f"node {identifier!r} has a malformed direct tag-profile marker")
        for source_label in [
            child
            for child in node.findall(qname(TEI_NS, "name"))
            if child.get("type") == "sourceLabel"
        ]:
            if source_label.get("subtype") not in {"abbreviation", "label-only"}:
                raise RegistryBuildError(f"node {identifier!r} has an ambiguous source-label abbreviation state")
            ana_tokens = source_label.get("ana", "").split()
            profile_targets = [token for token in ana_tokens if token.startswith("#profile-")]
            catalog_targets = [token for token in ana_tokens if token.startswith("#catalog-")]
            if (
                len(ana_tokens) != 2
                or len(profile_targets) != 1
                or len(catalog_targets) != 1
                or profile_targets[0][1:] not in xml_ids
                or catalog_targets[0][1:] not in xml_ids
            ):
                raise RegistryBuildError(f"source record on {identifier!r} must link one profile and one catalog")
            if profile_targets[0] != f"#profile-{identifier}":
                raise RegistryBuildError(f"source record on {identifier!r} links the wrong direct profile")
            record_id = source_label.get(qname(XML_NS, "id"), "")
            localized = [
                child
                for child in node.findall(qname(TEI_NS, "name"))
                if child.get("type") == "sourceRecordLabel" and child.get("corresp") == f"#{record_id}"
            ]
            if len(localized) != 3 or {child.get(qname(XML_NS, "lang")) for child in localized} != set(LANGUAGES):
                raise RegistryBuildError(f"source record {record_id!r} lacks one trilingual label set")
        for pointer_element in node.findall(".//*[@source]"):
            pointer = pointer_element.get("source", "")
            if not pointer.startswith("#") or pointer[1:] not in xml_ids:
                raise RegistryBuildError(f"node {identifier!r} contains unresolved source pointer {pointer!r}")
        for ref in node.findall(f".//{qname(TEI_NS, 'ref')}[@target]"):
            target = ref.get("target", "")
            if target.startswith("#") and target[1:] not in xml_ids:
                raise RegistryBuildError(f"node {identifier!r} contains unresolved target {target!r}")
        direct_geo_path = (
            f"./{qname(TEI_NS, 'settingDesc')}/{qname(TEI_NS, 'place')}/"
            f"{qname(TEI_NS, 'location')}/{qname(TEI_NS, 'geo')}"
        )
        if node.get("type") in {"family", "collective"} and node.find(direct_geo_path) is not None:
            raise RegistryBuildError(f"semantic {node.get('type')} node {identifier!r} has a point")
        for geo in node.findall(direct_geo_path):
            parts = normalized(geo.text or "").split(" ")
            if len(parts) != 2:
                raise RegistryBuildError(f"node {identifier!r} has malformed geo content")
            try:
                latitude, longitude = map(float, parts)
            except ValueError as exc:
                raise RegistryBuildError(f"node {identifier!r} has nonnumeric geo content") from exc
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                raise RegistryBuildError(f"node {identifier!r} has out-of-range geo content")
    if canonical_codes != {node["id"] for node in plan["nodes"]}:
        raise RegistryBuildError("generated registry node inventory differs from the plan")


def validate_generated_manifest(
    manifest_bytes: bytes,
    registry_bytes: bytes,
    plan: dict[str, Any],
    sources: list[dict[str, Any]],
) -> None:
    try:
        root = ET.fromstring(manifest_bytes)
    except ET.ParseError as exc:
        raise RegistryBuildError(f"generated manifest is not well-formed: {exc}") from exc
    try:
        registry_root = ET.fromstring(registry_bytes)
    except ET.ParseError as exc:
        raise RegistryBuildError(f"generated registry is not well-formed: {exc}") from exc
    if root.tag != qname(MANIFEST_NS, "registryManifest") or root.get("formatVersion") != "1":
        raise RegistryBuildError("unexpected generated manifest root")
    if root.get("registryVersion") != plan["registryVersion"]:
        raise RegistryBuildError("manifest registry version differs from plan")
    if root.get("builtAt") != plan["releasedAt"]:
        raise RegistryBuildError("manifest release timestamp differs from plan")
    if root.get("displayClassificationId") != plan["displayClassificationId"]:
        raise RegistryBuildError("manifest display classification differs from plan")
    if root.get("contentSha256") != hashlib.sha256(registry_bytes).hexdigest():
        raise RegistryBuildError("manifest registry content hash differs")
    if root.get("planSha256") != hashlib.sha256(canonical_json_bytes(plan)).hexdigest():
        raise RegistryBuildError("manifest plan hash differs")
    schema = root.find(qname(MANIFEST_NS, "schema"))
    if schema is None or (schema.get("version"), schema.get("revision"), schema.get("sha256")) != (
        LEX0_VERSION,
        LEX0_REVISION,
        LEX0_SHA256,
    ):
        raise RegistryBuildError("manifest does not pin the reviewed Lex-0 schema")
    source_elements = root.findall(
        f"./{qname(MANIFEST_NS, 'sources')}/{qname(MANIFEST_NS, 'source')}"
    )
    source_id_list = [source.get(qname(XML_NS, "id")) for source in source_elements]
    if any(not source_id for source_id in source_id_list) or len(source_id_list) != len(
        set(source_id_list)
    ):
        raise RegistryBuildError("manifest source IDs must be nonempty and unique")
    source_ids = set(source_id_list)
    expected_sources = [
        {
            "id": source["manifestId"],
            "upstreamId": source["id"],
            "title": source["title"],
            "version": None if source["version"] is None else str(source["version"]),
            "revision": None if source["revision"] is None else str(source["revision"]),
            "url": source["url"],
            "licenceName": source["licenceName"],
            "licenceUrl": source["licenceUrl"],
            "attribution": source["attribution"],
            "files": source["files"],
        }
        for source in sources
    ]
    try:
        actual_sources = _manifest_source_records(root)
    except ValueError as exc:
        raise RegistryBuildError("manifest source file byte counts must be integers") from exc
    if actual_sources != expected_sources:
        raise RegistryBuildError("manifest sources differ from the pinned source contract")
    classifications = root.findall(
        f"./{qname(MANIFEST_NS, 'classifications')}/{qname(MANIFEST_NS, 'classification')}"
    )
    classification_ids = {item.get(qname(XML_NS, "id")) for item in classifications}
    if root.get("displayClassificationId") not in classification_ids:
        raise RegistryBuildError("manifest display classification does not resolve")
    for classification in classifications:
        labels = classification.findall(qname(MANIFEST_NS, "label"))
        if len(labels) != len(LANGUAGES) or {
            label.get(qname(XML_NS, "lang")) for label in labels
        } != set(LANGUAGES):
            raise RegistryBuildError("manifest classification lacks trilingual labels")
        for source in classification.findall(qname(MANIFEST_NS, "source")):
            reference = source.get("ref", "")
            if not reference.startswith("#") or reference[1:] not in source_ids:
                raise RegistryBuildError("manifest classification source does not resolve")
    catalogs = root.findall(f"./{qname(MANIFEST_NS, 'catalogs')}/{qname(MANIFEST_NS, 'catalog')}")
    catalog_ids: set[str] = set()
    dictionary_ids: set[str] = set()
    for catalog in catalogs:
        catalog_id = catalog.get(qname(XML_NS, "id"))
        dictionary_id = catalog.get("dictionaryId")
        source_refs = catalog.findall(qname(MANIFEST_NS, "source"))
        if (
            not catalog_id
            or catalog_id in catalog_ids
            or not dictionary_id
            or dictionary_id in dictionary_ids
            or len(source_refs) != 1
            or source_refs[0].get("ref", "").removeprefix("#") not in source_ids
        ):
            raise RegistryBuildError("manifest catalog identity or source reference is invalid")
        catalog_ids.add(catalog_id)
        dictionary_ids.add(dictionary_id)
    compatibilities = root.findall(
        f"./{qname(MANIFEST_NS, 'compatibility')}/{qname(MANIFEST_NS, 'dictionary')}"
    )
    seen_compatibilities: set[str] = set()
    for dictionary in compatibilities:
        identifier = dictionary.get("id", "")
        resource_hash = dictionary.get("resourceHash", "")
        if (
            not identifier
            or identifier in seen_compatibilities
            or not resource_hash.startswith("sha256:")
            or SHA256_RE.fullmatch(resource_hash[7:]) is None
        ):
            raise RegistryBuildError("manifest dictionary compatibility record is invalid")
        seen_compatibilities.add(identifier)
    if _manifest_classification_records(root) != plan["classifications"]:
        raise RegistryBuildError("manifest classifications differ from the approved plan")
    if _manifest_catalog_records(root) != plan["catalogs"]:
        raise RegistryBuildError("manifest catalogs differ from the approved plan")
    if _manifest_compatibility_records(root) != plan["compatibleDictionaries"]:
        raise RegistryBuildError("manifest compatibility differs from the approved plan")
    _validate_source_desc_mirrors(registry_root, root)
