# Raskovnik Language Registry

This public repository builds the versioned language-classification package shared by Raskovnik dictionaries. It contains classification, names, identifiers, corpus-label mappings, and provenance. It does not contain dictionary entries, forms, evidence flags, corpus counts, coverage, or map attestation.

The released eXist XAR installs `registry.xml` and `manifest.xml` at `/db/apps/raskovnik-data/metadata/languages`. Dictionary-scoped evidence remains in the backend and is protected by each dictionary's visibility policy.

## Source layers

- `upstream/` contains immutable, checksum-locked public inputs: Glottolog 5.3, Unicode CLDR 48.2, IANA's 2026-08-08 Language Subtag Registry, the 2026-07-22 ISO 639-3 table, and a count-free mapping export from the PERSJ conversion at commit `670dac4d45a2762f34597860c9bf8c080b3cbee3`.
- `registry/raskovnik-overrides.xml` records reviewed project labels, codes, lineages, and nonexact alignments. Pending linguistic judgments are not silently promoted into the effective registry.
- `dist/registry-candidates.json` and `dist/editorial-review.tsv` are deterministic review artifacts. `dist/registry.xml` and `dist/manifest.xml` will become the release inputs after the editorial gate closes.

Ordinary builds are offline. Network acquisition and PERSJ conversion export are separate operator actions; `make check` never fetches moving upstream data or depends on a sibling checkout.

## Checks

```sh
make candidates
make check
```

`make check` verifies every pinned byte and SHA-256, validates the override format, regenerates candidate artifacts for a byte comparison, runs the test suite, and validates the Maven project offline.

The release gate is intentionally stricter:

```sh
make editorial-gate
make package
```

`make editorial-gate` fails while any exception remains in `dist/editorial-review.tsv`. `make package` cannot run until that gate passes, so an incomplete or unreviewed classification cannot produce a release XAR.

To compare the public PERSJ mapping snapshot with the exact local conversion source, run:

```sh
python3 scripts/import-persj.py --source /path/to/new-conversions4raskovnik/PERSJ --check
```

The importer verifies the pinned source hashes and deliberately strips compound occurrence counts from the public mapping export.

## Package contract

The package URI is `http://raskovnik.org/raskovnik-language-registry`; it depends on `raskovnik-data-core >= 2026.6.6-1`. The XAR contains only the effective `registry.xml`, `manifest.xml`, `post-install.xq`, and generated EXPath descriptors. Registry releases are published from this repository and pinned by compatible backend release sets; generated registry data is not copied into the backend repository.
