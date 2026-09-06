#!/usr/bin/env python3
"""Fail a release while any generated registry exception remains unapproved."""

from __future__ import annotations

import argparse
import csv
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "dist/editorial-review.tsv"


class EditorialGateError(RuntimeError):
    """Raised when the exception-only editorial queue is not closed."""


def pending_records(path: Path) -> tuple[dict[str, str], ...]:
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source, delimiter="\t")
        expected = {
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
        }
        if reader.fieldnames is None or set(reader.fieldnames) != expected:
            raise EditorialGateError("unexpected editorial report columns")
        pending = []
        for row in reader:
            if row["approval"] != "PENDING":
                raise EditorialGateError(
                    f"generated report contains unsupported approval marker for {row['id']!r}"
                )
            if not row["id"] or not row["reviewReasons"]:
                raise EditorialGateError("incomplete editorial exception record")
            pending.append(row)
    return tuple(pending)


def assert_release_ready(path: Path) -> None:
    pending = pending_records(path)
    if pending:
        profile_count = sum(row["recordType"] == "tag-profile" for row in pending)
        ancestor_count = sum(row["recordType"] == "ancestor" for row in pending)
        raise EditorialGateError(
            "editorial review is incomplete: "
            f"tag_profiles={profile_count} ancestors={ancestor_count} total={len(pending)}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    try:
        assert_release_ready(args.report)
        if args.report == DEFAULT_REPORT:
            root = ET.parse(ROOT / "registry/raskovnik-overrides.xml").getroot()
            pending = [r.get("key") for r in root.findall("{https://raskovnik.org/ns/language-registry/overrides}reviewRecord") if r.get("status") == "pending"]
            if pending:
                raise EditorialGateError("unresolved imported decisions: " + ", ".join(pending))
    except (OSError, EditorialGateError) as exc:
        print(f"editorial release gate failed: {exc}", file=sys.stderr)
        return 1
    print("editorial release gate passed: no pending exceptions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
