# Raskovnik Language Registry

This public repository builds the versioned language-classification package shared by Raskovnik dictionaries. It contains classification, names, identifiers, corpus-label mappings, and provenance. It does not contain dictionary entries, forms, evidence flags, corpus counts, coverage, or map attestation.

The released eXist XAR installs `registry.xml` and `manifest.xml` at `/db/apps/raskovnik-data/metadata/languages`. Dictionary-scoped evidence remains in the backend and is protected by each dictionary's visibility policy.

## Source layers

- `upstream/` contains immutable, checksum-locked public inputs: Glottolog 5.3, Unicode CLDR 48.2, IANA's 2026-08-08 Language Subtag Registry, the 2026-07-22 ISO 639-3 table, and a count-free mapping export from the PERSJ conversion at commit `670dac4d45a2762f34597860c9bf8c080b3cbee3`.
- `registry/source-publication-metadata.json` supplements each pinned upstream source only with its public manifest ID, licence, and attribution. Its upstream records use an exact allowlist and unique IDs; they cannot replace pinned titles, versions, revisions, URLs, or file inventories.
- `registry/raskovnik-overrides.xml` records reviewed project labels, codes, lineages, and nonexact alignments. Pending linguistic judgments are not silently promoted into the effective registry.
- `dist/registry-candidates.json` and `dist/editorial-review.tsv` are deterministic review artifacts. `dist/registry.xml` and `dist/manifest.xml` will become the release inputs after the editorial gate closes.
- `dist/effective-registry-plan.json` is a generated compiler input, not another editable classification. It may be emitted only after the exception report closes and must carry release-approval hashes for the exact candidate inventory, report, override ledger, and complete output-driving plan payload from which it was derived. The payload hash excludes only the approval envelope itself, so adding a node or changing any label, kind, selection state, parentage, lineage, catalog, compatibility, or source-record field invalidates approval.

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

`make registry` runs the same gate, verifies the release plan against its four approval hashes and the pinned standards inputs, compiles deterministic `dist/registry.xml` and `dist/manifest.xml`, and validates the result against the pinned Lex-0 RNG, the Raskovnik Schematron, the manifest RNG, and native referential-integrity checks. `make package` depends on that complete registry build. The Maven `package` lifecycle independently invokes that same fail-closed compiler through a fixed `python3` command before XAR assembly and refuses to assemble an archive unless both validated distribution files exist. The production compiler intentionally checks the editorial queue before looking for `dist/effective-registry-plan.json`; at the current incomplete review stage it therefore fails on the 286 pending decisions and emits neither release artifact.

The compiler has a synthetic, fully approved test plan at `tests/fixtures/approved-registry-plan.json`. It exercises arbitrary display depth, a semantic language represented by `languageGrp`, an ordinary leaf, a registered-base private-use group, a group with direct and descendant tag profiles, exact-case mixed BCP 47 technical IDs, all three classification statuses, alternate lineage references, representative and missing locations, explicit null abbreviations, and compatibility hashes. Its `approval.mode` is `fixture`; the production CLI accepts only `release`, so the fixture cannot be packaged.

## Effective XML contract

The effective document is a complete TEI Lex-0 document. Its display tree is the recursive `languageGrp`/terminal `language` structure under `teiHeader/profileDesc/langUsage`; each node's canonical code is repeated in exactly one direct `ident type="BCP47"` whose `xml:id` is `lang-` plus the canonical code with case preserved. Node kind is direct `@type`, selection is a direct `note type="selectionStatus"`, classification status is a direct `note type="classificationStatus"`, and optional localized uncertainty prose uses direct `note type="classificationNote"` children.

A direct corpus tag profile is explicit rather than inferred from node `@ident`: `note type="tagProfile" subtype="direct" xml:id="profile-CANONICAL-CODE"` repeats that code. A generic standards profile may legitimately have no dictionary-owned source records. Every count-free source record that does exist is a direct `name type="sourceLabel"` with its stable source-record `xml:id`; its whitespace-separated `@ana` points to exactly one profile marker and one dictionary-catalog record. `@subtype="abbreviation"` preserves a string abbreviation, while `@subtype="label-only"` preserves a JSON null abbreviation without discarding the literal searchable source label. Three linked `sourceRecordLabel` names preserve the Serbian, English, and German display labels.

Dictionary catalog identity is explicit and generic. A TEI `bibl type="dictionaryLanguageCatalog"` holds its dictionary ID and provenance source, and the manifest mirrors it as `catalog[@xml:id][@dictionaryId]/source[@ref]`. Backends filter source records by their catalog reference rather than inferring a dictionary from a source-name convention. Classification sources, label sources, alternate paths, tag profiles, source records, and catalogs all use resolvable same-document `xml:id` pointers. Native validation compares the complete TEI source, classification, and catalog mirrors—including labels, versions, dictionary IDs, and source references—to the manifest, while manifest classifications, catalogs, and compatibility records must equal the approved plan.

Each node has at most one `settingDesc`; each location uses its own `place/location/geo`, followed by `place/idno type="sourceNode"`. This order is required by the pinned Lex-0 grammar. Coordinates are decimal WGS84 latitude then longitude, and semantic families or collectives cannot carry points. The embedded registry version is `teiHeader/revisionDesc/change[@type="registryVersion"]/@n`; it must equal the manifest's `registryVersion`, whose `contentSha256` hashes the exact generated registry bytes.

The manifest namespace is `https://raskovnik.org/ns/language-registry/manifest`. It records the pinned Lex-0 identity, public registry source IDs and raw upstream IDs, source files and hashes, licence/attribution metadata, trilingual classification records, dictionary catalogs, and compatible dictionary resource hashes in the canonical `sha256:<64 lowercase hex>` form. Its public source ID is always `source/@xml:id`; `@upstreamId` preserves the separate raw key from `upstream/sources.json`.

## Production proof boundary

Syntactically valid XML is insufficient for release. The production-plan verifier requires an empty regenerated exception report, exact approval hashes for `registry-candidates.json`, `editorial-review.tsv`, `raskovnik-overrides.xml`, and the complete output-driving plan payload, a tag-profile inventory identical to the standards-derived candidates, the exact count-free PERSJ source-record inventory and inverses, an approved canonical code and exact Glottolog identifier for every required ancestor, and an approved record for every candidate exception. It validates all canonical tags against the pinned IANA registry, rejects deprecated or unavailable non-private subtags, and retains the registered-base private-use policy.

For exact identifiers, a Glottolog identifier in the plan is treated as an exact claim and must resolve in pinned Glottolog 5.3; duplicate exact claims fail. Any Glottolog node carrying ISO 639-3 must expose that same exact ISO identifier, and any ISO 639-3 claim must reproduce the complete applicable ISO 639-1, 639-2B, 639-2T, and 639-3 inventory from the pinned table. The shortest exact standard code is enforced where an ISO 639-1 code exists. Nonexact or broader relationships are not emitted as exact identifiers and remain editorial exceptions. These checks become satisfiable only after the outstanding editorial queue is resolved; until then the production artifact gate remains deliberately red.

To compare the public PERSJ mapping snapshot with the exact local conversion source, run:

```sh
python3 scripts/import-persj.py --source /path/to/new-conversions4raskovnik/PERSJ --check
```

The importer verifies the pinned source hashes and deliberately strips compound occurrence counts from the public mapping export.

## Package contract

The package URI is `http://raskovnik.org/raskovnik-language-registry`; it depends on `raskovnik-data-core >= 2026.6.6-1`. The XAR contains only the effective `registry.xml`, `manifest.xml`, `post-install.xq`, and generated EXPath descriptors. Registry releases are published from this repository and pinned by compatible backend release sets; generated registry data is not copied into the backend repository.
