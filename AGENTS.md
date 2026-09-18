# Repository guidance

`registry/registry.xml` is the sole editable language-data authority. Edit TEI directly, preserving style, stable IDs, display nesting, source links, and reviewed distinctions. Do not regenerate it from the retired bootstrap or edit distribution files.

Run `make check` and `make package`. Normal builds are offline. Keep the Lex-0 development schema and IANA/ISO data pinned in `registry/standards-lock.json`; standards refreshes require explicit review and updated provenance/checksums. Never silently change exact identities or erase reviewed exclusions.

The registry is public and count-free. It does not own dictionary evidence, forms, counts, coverage results, or authorization. Do not import private conversion statistics.

Commit the TEI master, focused validation/packaging code, schemas, small standards tables, tests, and durable documentation. Do not commit `dist/`, `target/`, XARs, review exports, or bulk upstream datasets. Bootstrap history is preserved at commit `2f63dc0`.

The XAR contains only registry.xml, manifest.xml, post-install.xq, and generated descriptors. It installs at `/db/apps/raskovnik-data/metadata/languages`. Backend release sets own deployment, verification, rollback, and cache clearing. Manifest v2 uses language-tag coverage; never restore dictionary-hash compatibility pins or copy generated registry data into the backend.

Read sibling repository instructions and check their status before coordinated edits. Do not print credentials or publish/deploy without authorization. Keep Markdown paragraphs and list items on one physical source line.
