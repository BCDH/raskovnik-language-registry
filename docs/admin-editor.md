# Registry editing through the shared admin

`registry/registry.xml` remains the sole language-data authority. The Laravel **Именовани ентитети → Језици** interface edits isolated Git drafts through `scripts/registry_editor.py`; it does not write to the operator checkout or the installed eXist registry. Dictionary language assignment remains in dictionary TEI.

The editor accepts JSON on stdin and returns JSON diagnostics. `inventory`, `validate`, `diff`, `inspect-glottolog`, and `review-glottolog` complement the `edit` command. Every edit supplies `expectedRevision` (SHA-256 of the current XML bytes), an operation, an editorial rationale, and values. Failed validation leaves the draft unchanged. A per-document lock prevents concurrent writers and atomic replacement prevents partial XML files. The worker additionally binds saves and approvals to the Glottolog review table, enrichment catalogue, and image bytes.

```sh
python3 scripts/registry_editor.py inventory --registry registry/registry.xml
python3 scripts/registry_editor.py validate --registry registry/registry.xml
python3 scripts/registry_editor.py diff --registry /path/to/draft/registry.xml --base /path/to/base.xml
```

Names, aliases, exact identifiers, selection status, classifications, existing source-label translations, bibliography, exclusions, geographic profiles, and locations have targeted editing operations. Unowned XML remains intact. Location updates retain additional notes and comments; deletion of a location with additional source markup requires explicit XML editing. Creating, moving, or deleting children changes `language`/`languageGrp` wrappers automatically. Canonical IDs cannot be renamed. Referenced nodes, nodes with children, and nodes with dictionary tag profiles or source mappings cannot be deleted through ordinary CRUD; retirement of a covered tag requires the existing backend coverage-verified migration workflow.

Alias replacement is limited to the Serbian, English and German fields exposed by the form. Existing aliases in other languages retain their exact XML, identifiers and provenance when an exposed alias is changed.

Glottolog registration is explicit: inspect the archived record, approve it with reviewer and rationale, then register the concept. The tool checks the archive checksum against the review table and TEI bibliography and rejects retired or Bookkeeping records. It does not refresh standards or promote narrower component identities. The Luwian pilot test approves `cune1239` and `hier1240` in temporary data, creates `xlu` and `hlu`, and verifies that `ine-x-luwian` keeps its identifiers while becoming a group wrapper. It does not add those children to the master.

Reviewed geography uses ordinary Lex-0 elements: a `note[@type='geographyProfile']` with individual/aggregate subtype, followed by `note[@type='geographyDecision']` records. A decision records pending/approved/blocked status, own/broader/proxy/member mechanism, a bibliographic source, represented region and period, rationale and date. `ref` elements identify registered donors/members and specific stable location IDs. Source/identity bindings in `@n` and `seg[@type='subjectBinding']` let the backend suppress approvals after relevant source or classification changes. The admin requires explicit reconfirmation of stale approvals.

The first geographic edit adds one `revisionDesc/change[@type='geographyPolicy'][@n='reviewed-v1']`. Packaging then emits **manifest v3**, retaining `language-tag-coverage-v1` compatibility and adding `geographyPolicy="reviewed-v1"`. Existing documents without that marker remain manifest v2. Deploy the matching backend resolver and frontend before, or in the same coordinated release as, the first v3 registry. Older backends reject v3 instead of silently applying automatic ancestor geography. Do not downgrade a reviewed document to v2 to bypass that boundary.

Under the reviewed policy, unchanged own locations remain visibly unreviewed; automatic ancestor fallback is suppressed. Individual approvals bind specific own or donor locations. Aggregates contribute their registered members' points, preserve the owning concept and provenance, report missing members, and never donate a centroid or invented umbrella point. Stale decisions remain visible for review but contribute no points. `registry/geography-worklists.json` preserves the initial A–D queues from the coverage plan (18/8/7/50 nodes); queue membership never approves a geographic claim.

The count-free preview is exposed by the backend's `langreg:geography-projection` and uses the same effective-location resolver as runtime. Its legacy mode reproduces the current automatic fallback; its reviewed mode uses `language-geography.xqm`. No dictionary counts or private evidence enter registry drafts, packages, or review commits.

Run `make package` before release; it includes offline checks, schema validation, all Python tests, package assembly, and byte-preservation checks. CI runs that same workflow. Deployments remain owned by backend release sets. Frontend worker configuration and the linked enrichment workflow are documented in `raskovnik-frontend/docs/language-registry-admin.md`.
