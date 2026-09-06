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
    parse_wikidata_evidence,
    primary_subtag,
    standard_prefix,
    validate_registered_tag,
)
from registry_overrides import parse_overrides, approved_iso_scope_exceptions


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dist/registry-candidates.json"
DEFAULT_REVIEW = ROOT / "dist/editorial-review.tsv"
PERSJ_COMMIT = "a258c532c1037b9550d22154ccd9f34cef1a2073"
PERSJ_SNAPSHOT = ROOT / "upstream/persj/a258c53/effective-language-catalog.xml"


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


def deterministic_ancestor_code(glottocode: str) -> str:
    """Return the policy-owned BCP 47 identifier for an uncoded structural node."""
    return f"und-x-glot-{glottocode}"


def validate_reviewed_wikidata_assignment(
    *,
    ident: str,
    qid: str,
    items: dict[str, object],
    alignment: GlottologRecord | None,
    iso: Iso6393Record | None,
    relationship: str = "exact",
) -> object:
    """Resolve a reviewed semantic QID and reject every structured-claim conflict."""
    item = items.get(qid)
    if item is None:
        raise RuntimeError(
            f"reviewed Wikidata assignment {qid!r} for {ident!r} is absent from the pinned evidence snapshot"
        )
    private = "-x-" in ident
    exact_bridge = alignment is not None and alignment.glottocode in item.glottocodes
    if item.ietf_tags and not private and ident.casefold() not in {
        value.casefold() for value in item.ietf_tags
    }:
        raise RuntimeError(
            f"reviewed Wikidata assignment {qid!r} conflicts with tag {ident!r}"
        )
    alignment_codes = set(item.glottocodes)
    if relationship == "broader":
        records, _ = parse_glottolog(ROOT / "upstream/glottolog/5.3/languoid.csv")
        for code in item.glottocodes:
            if code in records:
                alignment_codes.update(n.glottocode for n in glottolog_lineage(records[code], records))
    if item.glottocodes and (
        alignment is None or alignment.glottocode not in alignment_codes
    ):
        raise RuntimeError(
            f"reviewed Wikidata assignment {qid!r} conflicts with the Glottolog alignment for {ident!r}"
        )
    if item.iso639_3 and "-" not in ident and (
        iso is None or iso.identifier not in item.iso639_3
    ):
        raise RuntimeError(
            f"reviewed Wikidata assignment {qid!r} conflicts with the ISO 639-3 identity for {ident!r}"
        )
    return item


def build_candidates(*, overrides_path: Path | None = None) -> dict[str, object]:
    ledger_path = overrides_path or ROOT / "registry/raskovnik-overrides.xml"
    overrides = parse_overrides(ledger_path)
    scope_exceptions = approved_iso_scope_exceptions(ROOT, ledger_path=ledger_path)
    profiles, source_records = parse_effective_persj_catalog(PERSJ_SNAPSHOT)
    iana_date, iana = parse_iana_registry(
        ROOT / "upstream/iana/2026-08-08/language-subtag-registry"
    )
    iso_by_id, iso_by_part1, iso_by_part2 = parse_iso639_3(
        ROOT / "upstream/iso-639-3/2026-07-22/iso-639-3.tab"
    )
    glottolog, glottolog_by_iso = parse_glottolog(
        ROOT / "upstream/glottolog/5.3/languoid.csv"
    )
    wikidata, wikidata_by_glottocode, wikidata_by_iso, wikidata_by_ietf = parse_wikidata_evidence(
        ROOT / "upstream/wikidata/2026-09-06/language-items.json"
    )
    cldr_languages, cldr_territories, cldr_variants = parse_cldr_german(
        ROOT / "upstream/cldr/48.2/de.xml"
    )
    collection_map, ambiguous_collections = collection_glottolog_map(iana, glottolog)

    profile_rows: list[dict[str, object]] = []
    glottocode_to_code: dict[str, str] = {}
    for tag, profile in sorted(profiles.items()):
        override = overrides.nodes.get(tag)
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
        ietf_item = wikidata_by_ietf.get(tag.casefold())
        iso_item = wikidata_by_iso.get(iso.identifier) if tag == primary and iso is not None else None
        identity_item = (
            None
            if ietf_item is not None and iso_item is not None and ietf_item.qid != iso_item.qid
            else ietf_item or iso_item
        )
        if identity_item is not None:
            claimed = [glottolog[code] for code in identity_item.glottocodes if code in glottolog]
            compatible = [
                record
                for record in claimed
                if (
                    primary_record.fields.get("Scope") == ("collection",)
                    and record.level == "family"
                    or primary_record.fields.get("Scope") != ("collection",)
                    and record.level != "family"
                )
            ]
            if len(compatible) == 1:
                exact_glottolog = compatible[0]
                broader_glottolog = None
        if override is not None:
            if override.alignment == "none":
                exact_glottolog = None
                broader_glottolog = None
            else:
                reviewed_alignment = glottolog.get(override.glottocode or "")
                if reviewed_alignment is None:
                    raise RuntimeError(
                        f"approved override {tag!r} references unknown Glottocode {override.glottocode!r}"
                    )
                exact_glottolog = (
                    reviewed_alignment if override.alignment == "exact" else None
                )
                broader_glottolog = (
                    reviewed_alignment if override.alignment == "broader" else None
                )
        if exact_glottolog is not None:
            previous = glottocode_to_code.get(exact_glottolog.glottocode)
            if previous is not None and previous != tag:
                raise RuntimeError(
                    f"Glottolog {exact_glottolog.glottocode} maps to {previous!r} and {tag!r}"
                )
            glottocode_to_code[exact_glottolog.glottocode] = tag
        wikidata_item = identity_item
        if exact_glottolog is not None:
            glottolog_item = wikidata_by_glottocode.get(exact_glottolog.glottocode)
            if wikidata_item is not None and glottolog_item is not None and wikidata_item.qid != glottolog_item.qid:
                raise RuntimeError(
                    f"conflicting Wikidata IETF/Glottolog claims for {tag!r}: "
                    f"{wikidata_item.qid} and {glottolog_item.qid}"
                )
            wikidata_item = wikidata_item or glottolog_item
        if tag == primary and iso is not None:
            if identity_item is not None and ietf_item is None and wikidata_item is not None and iso_item is not None and wikidata_item.qid != iso_item.qid:
                raise RuntimeError(
                    f"conflicting Wikidata Glottolog/ISO claims for {tag!r}: "
                    f"{wikidata_item.qid} and {iso_item.qid}"
                )
            wikidata_item = wikidata_item or iso_item
        if override is not None and override.wikidata_explicit:
            wikidata_item = None
        if override is not None and override.wikidata is not None:
            reviewed_item = validate_reviewed_wikidata_assignment(
                ident=tag,
                qid=override.wikidata,
                items=wikidata,
                alignment=exact_glottolog or broader_glottolog,
                iso=iso,
                relationship=override.alignment,
            )
            if wikidata_item is not None and wikidata_item.qid != reviewed_item.qid:
                raise RuntimeError(
                    f"reviewed Wikidata assignment for {tag!r} conflicts with exact structured claims: "
                    f"{override.wikidata} and {wikidata_item.qid}"
                )
            wikidata_item = reviewed_item
        if (override is None or not override.wikidata_explicit) and exact_glottolog is not None and wikidata_item is not None and wikidata_item.glottocodes and exact_glottolog.glottocode not in wikidata_item.glottocodes:
            # A broader Wikidata claim is not an exact identity for the ISO-linked node.
            wikidata_item = None
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
                "parentCandidate": None,
                "selectableCandidate": True,
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
                "aliasCandidates": {"sr": [], "en": [], "de": []},
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
                "wikidataQidCandidate": wikidata_item.qid if wikidata_item else None,
                "lineage": lineage,
                "sourceRecordIds": [record.identifier for record in profile.source_records],
                "reviewReasons": sorted(set(reasons)),
                "approval": None,
            }
        if override is not None:
            row["kindCandidate"] = override.kind
            row["parentCandidate"] = override.parent
            row["selectableCandidate"] = override.selectable
            row["preferredLabels"] = {
                language: override.names[language].value or None
                for language in ("sr", "en", "de")
            }
            row["labelProvenance"] = {
                language: override.names[language].source if override.names[language].value else None
                for language in ("sr", "en", "de")
            }
            row["aliasCandidates"] = {
                language: [
                    {"value": alias.value, "source": alias.source}
                    for alias in override.aliases[language]
                ]
                for language in ("sr", "en", "de")
            }
            row["approval"] = {
                "status": override.review_status,
                "reviewedBy": override.reviewed_by,
                "reviewedOn": override.reviewed_on,
                "reasons": list(override.reasons),
            }
        # The 2026-09-06 source-label split is authorized; finer identities and
        # German labels remain proposals, never implicit editorial approvals.
        if override is None and tag in {"os", "ira-x-ossetic"}:
            row["reviewReasons"] = sorted(set(row["reviewReasons"]) | {"non-cldr-german-label"})
            row["labelProvenance"]["de"] = "ossetian-split-proposal-2026-09-06"
            if tag == "os":
                row["preferredLabels"]["de"] = "Iron-Ossetisch"
            else:
                if "Q33968" not in wikidata:
                    raise RuntimeError("generic Ossetian proposal requires pinned Q33968 evidence")
                row["preferredLabels"].update({"en": "Ossetian", "de": "Ossetisch"})
                row["labelProvenance"]["en"] = "ossetian-split-proposal-2026-09-06"
                row["kindCandidate"] = "language"
                row["parentCandidate"] = "ira"
                row["glottolog"] = None
                row["lineage"] = []
                row["wikidataQidCandidate"] = "Q33968"
                row["reviewReasons"] = sorted(set(row["reviewReasons"]) | {"wikidata-scope-review", "lineage-review-required"})
                row["reviewReasons"].remove("english-label-required")
        if exact_glottolog is not None and exact_glottolog.iso639_3 in iso_by_id and tag == primary and iso is not None and iso.identifier != exact_glottolog.iso639_3:
            row["reviewReasons"] = sorted(set(row["reviewReasons"]) | {"exact-iso-scope-mismatch"})
            row["approval"] = None
        if exact_glottolog is not None and tag != primary and exact_glottolog.iso639_3 in iso_by_id:
            if (tag, exact_glottolog.glottocode, exact_glottolog.iso639_3) not in scope_exceptions:
                row["reviewReasons"] = sorted(set(row["reviewReasons"]) | {"exact-iso-scope-review"})
                row["approval"] = None
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
    for glottocode in ancestor_glottocodes:
        if glottocode not in glottocode_to_code and glottocode not in reverse_collection_map:
            glottocode_to_code[glottocode] = deterministic_ancestor_code(glottocode)
    for row in profile_rows:
        for lineage_node in row["lineage"]:
            lineage_node["canonicalCode"] = (
                glottocode_to_code.get(lineage_node["glottocode"])
                or reverse_collection_map.get(lineage_node["glottocode"])
            )
    ancestor_rows: list[dict[str, object]] = []
    for glottocode in sorted(ancestor_glottocodes):
        record = glottolog[glottocode]
        code = glottocode_to_code.get(glottocode) or reverse_collection_map.get(glottocode)
        override = overrides.nodes_by_glottocode.get(glottocode)
        ancestor_primary = primary_subtag(code) if code is not None else None
        ancestor_iana = (
            iana.get(("language", ancestor_primary)) if ancestor_primary is not None else None
        )
        ancestor_iso = (
            iso_for_primary(ancestor_primary, iso_by_id, iso_by_part1, iso_by_part2)
            if ancestor_primary is not None
            else None
        )
        ancestor_rows.append(
            {
                "glottocode": glottocode,
                "name": record.name,
                "level": record.level,
                "parentGlottocode": record.parent_id,
                "canonicalCodeCandidate": code,
                "ianaScope": (
                    ancestor_iana.fields.get("Scope", ("individual",))[0]
                    if ancestor_iana is not None and code == ancestor_primary
                    else None
                ),
                "iso639": (
                    {
                        "part3": ancestor_iso.identifier,
                        "part2B": ancestor_iso.part2b,
                        "part2T": ancestor_iso.part2t,
                        "part1": ancestor_iso.part1,
                    }
                    if ancestor_iso is not None and code == ancestor_primary
                    else None
                ),
                "kindCandidate": override.kind if override is not None else "variety" if record.level == "dialect" else record.level,
                "parentCandidate": override.parent if override is not None else None,
                "selectableCandidate": override.selectable if override is not None else False,
                "preferredLabels": (
                    {
                        language: override.names[language].value or None
                        for language in ("sr", "en", "de")
                    }
                    if override is not None
                    else {"sr": None, "en": record.name, "de": None}
                ),
                "labelProvenance": (
                    {
                        language: override.names[language].source if override.names[language].value else None
                        for language in ("sr", "en", "de")
                    }
                    if override is not None
                    else {"sr": None, "en": "glottolog-5.3", "de": None}
                ),
                "aliasCandidates": (
                    {
                        language: [
                            {"value": alias.value, "source": alias.source}
                            for alias in override.aliases[language]
                        ]
                        for language in ("sr", "en", "de")
                    }
                    if override is not None
                    else {"sr": [], "en": [], "de": []}
                ),
                "wikidataQidCandidate": None,
                "reviewReasons": ([] if override is not None else ["ancestor-review-required"]) + ([] if code else ["canonical-ancestor-code-required"]),
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
        ancestor = ancestor_rows[-1]
        automatic_item = wikidata_by_glottocode.get(glottocode)
        if override is not None and override.wikidata is not None:
            reviewed_item = validate_reviewed_wikidata_assignment(
                ident=override.ident,
                qid=override.wikidata,
                items=wikidata,
                alignment=record,
                iso=iso_for_primary(
                    primary_subtag(override.ident), iso_by_id, iso_by_part1, iso_by_part2
                ),
            )
            if automatic_item is not None and automatic_item.qid != reviewed_item.qid:
                raise RuntimeError(
                    f"reviewed Wikidata assignment for {override.ident!r} conflicts with "
                    f"Glottolog claim {automatic_item.qid}"
                )
            ancestor["wikidataQidCandidate"] = reviewed_item.qid
        elif automatic_item is not None and not (override and override.wikidata_explicit):
            ancestor["wikidataQidCandidate"] = automatic_item.qid

    profile_qids = {p["wikidataQidCandidate"]: p["id"] for p in profile_rows if p["wikidataQidCandidate"]}
    for ancestor in ancestor_rows:
        qid = ancestor["wikidataQidCandidate"]
        if qid in profile_qids and profile_qids[qid] != ancestor["canonicalCodeCandidate"]:
            ancestor["wikidataQidCandidate"] = None
        exact_iso = iso_by_id.get(glottolog[ancestor["glottocode"]].iso639_3)
        if (ancestor["canonicalCodeCandidate"], ancestor["glottocode"], glottolog[ancestor["glottocode"]].iso639_3) in scope_exceptions:
            ancestor["iso639"] = None
        elif exact_iso is not None:
            ancestor["iso639"] = {"part3":exact_iso.identifier,"part2B":exact_iso.part2b,"part2T":exact_iso.part2t,"part1":exact_iso.part1}

    # A profile and its structural occurrence describe one display node. The
    # profile owns its reviewed labels/kind/selectability, including macrolanguages.
    by_code = {p["id"]: p for p in profile_rows}
    for ancestor in ancestor_rows:
        profile = by_code.get(ancestor["canonicalCodeCandidate"])
        if profile is None or not profile.get("glottolog") or profile["glottolog"]["relationship"] != "exact" or profile["glottolog"]["glottocode"] != ancestor["glottocode"]:
            continue
        for key in ("kindCandidate", "parentCandidate", "selectableCandidate", "preferredLabels", "labelProvenance", "aliasCandidates", "wikidataQidCandidate", "reviewReasons", "approval"):
            ancestor[key] = profile[key]
        bare = profile["id"] == profile["iana"]["primary"]
        ancestor["iso639"] = profile["iso639"] if bare else None
        ancestor["ianaScope"] = profile["iana"]["scope"] if bare else None

    return {
        "schema": "language-registry-candidates-v1",
        "sources": {
            "persjCommit": PERSJ_COMMIT,
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
