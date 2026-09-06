# Offline registry review

Generate a self-contained page from the current generated candidates and their pinned PERSJ catalogue:

```sh
python3 scripts/build-review-page.py --output /private/tmp/language-registry-review.html
```

Optionally pass `--previous /path/to/earlier/language-registry-review.html` to retain earlier audit suggestions as clearly marked historical context and enable discovery of that snapshot's browser storage. Earlier suggestions never provide current defaults. The generator reads no saved browser decisions or override exports and writes no editorial approvals. At page load, accessible earlier browser decisions are migrated into the local review.

With `--previous`, the page retains the original audit inventory, queues, proposals, and resolved policy work. Only the implemented Serbian/Serbo-Croatian and Iron/generic Ossetian mapping updates are applied; `sh` and `ira-x-ossetic` are added. Raw candidate missing labels do not reopen the established audit. Without `--previous`, the page shows the full candidate inventory. Approved ledger records are locked. Local confirmations and corrections are review material; publication still requires the durable editorial ledger and existing validation gate.

Earlier decisions, edited values, notes, and timestamps carry forward for unchanged identities without reconfirmation. The page automatically finds earlier storage when the browser exposes it to the new file. **Import review JSON** provides the same migration when file-origin isolation prevents discovery: export JSON from the original page in its original browser, then import it here once. The old page and its storage are never modified.

Only changed identities require reconciliation. The former `os` decision is retained as history beside `os` (Iron) and `ira-x-ossetic` (generic Ossetian), with both split rows pending. A backup from this exact current snapshot restores those decisions directly. Existing work on the current page takes precedence over imports. Comparison-only placeholders created by the previous importer are automatically repaired from their archived records on reload.

Unmatched records remain in the JSON backup. Export review JSON regularly; TSV is a flat review report and does not preserve imported history. Local review migration does not update the durable registry approval ledger or conversion mappings.

## Label completion from a saved review

Pass `--review-json /path/to/language-registry-review-current.json` to seed a page from the user's exported decisions and complete blank Serbian/German labels using `review/label-supplements-20260906.json`. The additions are review-only: descriptive ancestor translations are identified as such, and attested labels carry their source. The generator preserves nonblank user labels and every non-label decision field; no registry ledger approvals are created. The supplied JSON is read-only. An existing output's embedded decision seed is retained when the option is omitted on regeneration. Newer local edits override the embedded seed; older equal-timestamp copies cannot erase a completed blank label.

The label-completion exception report covers Bookkeeping and the two Shifted Romance nodes. They remain in their existing queues. PB and PBS are retained as distinct untranslated suffixes, and Nuclear/Core use distinct descriptive labels. Each generated HTML row exposes provenance for its added labels; exported JSON includes the additions separately from human decisions.
