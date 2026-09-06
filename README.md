# Raskovnik language registry

Edit [registry/registry.xml](registry/registry.xml). It is the authoritative TEI Lex-0 language registry: classification, names, identifiers, representative locations, count-free source-label mappings, and provenance. Dictionary entries, evidence, occurrence counts, and authorization belong to the backend.

## Edit and validate

The document links to the checked-in Lex-0 development RNG and Raskovnik Schematron for editor validation. Use the full check before committing:

```sh
make check
make package
```

Requirements: Python 3.10+, Jing, xmllint, Java, and Maven. Maven plugin dependencies must be available locally; provision them once with `mvn dependency:go-offline`. Ordinary builds are offline and need no sibling checkout. `make package` writes a validated XAR under `target/` and its companion release JSON at `dist/release.json`. Generated files are ignored. `mvn -o package` independently validates the master before assembly and verifies archive contents afterward.

Edit labels in place and preserve technical IDs, canonical tags, source-record links, and display nesting. Every selectable node requires Serbian, English, and German names; nonselectable ancestors require English and may omit the other two. Explicit private tags have registered bases. Exact identifiers must not absorb broader or narrower supporting evidence; `note[@type='excludedExactIdentifier']` preserves reviewed exclusions. Add ordinary TEI review notes and revision history when decisions change.

The version and release timestamp come from the single `revisionDesc/change[@type='registryVersion']`; package version comes from `pom.xml`. Update these intentionally for a release. Packaging preserves the master bytes exactly and derives the complete manifest from TEI. The master is never rebuilt from upstream datasets.

## Standards and provenance

Lex-0 is pinned to `0.9.6-dev`, revision `f6d51f29d1d2227c012dafcef20bec0708938505`. The schema and the small IANA/ISO tables are checked against `registry/standards-lock.json`. Refresh these only as an explicit reviewed change with exact bytes, checksum, revision, and attribution updates; update backend schema acceptance at the same time if the Lex-0 pin changes.

Glottolog, CLDR, Wikidata, conversion-catalogue, and review provenance remain in TEI source bibliography records. Historical source-file references point into the preserved bootstrap commit. Those bulk datasets are not routine build inputs. IANA/ISO checks verify current recorded standards claims; external Glottolog/Wikidata equivalences require editorial review.

## Release and installation

The XAR contains `registry.xml`, manifest v2, the installation hook, and four generated EXPath/eXist descriptors. It depends on `raskovnik-data-core` and installs under `/db/apps/raskovnik-data/metadata/languages`.

Publish the XAR and `dist/release.json` together from this repository when a release is authorized. Backend release sets select the exact registry release with `prepare-release.sh --assemble-release-set --registry-release <tag>` and own installation, verification, rollback, and frontend cache clearing. There is no standalone deployment script here.

Manifest v2 declares `language-tag-coverage-v1`. Every nonempty canonical etymon-form language tag in each enabled dictionary must resolve to one direct registry profile. Dictionary content hashes remain artifact/provenance checks in the backend; they do not tie registry releases to dictionary revisions. New unsupported tags require a registry update, while spelling corrections using existing tags do not.

Deploy the manifest-v2 registry with the matching backend app as one release set. Old backend versions reject v2. Roll back the explicitly pinned app and registry together.

## Migration history

Commit `2f63dc0` preserves the completed reproducible bootstrap, full review archive, override ledger, and initial validated TEI master. All 89 bootstrap tests passed and the editorial gate was empty. The initial inventory was 380 nodes, 214 direct profiles, and 311 source records. The promoted TEI was compared against the complete compiler projection before the bootstrap was removed; [migration digests](docs/tei-migration-digests.json) record the initial semantic projection, not a constraint on subsequent editing.

The complete 20-ancestor translation batch was approved by ttasovac on 2026-09-06. Earlier human decisions, the three English-only fallbacks, generic Ossetian/Iron separation, and Kajkavian's narrower-ISO exclusion are retained.
