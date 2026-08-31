#!/usr/bin/env python3
"""Generate deterministic standards mappings and the exception review queue."""

from __future__ import annotations

import argparse
import csv
import json
import re
import tempfile
from pathlib import Path

from registry_sources import (
    GlottologRecord,
    IanaRecord,
    Iso6393Record,
    TagProfile,
    glottolog_lineage,
    parse_cldr_german,
    parse_effective_persj_catalog,
    parse_glottolog,
    parse_iana_registry,
    parse_iso639_3,
    primary_subtag,
    standard_prefix,
    validate_registered_tag,
)
from registry_overrides import parse_overrides


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dist/registry-candidates.json"
DEFAULT_REVIEW = ROOT / "dist/editorial-review.tsv"


def name_key(value: str) -> str:
    value = value.casefold().replace("&", "and")
    value = re.sub(r"\blanguages?\b", "", value)
    return re.sub(r"[^a-z0-9]+", "", value)


def iso_for_primary(
    primary: str,
    by_id: dict[str, Iso6393Record],
    by_part1: dict[str, Iso6393Record],
    by_part2: dict[str, Iso6393Record],
) -> Iso6393Record | None:
    return by_part1.get(primary) or by_id.get(primary) or by_part2.get(primary)


def collection_glottolog_map(
    iana: dict[tuple[str, str], IanaRecord],
    glottolog: dict[str, GlottologRecord],
) -> tuple[dict[str, GlottologRecord], dict[str, list[GlottologRecord]]]:
    families_by_name: dict[str, list[GlottologRecord]] = {}
    for record in glottolog.values():
        if record.level == "family":
            families_by_name.setdefault(name_key(record.name), []).append(record)
    exact: dict[str, GlottologRecord] = {}
    ambiguous: dict[str, list[GlottologRecord]] = {}
    for (record_type, code), record in iana.items():
        if record_type != "language" or record.fields.get("Scope") != ("collection",):
            continue
        candidates: dict[str, GlottologRecord] = {}
        for description in record.descriptions:
            for glottolog_record in families_by_name.get(name_key(description), []):
                candidates[glottolog_record.glottocode] = glottolog_record
        if len(candidates) == 1:
            exact[code] = next(iter(candidates.values()))
        elif candidates:
            ambiguous[code] = sorted(candidates.values(), key=lambda item: item.glottocode)
    return exact, ambiguous


def english_candidate(
    tag: str,
    primary_record: IanaRecord,
    exact_glottolog: GlottologRecord | None,
    iana: dict[tuple[str, str], IanaRecord],
) -> str | None:
    if exact_glottolog is not None:
        return exact_glottolog.name
    base = primary_record.descriptions[0] if primary_record.descriptions else None
    if base is None:
        return None
    parts = tag.split("-")
    lower_parts = [part.lower() for part in parts]
    if "x" in lower_parts:
        private_parts = lower_parts[lower_parts.index("x") + 1 :]
        historical = {
            "old": "Old",
            "middle": "Middle",
            "new": "New",
            "young": "Young",
            "late": "Late",
            "vulgar": "Vulgar",
            "proto": "Proto",
        }
        if len(private_parts) == 1 and private_parts[0] in historical:
            return f"{historical[private_parts[0]]} {base}"
        return None
    descriptors: list[str] = []
    for part in parts[1:]:
        if re.fullmatch(r"[A-Z][a-z]{3}", part):
            record_type = "script"
        elif re.fullmatch(r"[A-Z]{2}|[0-9]{3}", part):
            record_type = "region"
        else:
            record_type = "variant"
        record = iana.get((record_type, part.lower()))
        if record and record.descriptions:
            descriptors.append(record.descriptions[0])
    return f"{base} ({', '.join(descriptors)})" if descriptors else base


def german_candidate(
    tag: str,
    languages: dict[str, str],
    territories: dict[str, str],
    variants: dict[str, str],
) -> tuple[str | None, str | None]:
    cldr_key = tag.replace("-", "_")
    if cldr_key in languages:
        return languages[cldr_key], "cldr-exact"
    parts = tag.split("-")
    if "x" in [part.lower() for part in parts]:
        return None, None
    base = languages.get(parts[0])
    if base is None:
        return None, None
    descriptors: list[str] = []
    for part in parts[1:]:
        descriptor = territories.get(part) or variants.get(part.upper())
        if descriptor is None:
            return None, None
        descriptors.append(descriptor)
    if descriptors:
        return f"{base} ({', '.join(descriptors)})", "cldr-composed"
    return base, "cldr-exact"


def kind_candidate(
    tag: str,
    primary_record: IanaRecord,
    glottolog: GlottologRecord | None,
) -> str:
    private_parts = tag.lower().split("-x-", 1)
    if len(private_parts) == 2:
        suffixes = private_parts[1].split("-")
        if "proto" in suffixes:
            return "reconstructed-language"
        if any(
            suffix in {"old", "middle", "new", "young", "late", "vulgar"}
            for suffix in suffixes
        ):
            return "historical-stage"
        return "variety"
    if primary_record.fields.get("Scope") == ("collection",):
        return "family"
    if glottolog is not None and glottolog.level == "dialect":
        return "variety"
    return "language"


def preferred_serbian(profile: TagProfile) -> str:
    names = profile.serbian_names
    return sorted(names, key=lambda value: (len(value), value))[0]


def build_candidates() -> dict[str, object]:
    overrides = parse_overrides(ROOT / "registry/raskovnik-overrides.xml")
    profiles, source_records = parse_effective_persj_catalog(
        ROOT / "upstream/persj/670dac4/effective-language-catalog.xml"
    )
    iana_date, iana = parse_iana_registry(
        ROOT / "upstream/iana/2026-08-08/language-subtag-registry"
    )
    iso_by_id, iso_by_part1, iso_by_part2 = parse_iso639_3(
        ROOT / "upstream/iso-639-3/2026-07-22/iso-639-3.tab"
    )
    glottolog, glottolog_by_iso = parse_glottolog(
        ROOT / "upstream/glottolog/5.3/languoid.csv"
    )
    cldr_languages, cldr_territories, cldr_variants = parse_cldr_german(
        ROOT / "upstream/cldr/48.2/de.xml"
    )
    collection_map, ambiguous_collections = collection_glottolog_map(iana, glottolog)

    profile_rows: list[dict[str, object]] = []
    glottocode_to_code: dict[str, str] = {}
    for tag, profile in sorted(profiles.items()):
        validate_registered_tag(tag, iana)
        primary = primary_subtag(tag)
        primary_record = iana.get(("language", primary))
        if primary_record is None:
            raise RuntimeError(f"missing IANA primary record for {tag!r}")
        iso = iso_for_primary(primary, iso_by_id, iso_by_part1, iso_by_part2)
        has_extra_standard_parts = standard_prefix(tag) != primary
        exact_glottolog: GlottologRecord | None = None
        broader_glottolog: GlottologRecord | None = None
        if primary_record.fields.get("Scope") == ("collection",):
            base_glottolog = collection_map.get(primary)
        else:
            base_glottolog = glottolog_by_iso.get(iso.identifier) if iso else None
        if tag == primary:
            exact_glottolog = base_glottolog
        else:
            broader_glottolog = base_glottolog
        if exact_glottolog is not None:
            previous = glottocode_to_code.get(exact_glottolog.glottocode)
            if previous is not None and previous != tag:
                raise RuntimeError(
                    f"Glottolog {exact_glottolog.glottocode} maps to {previous!r} and {tag!r}"
                )
            glottocode_to_code[exact_glottolog.glottocode] = tag
        german, german_source = german_candidate(
            tag, cldr_languages, cldr_territories, cldr_variants
        )
        english = english_candidate(tag, primary_record, exact_glottolog, iana)
        reasons: list[str] = []
        if profile.status == "private":
            reasons.append("private-use-code")
        if primary_record.fields.get("Scope") == ("collection",):
            reasons.append("collection-classification")
        if has_extra_standard_parts:
            reasons.append("nonexact-standard-tag-alignment")
        if exact_glottolog is None:
            reasons.append("no-exact-glottolog-alignment")
        if english is None:
            reasons.append("english-label-required")
        if german is None:
            reasons.append("non-cldr-german-label")
        if len(profile.serbian_names) > 1:
            reasons.append("multiple-serbian-source-meanings")
        alignment = exact_glottolog or broader_glottolog
        lineage = (
            [
                {
                    "glottocode": node.glottocode,
                    "name": node.name,
                    "level": node.level,
                    "canonicalCode": glottocode_to_code.get(node.glottocode),
                }
                for node in glottolog_lineage(alignment, glottolog)
            ]
            if alignment is not None
            else []
        )
        row: dict[str, object] = {
                "id": tag,
                "status": profile.status,
                "kindCandidate": kind_candidate(tag, primary_record, alignment),
                "preferredLabels": {
                    "sr": preferred_serbian(profile),
                    "en": english,
                    "de": german,
                },
                "labelProvenance": {
                    "sr": "persj-conversion-catalog",
                    "en": "glottolog-5.3" if exact_glottolog else "iana-2026-08-08",
                    "de": german_source,
                },
                "serbianCandidates": list(profile.serbian_names),
                "iana": {
                    "primary": primary,
                    "scope": primary_record.fields.get("Scope", ("individual",))[0],
                    "descriptions": list(primary_record.descriptions),
                },
                "iso639": (
                    {
                        "part3": iso.identifier,
                        "part2B": iso.part2b,
                        "part2T": iso.part2t,
                        "part1": iso.part1,
                        "scope": iso.scope,
                        "type": iso.language_type,
                    }
                    if iso is not None
                    else None
                ),
                "glottolog": (
                    {
                        "relationship": "exact" if exact_glottolog else "broader",
                        "glottocode": alignment.glottocode,
                        "name": alignment.name,
                        "level": alignment.level,
                        "latitude": alignment.latitude,
                        "longitude": alignment.longitude,
                    }
                    if alignment is not None
                    else None
                ),
                "lineage": lineage,
                "sourceRecordIds": [record.identifier for record in profile.source_records],
                "reviewReasons": sorted(set(reasons)),
                "approval": None,
            }
        override = overrides.nodes.get(tag)
        if override is not None:
            row["kindCandidate"] = override.kind
            row["preferredLabels"] = {
                language: override.names[language].value
                for language in ("sr", "en", "de")
            }
            row["labelProvenance"] = {
                language: override.names[language].source
                for language in ("sr", "en", "de")
            }
            row["approval"] = {
                "status": override.review_status,
                "reviewedBy": override.reviewed_by,
                "reviewedOn": override.reviewed_on,
                "reasons": list(override.reasons),
            }
        profile_rows.append(row)

    reverse_collection_map = {
        record.glottocode: code for code, record in collection_map.items()
    }
    for glottocode, override in overrides.nodes_by_glottocode.items():
        if glottocode not in glottolog:
            raise RuntimeError(
                f"approved override {override.ident!r} references unknown Glottocode {glottocode!r}"
            )
        previous = glottocode_to_code.get(glottocode) or reverse_collection_map.get(glottocode)
        if previous is not None and previous != override.ident:
            raise RuntimeError(
                f"approved override {override.ident!r} conflicts with automatic code {previous!r}"
            )
        glottocode_to_code[glottocode] = override.ident
    for row in profile_rows:
        for lineage_node in row["lineage"]:
            lineage_node["canonicalCode"] = (
                glottocode_to_code.get(lineage_node["glottocode"])
                or reverse_collection_map.get(lineage_node["glottocode"])
            )

    ancestor_glottocodes: set[str] = set()
    for row in profile_rows:
        for lineage_node in row["lineage"]:
            ancestor_glottocodes.add(lineage_node["glottocode"])
    ancestor_rows: list[dict[str, object]] = []
    for glottocode in sorted(ancestor_glottocodes):
        record = glottolog[glottocode]
        code = glottocode_to_code.get(glottocode) or reverse_collection_map.get(glottocode)
        override = overrides.nodes_by_glottocode.get(glottocode)
        ancestor_rows.append(
            {
                "glottocode": glottocode,
                "name": record.name,
                "level": record.level,
                "parentGlottocode": record.parent_id,
                "canonicalCodeCandidate": code,
                "reviewReasons": [] if code else ["canonical-ancestor-code-required"],
                "approval": (
                    {
                        "status": override.review_status,
                        "reviewedBy": override.reviewed_by,
                        "reviewedOn": override.reviewed_on,
                        "reasons": list(override.reasons),
                    }
                    if override is not None
                    else None
                ),
            }
        )

    return {
        "schema": "language-registry-candidates-v1",
        "sources": {
            "persjCommit": "670dac4d45a2762f34597860c9bf8c080b3cbee3",
            "ianaFileDate": iana_date,
            "glottologVersion": "5.3",
            "cldrVersion": "48.2",
            "iso6393Snapshot": "2026-07-22",
        },
        "summary": {
            "tagProfiles": len(profile_rows),
            "sourceRecords": len(source_records),
            "profileExceptions": sum(
                bool(row["reviewReasons"]) and row["approval"] is None
                for row in profile_rows
            ),
            "ancestorNodes": len(ancestor_rows),
            "ancestorExceptions": sum(
                bool(row["reviewReasons"]) and row["approval"] is None
                for row in ancestor_rows
            ),
            "ambiguousCollectionMappings": len(ambiguous_collections),
        },
        "profiles": profile_rows,
        "ancestorCandidates": ancestor_rows,
        "ambiguousCollectionMappings": {
            code: [
                {"glottocode": record.glottocode, "name": record.name}
                for record in records
            ]
            for code, records in sorted(ambiguous_collections.items())
        },
    }


def write_outputs(data: dict[str, object], output: Path, review: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with review.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "recordType",
                "id",
                "kind",
                "parentOrLineage",
                "labelSr",
                "labelEn",
                "labelDe",
                "externalAlignment",
                "reviewReasons",
                "approval",
            ]
        )
        for row in data["profiles"]:
            if not row["reviewReasons"] or row["approval"] is not None:
                continue
            glottolog = row["glottolog"]
            alignment = (
                f"{glottolog['relationship']}:{glottolog['glottocode']}"
                if glottolog
                else ""
            )
            writer.writerow(
                [
                    "tag-profile",
                    row["id"],
                    row["kindCandidate"],
                    " > ".join(node["name"] for node in row["lineage"]),
                    row["preferredLabels"]["sr"],
                    row["preferredLabels"]["en"] or "",
                    row["preferredLabels"]["de"] or "",
                    alignment,
                    ",".join(row["reviewReasons"]),
                    "PENDING",
                ]
            )
        for row in data["ancestorCandidates"]:
            if not row["reviewReasons"] or row["approval"] is not None:
                continue
            writer.writerow(
                [
                    "ancestor",
                    row["glottocode"],
                    row["level"],
                    row["parentGlottocode"] or "",
                    "",
                    row["name"],
                    "",
                    f"exact:{row['glottocode']}",
                    ",".join(row["reviewReasons"]),
                    "PENDING",
                ]
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = build_candidates()
    if args.check:
        with tempfile.TemporaryDirectory(prefix="raskovnik-registry-candidates-") as directory:
            candidate_output = Path(directory) / "registry-candidates.json"
            candidate_review = Path(directory) / "editorial-review.tsv"
            write_outputs(data, candidate_output, candidate_review)
            stale = [
                path
                for path, candidate in (
                    (args.output, candidate_output),
                    (args.review, candidate_review),
                )
                if not path.is_file() or path.read_bytes() != candidate.read_bytes()
            ]
            if stale:
                raise RuntimeError(
                    "generated candidate artifacts are stale: "
                    + ", ".join(str(path) for path in stale)
                )
        return 0
    write_outputs(data, args.output, args.review)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
