#!/usr/bin/env python3
"""Create the compact, offline Wikidata language-evidence snapshot."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


QID_RE = re.compile(r"Q[1-9][0-9]*")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--revisions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    revisions = json.loads(args.revisions.read_text(encoding="utf-8"))
    revision_by_qid = {
        page["title"]: {
            "lastRevisionId": page["lastrevid"],
            "lastRevisionTimestamp": page["touched"],
        }
        for page in revisions["query"]["pages"]
    }
    items = []
    seen: set[str] = set()
    for raw in audit["items"]:
        qid = raw["qid"]
        if QID_RE.fullmatch(qid) is None or qid in seen or qid not in revision_by_qid:
            raise SystemExit(f"invalid, duplicate, or revisionless QID: {qid!r}")
        seen.add(qid)
        items.append(
            {
                "qid": qid,
                **revision_by_qid[qid],
                "labels": {language: raw["labels"].get(language) for language in ("sr", "en", "de")},
                "descriptions": {
                    language: raw["descriptions"].get(language)
                    for language in ("sr", "en", "de")
                },
                "claims": {
                    "P1394": sorted(set(raw["glottocodes"])),
                    "P220": sorted(set(raw["iso639_3"])),
                    "P305": sorted(set(raw.get("ietf_tags", []))),
                    "P31": sorted(set(raw["instanceOf"])),
                    "P279": sorted(set(raw["subclassOf"])),
                },
                "sitelinks": {
                    language: raw["sitelinks"].get(language)
                    for language in ("sr", "en", "de")
                },
            }
        )
    payload = {
        "schemaVersion": "raskovnik-wikidata-language-evidence-v1",
        "retrievedOn": audit["retrievedOn"],
        "source": "https://www.wikidata.org/",
        "selectionPolicy": audit["selectionPolicy"],
        "items": sorted(items, key=lambda item: int(item["qid"][1:])),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output} with {len(items)} revision-pinned items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
