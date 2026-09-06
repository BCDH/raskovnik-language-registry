#!/usr/bin/env python3
"""Offline parsers for the pinned Raskovnik language-registry inputs."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


PERSJ_CATALOG_NS = "urn:persj:source-vocabulary"
PERSJ_EXTENSION_NS = "urn:persj:etymon-languages"
REGISTRY_SOURCE_NS = "https://raskovnik.org/ns/language-registry/source"
XML_NS = "http://www.w3.org/XML/1998/namespace"
PRIVATE_MODIFIERS = frozenset({"young", "new", "middle", "old"})
QID_RE = re.compile(r"Q[1-9][0-9]*")
NON_SEMANTIC_WIKIDATA_TYPES = frozenset(
    {"Q4167836", "Q4167410", "Q11266439", "Q13406463"}
)


class RegistrySourceError(RuntimeError):
    """Raised when a pinned registry input is malformed or inconsistent."""


@dataclass(frozen=True)
class IanaRecord:
    record_type: str
    identifier: str
    fields: dict[str, tuple[str, ...]]

    @property
    def descriptions(self) -> tuple[str, ...]:
        return self.fields.get("Description", ())

    @property
    def deprecated(self) -> bool:
        return "Deprecated" in self.fields


@dataclass(frozen=True)
class Iso6393Record:
    identifier: str
    part2b: str | None
    part2t: str | None
    part1: str | None
    scope: str
    language_type: str
    reference_name: str


@dataclass(frozen=True)
class GlottologRecord:
    glottocode: str
    family_id: str | None
    parent_id: str | None
    name: str
    level: str
    latitude: float | None
    longitude: float | None
    iso639_3: str | None


@dataclass(frozen=True)
class WikidataItem:
    qid: str
    last_revision_id: int
    last_revision_timestamp: str
    labels: dict[str, str | None]
    descriptions: dict[str, str | None]
    glottocodes: tuple[str, ...]
    iso639_3: tuple[str, ...]
    ietf_tags: tuple[str, ...]
    instance_of: tuple[str, ...]
    subclass_of: tuple[str, ...]
    sitelinks: dict[str, str | None]


@dataclass(frozen=True)
class SourceRecord:
    identifier: str
    kind: str
    label: str
    meaning_sr: str
    tag: str
    status: str
    reason: str | None
    occurrences: int | None


@dataclass(frozen=True)
class TagProfile:
    tag: str
    status: str
    source_records: tuple[SourceRecord, ...]

    @property
    def serbian_names(self) -> tuple[str, ...]:
        return tuple(sorted({record.meaning_sr for record in self.source_records}))


def normalized(value: str) -> str:
    """Return an NFC, collapsed-whitespace value."""
    return unicodedata.normalize("NFC", " ".join(value.split()))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_wikidata_evidence(
    path: Path,
) -> tuple[
    dict[str, WikidataItem],
    dict[str, WikidataItem],
    dict[str, WikidataItem],
    dict[str, WikidataItem],
]:
    """Parse the reviewed snapshot and return QID, Glottocode, ISO, and IETF maps."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RegistrySourceError(f"cannot read Wikidata evidence {path}: {exc}") from exc
    if payload.get("schemaVersion") != "raskovnik-wikidata-language-evidence-v1":
        raise RegistrySourceError("unsupported Wikidata evidence schema")
    items: dict[str, WikidataItem] = {}
    by_glottocode: dict[str, WikidataItem] = {}
    by_iso: dict[str, WikidataItem] = {}
    by_ietf: dict[str, WikidataItem] = {}
    for raw in payload.get("items", []):
        qid = raw.get("qid")
        if not isinstance(qid, str) or QID_RE.fullmatch(qid) is None or qid in items:
            raise RegistrySourceError(f"invalid or duplicate Wikidata QID {qid!r}")
        claims = raw.get("claims", {})
        instance_of = tuple(claims.get("P31", []))
        if NON_SEMANTIC_WIKIDATA_TYPES.intersection(instance_of):
            raise RegistrySourceError(f"non-semantic Wikidata item is forbidden: {qid}")
        revision = raw.get("lastRevisionId")
        timestamp = raw.get("lastRevisionTimestamp")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision <= 0:
            raise RegistrySourceError(f"Wikidata item {qid} lacks a valid revision ID")
        if not isinstance(timestamp, str) or not timestamp.endswith("Z"):
            raise RegistrySourceError(f"Wikidata item {qid} lacks a revision timestamp")
        glottocodes = tuple(claims.get("P1394", []))
        iso639_3 = tuple(claims.get("P220", []))
        ietf_tags = tuple(claims.get("P305", []))
        if any(re.fullmatch(r"[a-z0-9]{8}", value) is None for value in glottocodes):
            raise RegistrySourceError(f"Wikidata item {qid} has an invalid Glottocode claim")
        if any(re.fullmatch(r"[a-z]{3}", value) is None for value in iso639_3):
            raise RegistrySourceError(f"Wikidata item {qid} has an invalid ISO 639-3 claim")
        if any(
            not isinstance(value, str)
            or re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", value) is None
            for value in ietf_tags
        ):
            raise RegistrySourceError(f"Wikidata item {qid} has an invalid IETF tag claim")
        item = WikidataItem(
            qid=qid,
            last_revision_id=revision,
            last_revision_timestamp=timestamp,
            labels={language: raw["labels"].get(language) for language in ("sr", "en", "de")},
            descriptions={
                language: raw["descriptions"].get(language)
                for language in ("sr", "en", "de")
            },
            glottocodes=glottocodes,
            iso639_3=iso639_3,
            ietf_tags=ietf_tags,
            instance_of=instance_of,
            subclass_of=tuple(claims.get("P279", [])),
            sitelinks={
                language: raw["sitelinks"].get(language)
                for language in ("sr", "en", "de")
            },
        )
        items[qid] = item
        for value, target, kind in (
            *((value, by_glottocode, "Glottocode") for value in glottocodes),
            *((value, by_iso, "ISO 639-3") for value in iso639_3),
            *((value.casefold(), by_ietf, "IETF language tag") for value in ietf_tags),
        ):
            if value in target:
                raise RegistrySourceError(
                    f"duplicate exact Wikidata {kind} assignment {value!r}: "
                    f"{target[value].qid} and {qid}"
                )
            target[value] = item
    if not items:
        raise RegistrySourceError("Wikidata evidence snapshot is empty")
    return items, by_glottocode, by_iso, by_ietf


def canonical_language_tag(tag: str) -> str:
    """Validate and canonicalize the BCP 47 subset used by Raskovnik."""
    if not tag or not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", tag):
        raise RegistrySourceError(f"malformed BCP 47 tag {tag!r}")
    parts = tag.split("-")
    if parts[0].lower() == "x":
        if len(parts) < 2 or any(not 1 <= len(part) <= 8 for part in parts[1:]):
            raise RegistrySourceError(f"invalid wholly private language tag {tag!r}")
        canonical = "-".join(part.lower() for part in parts)
        if tag != canonical:
            raise RegistrySourceError(
                f"non-canonical language tag {tag!r}; expected {canonical!r}"
            )
        return canonical

    primary = parts[0]
    if not re.fullmatch(r"[A-Za-z]{2,3}", primary):
        raise RegistrySourceError(f"unsupported primary language subtag in {tag!r}")
    canonical_parts = [primary.lower()]
    private = False
    for part in parts[1:]:
        if private:
            if not 1 <= len(part) <= 8:
                raise RegistrySourceError(f"invalid private subtag {part!r} in {tag!r}")
            canonical_parts.append(part.lower())
            continue
        if part.lower() == "x":
            private = True
            canonical_parts.append("x")
        elif re.fullmatch(r"[A-Za-z]{4}", part):
            canonical_parts.append(part.title())
        elif re.fullmatch(r"[A-Za-z]{2}|[0-9]{3}", part):
            canonical_parts.append(part.upper())
        elif re.fullmatch(r"[A-Za-z0-9]{5,8}|[0-9][A-Za-z0-9]{3}", part):
            canonical_parts.append(part.lower())
        else:
            raise RegistrySourceError(f"unsupported BCP 47 subtag {part!r} in {tag!r}")
    if private and canonical_parts[-1] == "x":
        raise RegistrySourceError(f"private-use marker has no value in {tag!r}")
    canonical = "-".join(canonical_parts)
    if tag != canonical:
        raise RegistrySourceError(
            f"non-canonical language tag {tag!r}; expected {canonical!r}"
        )
    return canonical


def is_private_tag(tag: str) -> bool:
    parts = tag.lower().split("-")
    return parts[0] == "x" or "x" in parts[1:]


def technical_id(code: str) -> str:
    """Derive the one technical XML identifier from a canonical code."""
    return "lang-" + canonical_language_tag(code)


def stable_source_id(kind: str, label: str) -> str:
    """Return an input-order-independent source-record identifier."""
    payload = f"{kind}\0{normalized(label).casefold()}".encode("utf-8")
    return f"src-{kind}-{hashlib.sha256(payload).hexdigest()[:16]}"


def parse_iana_registry(path: Path) -> tuple[str, dict[tuple[str, str], IanaRecord]]:
    data = path.read_text(encoding="utf-8")
    header, *blocks = data.split("%%")
    date_match = re.search(r"^File-Date:\s*(\d{4}-\d{2}-\d{2})\s*$", header, re.MULTILINE)
    if date_match is None:
        raise RegistrySourceError("IANA registry has no File-Date")
    records: dict[tuple[str, str], IanaRecord] = {}
    for block in blocks:
        fields: dict[str, list[str]] = {}
        current: str | None = None
        for line in block.strip().splitlines():
            if line.startswith(" ") and current is not None:
                fields[current][-1] += " " + line.strip()
                continue
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            current = name
            fields.setdefault(name, []).append(value.strip())
        record_type = fields.get("Type", [""])[0]
        identifier = fields.get("Subtag", fields.get("Tag", [""]))[0]
        if not record_type or not identifier:
            continue
        key = (record_type, identifier.lower())
        if key in records:
            raise RegistrySourceError(f"duplicate IANA record {key!r}")
        records[key] = IanaRecord(
            record_type,
            identifier,
            {name: tuple(values) for name, values in fields.items()},
        )
    return date_match.group(1), records


def validate_registered_tag(
    tag: str, records: dict[tuple[str, str], IanaRecord]
) -> None:
    """Validate all non-private subtags of a canonical tag against IANA."""
    parts = canonical_language_tag(tag).split("-")
    if parts[0] == "x":
        return
    primary = records.get(("language", parts[0].lower()))
    if primary is None or primary.deprecated:
        raise RegistrySourceError(f"tag {tag!r} has an unavailable primary subtag")
    private_index = next(
        (index for index, part in enumerate(parts[1:], 1) if part.lower() == "x"),
        len(parts),
    )
    prefix_parts = [parts[0]]
    for part in parts[1:private_index]:
        if re.fullmatch(r"[A-Z][a-z]{3}", part):
            record_type = "script"
        elif re.fullmatch(r"[A-Z]{2}|[0-9]{3}", part):
            record_type = "region"
        else:
            record_type = "variant"
        record = records.get((record_type, part.lower()))
        if record is None or record.deprecated:
            raise RegistrySourceError(
                f"tag {tag!r} has unavailable {record_type} subtag {part!r}"
            )
        prefixes = {value.lower() for value in record.fields.get("Prefix", ())}
        if prefixes and "-".join(prefix_parts).lower() not in prefixes:
            raise RegistrySourceError(
                f"variant {part!r} is unavailable for prefix {'-'.join(prefix_parts)!r}"
            )
        prefix_parts.append(part)


def parse_iso639_3(path: Path) -> tuple[
    dict[str, Iso6393Record], dict[str, Iso6393Record], dict[str, Iso6393Record]
]:
    by_id: dict[str, Iso6393Record] = {}
    by_part1: dict[str, Iso6393Record] = {}
    by_part2: dict[str, Iso6393Record] = {}
    with path.open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source, delimiter="\t"):
            record = Iso6393Record(
                row["Id"],
                row["Part2b"] or None,
                row["Part2t"] or None,
                row["Part1"] or None,
                row["Scope"],
                row["Language_Type"],
                row["Ref_Name"],
            )
            if record.identifier in by_id:
                raise RegistrySourceError(
                    f"duplicate ISO 639-3 identifier {record.identifier!r}"
                )
            by_id[record.identifier] = record
            if record.part1:
                by_part1[record.part1] = record
            for part2 in (record.part2b, record.part2t):
                if part2:
                    by_part2[part2] = record
    return by_id, by_part1, by_part2


def parse_glottolog(path: Path) -> tuple[
    dict[str, GlottologRecord], dict[str, GlottologRecord]
]:
    by_id: dict[str, GlottologRecord] = {}
    by_iso: dict[str, GlottologRecord] = {}
    with path.open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            record = GlottologRecord(
                row["id"],
                row["family_id"] or None,
                row["parent_id"] or None,
                row["name"],
                row["level"],
                float(row["latitude"]) if row["latitude"] else None,
                float(row["longitude"]) if row["longitude"] else None,
                row["iso639P3code"] or None,
            )
            if record.glottocode in by_id:
                raise RegistrySourceError(
                    f"duplicate Glottolog identifier {record.glottocode!r}"
                )
            by_id[record.glottocode] = record
            if record.iso639_3:
                previous = by_iso.get(record.iso639_3)
                if previous is not None:
                    raise RegistrySourceError(
                        f"ISO 639-3 {record.iso639_3!r} maps to multiple Glottolog nodes"
                    )
                by_iso[record.iso639_3] = record
    return by_id, by_iso


def glottolog_lineage(
    record: GlottologRecord, by_id: dict[str, GlottologRecord]
) -> tuple[GlottologRecord, ...]:
    lineage: list[GlottologRecord] = []
    seen: set[str] = set()
    current: GlottologRecord | None = record
    while current is not None:
        if current.glottocode in seen:
            raise RegistrySourceError(
                f"Glottolog parent cycle at {current.glottocode!r}"
            )
        seen.add(current.glottocode)
        lineage.append(current)
        current = by_id.get(current.parent_id) if current.parent_id else None
    return tuple(reversed(lineage))


def parse_cldr_german(path: Path) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    root = ET.parse(path).getroot()
    languages: dict[str, str] = {}
    territories: dict[str, str] = {}
    variants: dict[str, str] = {}
    for node in root.findall("./localeDisplayNames/languages/language"):
        code = node.get("type")
        if code and node.get("alt") is None and normalized(node.text or "") != "↑↑↑":
            languages[code] = normalized(node.text or "")
    for node in root.findall("./localeDisplayNames/territories/territory"):
        code = node.get("type")
        if code and node.get("alt") is None and normalized(node.text or "") != "↑↑↑":
            territories[code] = normalized(node.text or "")
    for node in root.findall("./localeDisplayNames/variants/variant"):
        code = node.get("type")
        if code and node.get("alt") is None and normalized(node.text or "") != "↑↑↑":
            variants[code] = normalized(node.text or "")
    return languages, territories, variants


def _source_record(
    kind: str,
    label: str,
    meaning: str,
    tag: str,
    status: str,
    reason: str | None,
    occurrences: int | None = None,
) -> SourceRecord:
    label = normalized(label)
    return SourceRecord(
        stable_source_id(kind, label),
        kind,
        label,
        normalized(meaning),
        canonical_language_tag(tag),
        status,
        normalized(reason) if reason else None,
        occurrences,
    )


def _composed_tag(base_tag: str, semantic: str) -> str:
    suffix = f"-{semantic}" if is_private_tag(base_tag) else f"-x-{semantic}"
    return canonical_language_tag(base_tag + suffix)


def parse_persj_profiles(
    catalog_path: Path, extension_path: Path
) -> tuple[dict[str, TagProfile], tuple[SourceRecord, ...]]:
    """Resolve base, extension, compound, and full-name records to canonical tags."""
    catalog_root = ET.parse(catalog_path).getroot()
    extension_root = ET.parse(extension_path).getroot()
    if catalog_root.tag != f"{{{PERSJ_CATALOG_NS}}}languageTagCatalog":
        raise RegistrySourceError("unexpected PERSJ language catalog root")
    if extension_root.tag != f"{{{PERSJ_EXTENSION_NS}}}etymonLanguageExtensions":
        raise RegistrySourceError("unexpected PERSJ language extension root")
    if catalog_root.get("formatVersion") != "2" or extension_root.get("formatVersion") != "2":
        raise RegistrySourceError("unsupported PERSJ language input version")
    if extension_root.get("baseSha256") != sha256(catalog_path):
        raise RegistrySourceError("PERSJ extension catalog points to a stale base catalog")

    records: list[SourceRecord] = []
    by_label: dict[str, SourceRecord] = {}
    modifier_by_label: dict[str, tuple[str, str]] = {}
    for node in catalog_root:
        local_name = node.tag.rsplit("}", 1)[-1]
        if local_name == "modifier":
            label = normalized(node.get("match", ""))
            meaning = normalized(node.get("meaning", ""))
            semantic = node.get("semantic", "")
            if not label or not meaning or semantic not in PRIVATE_MODIFIERS:
                raise RegistrySourceError(f"invalid PERSJ modifier {label!r}")
            modifier_by_label[label.casefold()] = (meaning, semantic)
            continue
        if local_name != "language":
            raise RegistrySourceError(f"unexpected PERSJ catalog node {local_name!r}")
        label = normalized(node.get("match", ""))
        tag = node.get("tag", "")
        status = node.get("status", "")
        if status not in {"registered", "private"} or not tag:
            raise RegistrySourceError(f"unmapped PERSJ language record {label!r}")
        record = _source_record(
            "base",
            label,
            node.get("meaning", ""),
            tag,
            status,
            node.get("reason"),
        )
        if label.casefold() in by_label:
            raise RegistrySourceError(f"duplicate PERSJ source label {label!r}")
        by_label[label.casefold()] = record
        records.append(record)

    for node in extension_root.findall(f"{{{PERSJ_EXTENSION_NS}}}language"):
        label = normalized(node.get("match", ""))
        status = node.get("status", "")
        if status not in {"registered", "private"}:
            raise RegistrySourceError(f"invalid extension status for {label!r}")
        record = _source_record(
            "extension",
            label,
            node.get("meaning", ""),
            node.get("tag", ""),
            status,
            node.get("reason"),
        )
        if label.casefold() in by_label:
            raise RegistrySourceError(f"duplicate PERSJ source label {label!r}")
        by_label[label.casefold()] = record
        records.append(record)

    seen_compounds: set[tuple[str, str]] = set()
    for node in extension_root.findall(f"{{{PERSJ_EXTENSION_NS}}}compound"):
        modifier_label = normalized(node.get("modifier", ""))
        base_label = normalized(node.get("base", ""))
        key = (modifier_label.casefold(), base_label.casefold())
        if key in seen_compounds:
            raise RegistrySourceError(f"duplicate PERSJ compound {key!r}")
        modifier = modifier_by_label.get(key[0])
        base = by_label.get(key[1])
        if modifier is None or base is None:
            raise RegistrySourceError(f"unresolved PERSJ compound {key!r}")
        if node.get("ref"):
            target = by_label.get(normalized(node.get("ref", "")).casefold())
            if target is None:
                raise RegistrySourceError(f"unresolved PERSJ compound reference {node.get('ref')!r}")
            tag = target.tag
        elif node.get("tag"):
            tag = canonical_language_tag(node.get("tag", ""))
        else:
            tag = _composed_tag(base.tag, modifier[1])
        stem = modifier_label.removesuffix("-")
        label = f"{stem}{base.label}"
        meaning = f"{modifier[0].removesuffix('-')}{base.meaning_sr}"
        status = "private" if is_private_tag(tag) else "registered"
        record = _source_record(
            "compound",
            label,
            meaning,
            tag,
            status,
            "productive compound audited in the PERSJ conversion",
            int(node.get("occurrences", "0")),
        )
        records.append(record)
        by_label.setdefault(label.casefold(), record)
        seen_compounds.add(key)

    for node in extension_root.findall(f"{{{PERSJ_EXTENSION_NS}}}fullName"):
        label = normalized(node.get("match", ""))
        target = by_label.get(normalized(node.get("ref", "")).casefold())
        if target is None:
            raise RegistrySourceError(f"unresolved PERSJ full-name reference {node.get('ref')!r}")
        records.append(
            _source_record(
                "full-name",
                label,
                target.meaning_sr,
                target.tag,
                target.status,
                "controlled full-name alias in the PERSJ conversion",
            )
        )

    identifiers = [record.identifier for record in records]
    if len(identifiers) != len(set(identifiers)):
        raise RegistrySourceError("stable PERSJ source-record identifier collision")

    records_by_tag: dict[str, list[SourceRecord]] = {}
    statuses_by_tag: dict[str, set[str]] = {}
    for record in records:
        records_by_tag.setdefault(record.tag, []).append(record)
        statuses_by_tag.setdefault(record.tag, set()).add(record.status)
    profiles: dict[str, TagProfile] = {}
    for tag, tag_records in sorted(records_by_tag.items()):
        statuses = statuses_by_tag[tag]
        expected = "private" if is_private_tag(tag) else "registered"
        if statuses != {expected}:
            raise RegistrySourceError(
                f"tag {tag!r} has inconsistent statuses {sorted(statuses)!r}"
            )
        profiles[tag] = TagProfile(
            tag,
            expected,
            tuple(sorted(tag_records, key=lambda record: (record.kind, record.label))),
        )
    return profiles, tuple(sorted(records, key=lambda record: record.identifier))


def parse_effective_persj_catalog(
    path: Path,
) -> tuple[dict[str, TagProfile], tuple[SourceRecord, ...]]:
    """Read the count-free, repository-local PERSJ mapping export."""
    root = ET.parse(path).getroot()
    if root.tag != f"{{{REGISTRY_SOURCE_NS}}}effectiveLanguageCatalog":
        raise RegistrySourceError("unexpected effective PERSJ catalog root")
    if root.get("formatVersion") != "1":
        raise RegistrySourceError("unsupported effective PERSJ catalog version")
    records: list[SourceRecord] = []
    profiles: dict[str, TagProfile] = {}
    identifiers: set[str] = set()
    for profile_node in root.findall(f"{{{REGISTRY_SOURCE_NS}}}tagProfile"):
        tag = canonical_language_tag(profile_node.get("ident", ""))
        status = profile_node.get("status", "")
        expected = "private" if is_private_tag(tag) else "registered"
        if status != expected or tag in profiles:
            raise RegistrySourceError(f"invalid effective tag profile {tag!r}")
        tag_records: list[SourceRecord] = []
        for node in profile_node.findall(f"{{{REGISTRY_SOURCE_NS}}}sourceRecord"):
            identifier = node.get(f"{{{XML_NS}}}id", "")
            kind = node.get("kind", "")
            label_node = node.find(
                f"{{{REGISTRY_SOURCE_NS}}}name[@type='sourceLabel']"
            )
            meaning_node = node.find(
                f"{{{REGISTRY_SOURCE_NS}}}name[@type='meaning']"
            )
            reason_node = node.find(f"{{{REGISTRY_SOURCE_NS}}}note[@type='reason']")
            label = normalized(label_node.text or "") if label_node is not None else ""
            meaning = normalized(meaning_node.text or "") if meaning_node is not None else ""
            if (
                not identifier
                or identifier in identifiers
                or not kind
                or not label
                or not meaning
                or stable_source_id(kind, label) != identifier
            ):
                raise RegistrySourceError(
                    f"invalid effective PERSJ source record {identifier!r}"
                )
            record = SourceRecord(
                identifier,
                kind,
                label,
                meaning,
                tag,
                status,
                normalized(reason_node.text or "") if reason_node is not None else None,
                None,
            )
            identifiers.add(identifier)
            records.append(record)
            tag_records.append(record)
        if not tag_records:
            raise RegistrySourceError(f"empty effective tag profile {tag!r}")
        profiles[tag] = TagProfile(
            tag,
            status,
            tuple(sorted(tag_records, key=lambda record: (record.kind, record.label))),
        )
    return profiles, tuple(sorted(records, key=lambda record: record.identifier))


def primary_subtag(tag: str) -> str:
    return canonical_language_tag(tag).split("-", 1)[0]


def standard_prefix(tag: str) -> str:
    parts = canonical_language_tag(tag).split("-")
    try:
        private_index = [part.lower() for part in parts].index("x")
    except ValueError:
        private_index = len(parts)
    return "-".join(parts[:private_index])


def all_values(records: Iterable[SourceRecord], attribute: str) -> tuple[str, ...]:
    return tuple(sorted({str(getattr(record, attribute)) for record in records}))
