# Repository guidance

This repository owns the public, versioned Raskovnik language registry and its eXist XAR. It does not own dictionary evidence, entries, forms, counts, coverage, or dictionary authorization.

Normal builds are offline. Do not replace a pinned source with a moving URL, edit immutable files under `upstream/`, or bypass `scripts/check-inputs.py`. Refresh an upstream source as an explicit reviewed change and update its exact size, SHA-256, revision, licence, and attribution in `upstream/sources.json`.

The PERSJ source mapping checked into `upstream/` is deliberately count-free. Regenerate or compare it with `scripts/import-persj.py`; never copy the conversion extension file containing occurrence counts into this public repository.

Do not hand-edit generated files under `dist/`. Run `make candidates` and then `make check`. A release is not ready while `make editorial-gate` fails. Never add placeholder labels, inferred lineages, invented Glottolog equivalences, or implicit approvals merely to close that gate.

`registry/raskovnik-overrides.xml` is the durable editorial decision ledger. Every private-use code, reconstruction, collective, disputed or nonexact alignment, uncoded ancestor, and non-CLDR German label must remain blocked until its trilingual labels, lineage, provenance, rationale, reviewer, and review date are recorded there.

The release XAR must contain only `registry.xml`, `manifest.xml`, `post-install.xq`, and generated EXPath descriptors. It installs under `/db/apps/raskovnik-data/metadata/languages` and depends on `raskovnik-data-core`. Registry release artifacts are published from this repository and consumed by exact backend release-set pins; do not copy generated registry data into `raskovnik-backend`.
