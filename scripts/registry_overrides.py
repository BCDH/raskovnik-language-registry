#!/usr/bin/env python3
"""Parser and hard editorial gate for reviewed registry overrides."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from registry_sources import XML_NS, canonical_language_tag, normalized


OVERRIDE_NS = "https://raskovnik.org/ns/language-registry/overrides"
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
LABEL_SOURCES = frozenset(
    {
        "glottolog-5.3",
        "cldr-48.2",
        "iana-2026-08-08",
        "persj-conversion-catalog",
        "raskovnik-review",
    }
)


class RegistryOverrideError(RuntimeError):
    """Raised when editorial overrides do not satisfy the release gate."""


@dataclass(frozen=True)
class ReviewedName:
    language: str
    value: str
    source: str


@dataclass(frozen=True)
class ReviewedNode:
    ident: str
    kind: str
    parent: str | None
    selectable: bool
    alignment: str
    glottocode: str | None
    wikidata: str | None
    wikidata_explicit: bool
    review_status: str
    reviewed_by: str
    reviewed_on: str
    names: dict[str, ReviewedName]
    aliases: dict[str, tuple[ReviewedName, ...]]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RegistryOverrides:
    version: str
    nodes: dict[str, ReviewedNode]
    nodes_by_glottocode: dict[str, ReviewedNode]


def parse_overrides(path: Path, *, require_approved: bool = True) -> RegistryOverrides:
    root = ET.parse(path).getroot()
    if root.tag != f"{{{OVERRIDE_NS}}}registryOverrides" or root.get("formatVersion") != "1":
        raise RegistryOverrideError("unexpected registry override document")
    version = normalized(root.get("registryVersion", ""))
    if not version:
        raise RegistryOverrideError("registry override version is required")
    nodes: dict[str, ReviewedNode] = {}
    nodes_by_glottocode: dict[str, ReviewedNode] = {}
    nodes_by_wikidata: dict[str, ReviewedNode] = {}
    for node in root.findall(f"{{{OVERRIDE_NS}}}node"):
        ident = canonical_language_tag(node.get("ident", ""))
        kind = node.get("kind", "")
        parent = node.get("parent")
        if parent:
            parent = canonical_language_tag(parent)
        selectable_text = node.get("selectable", "")
        alignment = node.get("alignment", "")
        glottocode = node.get("glottocode")
        wikidata = node.get("wikidata") or None
        review_status = node.get("reviewStatus", "")
        reviewed_by = normalized(node.get("reviewedBy", ""))
        reviewed_on = node.get("reviewedOn", "")
        if ident in nodes:
            raise RegistryOverrideError(f"duplicate override {ident!r}")
        if kind not in NODE_KINDS:
            raise RegistryOverrideError(f"invalid node kind for {ident!r}")
        if selectable_text not in {"true", "false"}:
            raise RegistryOverrideError(f"invalid selectable value for {ident!r}")
        if alignment not in {"exact", "broader", "none"}:
            raise RegistryOverrideError(f"invalid alignment for {ident!r}")
        if alignment == "none" and glottocode:
            raise RegistryOverrideError(f"unaligned node {ident!r} has a Glottocode")
        if alignment != "none" and not glottocode:
            raise RegistryOverrideError(f"aligned node {ident!r} lacks a Glottocode")
        if wikidata is not None and re.fullmatch(r"Q[1-9][0-9]*", wikidata) is None:
            raise RegistryOverrideError(f"invalid Wikidata QID for {ident!r}")
        if review_status not in {"approved", "pending"}:
            raise RegistryOverrideError(f"invalid review status for {ident!r}")
        if require_approved and review_status != "approved":
            raise RegistryOverrideError(f"pending override blocks release: {ident}")
        if not reviewed_by or not reviewed_on:
            raise RegistryOverrideError(f"review provenance is incomplete for {ident!r}")
        names: dict[str, ReviewedName] = {}
        for name_node in node.findall(f"{{{OVERRIDE_NS}}}name"):
            language = name_node.get(f"{{{XML_NS}}}lang", "")
            source = name_node.get("source", "")
            value = normalized(name_node.text or "")
            if language not in {"sr", "en", "de"} or language in names or (not value and (selectable_text == "true" or language == "en")):
                raise RegistryOverrideError(f"invalid preferred name for {ident!r}")
            if source not in LABEL_SOURCES:
                raise RegistryOverrideError(f"invalid name provenance for {ident!r}")
            names[language] = ReviewedName(language, value, source)
        if set(names) != {"sr", "en", "de"}:
            raise RegistryOverrideError(f"trilingual preferred names required for {ident!r}")
        aliases: dict[str, list[ReviewedName]] = {language: [] for language in ("sr", "en", "de")}
        seen_aliases: set[tuple[str, str]] = set()
        for alias_node in node.findall(f"{{{OVERRIDE_NS}}}alias"):
            language = alias_node.get(f"{{{XML_NS}}}lang", "")
            source = alias_node.get("source", "")
            value = normalized(alias_node.text or "")
            key = (language, value.casefold())
            if (
                language not in aliases
                or source not in LABEL_SOURCES
                or not value
                or key in seen_aliases
                or value.casefold() == names[language].value.casefold()
            ):
                raise RegistryOverrideError(f"invalid alias for {ident!r}")
            seen_aliases.add(key)
            aliases[language].append(ReviewedName(language, value, source))
        reasons = tuple(
            normalized(reason.text or "")
            for reason in node.findall(f"{{{OVERRIDE_NS}}}note[@type='reviewReason']")
        )
        if not reasons or any(not reason for reason in reasons):
            raise RegistryOverrideError(f"review reason required for {ident!r}")
        reviewed = ReviewedNode(
            ident,
            kind,
            parent,
            selectable_text == "true",
            alignment,
            glottocode,
            wikidata,
            "wikidata" in node.attrib,
            review_status,
            reviewed_by,
            reviewed_on,
            names,
            {
                language: tuple(values)
                for language, values in aliases.items()
            },
            reasons,
        )
        nodes[ident] = reviewed
        if glottocode and alignment == "exact":
            previous = nodes_by_glottocode.get(glottocode)
            if previous is not None and previous.ident != ident:
                raise RegistryOverrideError(
                    f"Glottocode {glottocode!r} is claimed by {previous.ident!r} and {ident!r}"
                )
            nodes_by_glottocode[glottocode] = reviewed
        if wikidata:
            previous = nodes_by_wikidata.get(wikidata)
            if previous is not None and previous.ident != ident:
                raise RegistryOverrideError(
                    f"Wikidata QID {wikidata!r} is claimed by {previous.ident!r} and {ident!r}"
                )
            nodes_by_wikidata[wikidata] = reviewed
    return RegistryOverrides(version, nodes, nodes_by_glottocode)


def approved_iso_scope_exceptions(root: Path, *, ledger_path: Path | None = None) -> frozenset[tuple[str, str, str]]:
    """Authorize only ledger-bound, hash-pinned narrower ISO cross-references."""
    import hashlib
    from datetime import date
    path = ledger_path or root / "registry/raskovnik-overrides.xml"
    if not path.exists():
        return frozenset()
    tree = ET.parse(path).getroot()
    ns = "{" + OVERRIDE_NS + "}"
    nodes = {n.get("ident"): n for n in tree.findall(ns + "node")}
    result = set()
    required_evidence = {
        "upstream/glottolog/5.3/languoid.csv",
        "upstream/iso-639-3/2026-07-22/iso-639-3.tab",
    }
    for item in tree.findall(ns + "isoScopeException"):
        key = (item.get("node"), item.get("glottocode"), item.get("iso6393"))
        node = nodes.get(key[0])
        if (key in result or item.get("relationship") != "narrower"
            or item.get("reviewStatus") != "approved" or not item.get("reviewedBy")
            or node is None or node.get("reviewStatus") != "approved"
            or node.get("alignment") != "exact" or node.get("glottocode") != key[1]
            or not normalized(item.findtext(ns + "rationale", ""))):
            raise RegistryOverrideError("invalid or unapproved ISO scope exception: " + str(key))
        try:
            date.fromisoformat(item.get("reviewedOn", ""))
        except ValueError as exc:
            raise RegistryOverrideError("invalid ISO scope review date") from exc
        evidence = item.findall(ns + "evidence")
        if {e.get("path") for e in evidence} != required_evidence or len(evidence) != 2:
            raise RegistryOverrideError("ISO scope exception requires pinned Glottolog and ISO evidence")
        for e in evidence:
            if hashlib.sha256((root / e.get("path")).read_bytes()).hexdigest() != e.get("sha256"):
                raise RegistryOverrideError("stale ISO scope exception evidence")
        from registry_sources import parse_glottolog, parse_iso639_3
        glot, _ = parse_glottolog(root / "upstream/glottolog/5.3/languoid.csv")
        iso, _, _ = parse_iso639_3(root / "upstream/iso-639-3/2026-07-22/iso-639-3.tab")
        if key[1] not in glot or key[2] not in iso or glot[key[1]].iso639_3 != key[2]:
            raise RegistryOverrideError("ISO scope exception no longer matches pinned cross-reference")
        result.add(key)
    return frozenset(result)
