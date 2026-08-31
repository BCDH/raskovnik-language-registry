#!/usr/bin/env python3
"""Create or verify the public, count-free PERSJ mapping snapshot."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

from registry_sources import (
    REGISTRY_SOURCE_NS,
    XML_NS,
    parse_persj_profiles,
    sha256,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(
    "/Users/ttasovac/Development/ttasovac/new-conversions4raskovnik/PERSJ"
)
DEFAULT_OUTPUT = ROOT / "upstream/persj/670dac4/effective-language-catalog.xml"
SOURCE_COMMIT = "670dac4d45a2762f34597860c9bf8c080b3cbee3"
CATALOG_PATH = Path("resources/example-language-tags.xml")
EXTENSIONS_PATH = Path("resources/etymon-language-extensions.xml")
CATALOG_SHA256 = "ea852f0b07a053aba5b473b54845b5b9daf61f0a2c0ffaca06a8cffb17e1d84c"
EXTENSIONS_SHA256 = "743f455c3e60f6889ff32c1c88cde466181ded5e447c4fb3be9a76bf770d0cf5"


def build_tree(source: Path) -> ET.ElementTree:
    catalog = source / CATALOG_PATH
    extensions = source / EXTENSIONS_PATH
    actual_catalog_hash = sha256(catalog)
    actual_extensions_hash = sha256(extensions)
    if actual_catalog_hash != CATALOG_SHA256:
        raise RuntimeError(
            f"PERSJ base catalog hash mismatch: {actual_catalog_hash}"
        )
    if actual_extensions_hash != EXTENSIONS_SHA256:
        raise RuntimeError(
            f"PERSJ extension catalog hash mismatch: {actual_extensions_hash}"
        )
    profiles, _records = parse_persj_profiles(catalog, extensions)
    ET.register_namespace("", REGISTRY_SOURCE_NS)
    root = ET.Element(
        f"{{{REGISTRY_SOURCE_NS}}}effectiveLanguageCatalog",
        {
            "formatVersion": "1",
            "sourceRepository": "new-conversions4raskovnik/PERSJ",
            "sourceCommit": SOURCE_COMMIT,
            "sourceCatalogPath": str(CATALOG_PATH),
            "sourceCatalogSha256": CATALOG_SHA256,
            "sourceExtensionsPath": str(EXTENSIONS_PATH),
            "sourceExtensionsSha256": EXTENSIONS_SHA256,
        },
    )
    for tag, profile in sorted(profiles.items()):
        profile_node = ET.SubElement(
            root,
            f"{{{REGISTRY_SOURCE_NS}}}tagProfile",
            {"ident": tag, "status": profile.status},
        )
        for record in profile.source_records:
            record_node = ET.SubElement(
                profile_node,
                f"{{{REGISTRY_SOURCE_NS}}}sourceRecord",
                {f"{{{XML_NS}}}id": record.identifier, "kind": record.kind},
            )
            source_label = ET.SubElement(
                record_node,
                f"{{{REGISTRY_SOURCE_NS}}}name",
                {f"{{{XML_NS}}}lang": "sr", "type": "sourceLabel"},
            )
            source_label.text = record.label
            meaning = ET.SubElement(
                record_node,
                f"{{{REGISTRY_SOURCE_NS}}}name",
                {f"{{{XML_NS}}}lang": "sr", "type": "meaning"},
            )
            meaning.text = record.meaning_sr
            if record.reason:
                note = ET.SubElement(
                    record_node,
                    f"{{{REGISTRY_SOURCE_NS}}}note",
                    {"type": "reason"},
                )
                note.text = record.reason
    ET.indent(root, space="  ")
    return ET.ElementTree(root)


def serialize(tree: ET.ElementTree, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(path, encoding="utf-8", xml_declaration=True, short_empty_elements=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    tree = build_tree(args.source)
    if args.check:
        with tempfile.TemporaryDirectory(prefix="raskovnik-persj-import-") as directory:
            candidate = Path(directory) / "effective-language-catalog.xml"
            serialize(tree, candidate)
            if not args.output.is_file() or candidate.read_bytes() != args.output.read_bytes():
                raise RuntimeError(
                    f"{args.output} is stale; regenerate it with scripts/import-persj.py"
                )
        return 0
    serialize(tree, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
