# Geographic coverage audit and fix plan

Baseline audit date: 2026-09-12; plan revised 2026-09-13. This is a proposal, not a registry-data change. Geographic suitability is a prerequisite for every new fallback, aggregate maps have one shared projection contract, and review of existing inherited profiles is required batch D. No coordinates, identifiers, classification links, or deployment state were changed by this audit.

## Findings

The current registry contains 379 nodes: 180 families and 199 other concepts (119 languages, 41 varieties, 36 historical stages, and 3 reconstructed languages). Of the 199 nongroup nodes, 105 have their own coordinates, 50 inherit a location, and 44 have neither. Among selectable nodes, the corresponding figures are 105, 48, and 37, plus 26 groups. These are public registry inventory counts, not dictionary evidence counts.

| Nongroup coordinate availability in the current implementation | Nodes |
| --- | ---: |
| Own coordinates present | 105 |
| Coordinates available through automatic ancestor inheritance | 50 |
| Neither own nor inherited coordinates available | 44 |
| Total | 199 |

Availability and reviewed suitability are separate measurements. Neither an existing coordinate nor a successful build establishes that a location is geographically appropriate. This audit does not establish a total of reviewed profiles. Record each proposed or existing location/fallback as pending review, approved for a stated geographic and temporal scope, or blocked. Report own, inherited, proxy, and aggregate mechanisms independently of that review status; a blocked fallback can remain documented as a candidate while producing no marker.

Batch A has nine exact source-coordinate candidates and nine potential inherited children. The proposed Old Breton and Doric fallbacks are blocked; the other seven require individual review before activation. Batch B has eight editorial or aggregate profile candidates. Batch C has seven distinct Church Slavonic treatments. Batch D must review all fifty existing inherited profiles and resolve the known misleading cases through an appropriate location/proxy or an explicit block. Every new source point also needs a suitability decision for its owning concept; an exact identifier match alone is insufficient.

The previous 44 → 26 → 18 → 11 projection ignored geographic suitability and is withdrawn as a completion forecast. If all nine A source points, the other seven A fallbacks, all eight B profiles, and all seven C treatments are approved, thirteen of the originally unmapped nodes would still lack geography until further work, including Old Breton and Doric. That is a conditional scenario, not the final residual list: rejected candidates and D's blocked existing fallbacks can increase the missing count, while reviewed replacements can decrease it. Generate the final named residual list from the implemented review decisions, distinguishing deliberate blocks, pending research, absent members, and incomplete aggregates.

The current backend already implements two useful rules in `language-registry.xqm` and `language-map.xqm`: families have empty `locations` and `effectiveLocations`, and their map is assembled from descendant nongroup nodes; a nongroup node without its own location inherits the nearest nongroup ancestor that has an explicit location. It does not inherit through a sibling, a source-tag prefix, or an alternate classification. A family map currently filters descendants by dictionary evidence unless `includeUnattested=true`.

Fifteen groups have no mapped descendants under the current display tree. This is a separate problem from the 44 nongroup gaps. An absent `<geo>` on a family is intentional and should not itself be counted as a defect.

## Target behavior

1. A language, variety, or historical stage uses its own geographically reviewed point or points first. Any fallback must have an explicit suitability decision for the recipient, donor, source locations, and represented period/region. Distinguish a broader-language donor from a geographic proxy; preserve the relationship type and provenance. Classification ancestry alone never approves a new fallback. A failed or blocked candidate must not silently resume traversal toward a more distant ancestor. An alternative donor requires its own review. For Church Slavonic recensions, the order is own historical locations → approved modern-language proxy → no marker. Modern Serbian is a geographic proxy for Serbian Church Slavonic, not its broader language or a reason to reparent it. Apply the same suitability rule to all nine proposed A inheritances and the fifty existing inheritances reviewed in D.
2. A group displays the union of effective locations of its registered descendants and any explicitly reviewed registry members. It never acquires a synthetic family centroid or donates its aggregate points back to an individual language. Use only registry members, not every child that happens to exist in an upstream database.
3. Keep geographic relationships separate from exact language identity, the display tree, and dictionary evidence resolution. In particular, component locations used for Persian or generic Ossetian do not confer the components' Glottocodes or ISO identities on the umbrella concept.
4. Label coordinates as representative, historical, editorial, or inherited as appropriate, and distinguish geographic proxies from broader-language inheritance. Several anchors are valid for a geographically broad concept. A point locates a representative context; it does not delineate a language's territory. Glottolog itself explains that its points can have different representative meanings and are not substitutes for detailed geographic scholarship. [Glottolog coordinate policy](https://glottolog.org/glottolog/glottologinformation).
5. Expose distinct empty states: no reviewed location; no registered members; registered members lack locations; or mapped members are hidden by the evidence filter. To satisfy registry-wide group coverage, open group geography with registered members visible and distinguish those without dictionary evidence. Keep this map setting independent of the evidence list and its counts.

## Batch A: restore nine exact records from the pinned snapshot

Use the existing `src-glottolog-5-3` bibliography and each exact Glottocode as the location's `sourceNode`. After reviewing the source point's suitability for its owning concept, insert the missing `settingDesc/place/location` records in the TEI master. Preserve upstream decimal precision and coordinate order: latitude, longitude. Do not add or replace exact identifiers from the CSV's ISO column, whose scope can differ from the registry's reviewed concept. Deploy reviewed fallback gating before or atomically with these additions; a TEI-only release against the old automatic resolver could activate rejected child locations.

The coordinate pairs were recovered from the provenance-pinned [geo.csv at bootstrap commit 2f63dc0](https://github.com/BCDH/raskovnik-language-registry/blob/2f63dc0/upstream/glottolog/5.3/geo.csv), and cross-checked against the pinned `languoid.csv`. Their bytes match the checksums recorded in the current TEI bibliography. This is not an upstream-version refresh.

| Registry node / exact source | Coordinates | Affected nodes under the old automatic fallback; not approved coverage |
| --- | --- | --- |
| Old-Middle Welsh `und-x-glot-oldw1239` / `oldw1239` | `52.582 -4.089` | Old-Middle Welsh `und-x-glot-oldw1239`, Old Welsh `owl`, Middle Welsh `wlm` |
| Old South-West British `und-x-glot-oldc1252` / `oldc1252` | `50.61436 -4.34409` | Old South-West British `und-x-glot-oldc1252`, Old Breton `obt`, Old Cornish `oco` |
| Old Irish `sga` / `oldi1245` | `53.0 -8.0` | Old Irish `sga`, Middle Irish (10-12th century) `mga` |
| Middle High German `gmh` / `midd1343` | `48.254 10.599` | Middle High German `gmh` |
| Old Dutch-Old Frankish `und-x-glot-oldd1237` / `oldd1237` | `52.16 5.2` | Old Dutch-Old Frankish `und-x-glot-oldd1237` |
| Old Latin `la-x-old` / `oldl1238` | `41.901111 12.488333` | Old Latin `la-x-old` |
| Occitan `und-x-glot-occi1239` / `occi1239` | `44.1415 6.82979` | Occitan `und-x-glot-occi1239`, Southern Occitan `und-x-glot-sout2612` |
| Medieval Greek `grc-x-middle` / `medi1251` | `41.013889 28.955556` | Medieval Greek `grc-x-middle` |
| Ancient North Greek `und-x-glot-anci1249` / `anci1249` | `40.825 22.144` | Ancient North Greek `und-x-glot-anci1249`, Aeolic Greek `grc-x-aeolic`, West Ancient Greek `und-x-glot-west2995`, Doric Greek `grc-x-doric` |

The old resolver would place Old Breton at the Old South-West British point in southwestern Britain, and Doric at Ancient North Greek's point. Block those recipient/donor combinations before any restoration can become visible. Old Breton requires a historical location in its represented region or a reviewed geographic proxy such as Breton `br`; Doric requires appropriate historical locations or another specifically reviewed proxy. Neither substitution is approved by this document. The same scrutiny applies to Aeolic, West Ancient Greek, and every other affected child. A popup qualification cannot compensate for a geographically unsuitable marker. [Breton historical geography](https://www.cambridge.org/core/books/abs/substancefree-framework-for-phonology/breton-language/AA8A65A149DA6B2D1D9D6B55F3C70079), [Greek dialect geography](https://www.cambridge.org/core/books/indoeuropean-language-family/greek/D7ECB74210D90E01F00D41B9930BC70A).

| Potential inherited child | Candidate donor | Required A disposition |
| --- | --- | --- |
| Old Welsh `owl` | `und-x-glot-oldw1239` | Pending recipient-specific geographic and temporal review. |
| Middle Welsh `wlm` | `und-x-glot-oldw1239` | Pending recipient-specific geographic and temporal review. |
| Old Breton `obt` | `und-x-glot-oldc1252` | Block this fallback; source an own historical location or review a `br` proxy. |
| Old Cornish `oco` | `und-x-glot-oldc1252` | Pending recipient-specific geographic and temporal review. |
| Middle Irish `mga` | `sga` | Pending recipient-specific geographic and temporal review. |
| Southern Occitan `und-x-glot-sout2612` | `und-x-glot-occi1239` | Pending review of the narrower variety's geography. |
| Aeolic Greek `grc-x-aeolic` | `und-x-glot-anci1249` | Pending review of the represented historical dialect area. |
| West Ancient Greek `und-x-glot-west2995` | `und-x-glot-anci1249` | Pending review of geographic scope and whether member geography is more appropriate. |
| Doric Greek `grc-x-doric` | `und-x-glot-anci1249` | Block this fallback; source appropriate historical locations or a reviewed proxy. |

The tenth verified source record, `chur1257` at `43.7171 22.8442`, is excluded from batch A. A shared point for the Church Slavonic recensions would be misleading even with a popup qualification. Do not install it as a universal map location, propagate it to children, or automatically assign it to Old Church Slavonic. Handle the entire `cu` subtree through batch C.

## Batch B: eight proposed editorial profiles with available supporting coordinates

For external source components that are not registry nodes, an approved editorial profile can use the existing multiple-place model, with each point owned by the broader registry concept and its narrower source meaning explicitly documented. For registered components, use aggregate member geography under the shared map contract below; do not copy the members' points into the umbrella's own or inheritable locations. Preserve source record IDs and bibliographic provenance in either case. Neither mechanism is broader-language inheritance, and neither promotes component identifiers to exact identifiers of the umbrella. Review all eight proposals before counting them as suitable geographic profiles.

All Glottolog values below come from the same verified pinned snapshot; the WALS comparison is an additional source check rather than a replacement authority.

| Registry concept | Candidate anchors, latitude longitude | Proposed treatment |
| --- | --- | --- |
| Kurdish `ku` | Central Kurdish `cent1972`: `35.6539 45.8077`; Northern Kurdish `nort2641`: `37.0 43.0`; Southern Kurdish `sout2640`: `32.8977 46.5976` | Use a component-based editorial profile. `kurd1259` is an upstream family and has no own point. No Kurdish component currently exists as a separate registry node. |
| Nuclear Pashto `ps` | Central Pashto `cent1973`: `31.9153 69.4529`; Northern Pashto `nort2646`: `34.0 71.33`; Southern Pashto `sout2649`: `31.5 65.7` | Use components of exact upstream `nucl1276`; do not broaden to all of the larger Pashto grouping. |
| Persian `fa` | Western Farsi `west2369`: `32.9 53.3`; Dari `dari1249`: `34.39757 66.14961` | The registry already records these as narrower supporting concepts. Preserve both anchors and that qualification; do not equate `fa` with `pes` or broaden it to all Farsic-Caucasian Tat. |
| Generic Ossetian `ira-x-ossetic` | Existing `os` / Iron: `42.98 44.61`; `osd` / Digor: `43.158056 44.156944` | Use the two registered components through reviewed geographic links. They are display-tree cousins of the generic node, not its descendants. Keep generic Ossetian distinct from Iron. |
| Albanian `sq` | Existing Gheg `aln`: `42.317 21.3837`; Tosk `als`: `41 20` | Use both registered components. A single WALS Albanian point `41 20` also exists, but the two-member representation makes the scope clearer. |
| Mongolian `mn` | Halh `halh1238`: `48.32397 106.28874`; Peripheral Mongolian `peri1253`: `42.4208 110.157` | Use these as explicitly partial representative anchors. The registry has `xal` beneath `mn`, but automatically making its far-western Kalmyk point the sole Mongolian location would be misleading. The `mong1331`/ISO `mon`/Kalmyk scope needs separate review; do not silently change it for a map fix. |
| Estonian `et` | Standard Estonian `esto1258`: `58.55 25.82`; South Estonian `sout2679`: `57.85 27.0` | Both narrower components are already acknowledged in review notes. Their geography can support the umbrella without undoing the explicitly reviewed generic `et` identity. |
| New High German `de-x-high-new` | Existing Swabian `swg`: `48.386796 9.987111`; Bavarian `bar`: `47.9232 13.246`; Standard German `de`: `48.649 12.4676` | Adopt a labelled, partial component profile for the registered descendants. `mode1258` is an upstream family despite this registry concept's historical-stage type. Do not create a cycle by deriving a parent's profile from a child that inherits that parent's profile; use independently located component records only. |

WALS is useful but matching labels alone is insufficient: its [Persian](https://wals.info/languoid/lect/wals_code_prs) is Western Farsi, [Estonian](https://wals.info/languoid/lect/wals_code_est) is `ekk`, [Khalkha](https://wals.info/languoid/lect/wals_code_kha) is narrower than Mongolian, and [Pashto](https://wals.info/languoid/lect/wals_code_psh) identifies Central Pashto. [Albanian](https://wals.info/languoid/lect/wals_code_alb) and [Ossetic](https://wals.info/languoid/lect/wals_code_oss) provide usable comparative points, but source/registry scope still needs review. Do not introduce family centroids from Glottolog CLDF as if they were observed language locations: that distribution explicitly documents calculated family centroids and inherited dialect coordinates. [CLDF geography documentation](https://github.com/glottolog/glottolog-cldf/blob/master/cldf/README.md).

## Shared contract for selected and dictionary-wide maps

Use one canonical geographic projection for selected-language/group responses, dictionary-wide overview maps, and prepared summaries. These are proposed contract fields, not fields already supported by the current API. Geographic relationships and review decisions belong in schema-supported TEI and must be projected consistently. Dictionary evidence flags and selection/evidence context are derived by the authorized backend at runtime or during summary preparation; never store them in the public registry.

- Each node declares individual or aggregate geographic behavior independently of its linguistic `kind`. Individual nodes expose only their own approved locations or an approved recipient-specific fallback in `effectiveLocations`. Aggregate nodes expose reviewed member links and coverage status, with empty own/inheritable location arrays. This applies to `cu`, `cu-x-church`, families, and B's profiles derived from registered members.
- Each individual semantic point has a stable `pointId`, its owning registry `nodeId`, location source identity, derivation mechanism, and any donor/proxy relationship. Aggregation retains the contributing member's `nodeId`; it never emits a second point owned by the umbrella. For example, a Serbian Church Slavonic proxy point is owned by `cu-x-srp`, records `sr` as proxy donor, and can represent `cu-x-church` and `cu` without changing its owner.
- Add `representedForNodeIds` to retain the aggregate contexts through which a point was selected, and `evidencedThroughNodeIds` to retain any actually evidenced aggregate concepts that supplied contextual inclusion. These arrays are context, not child evidence. Owner-level direct/inclusive evidence flags must still come solely from the authorized dictionary evidence resolver. Do not set a recension's `attested` flag merely because generic `cu` is evidenced; label that point as a contextual member of an evidenced umbrella. Dictionary evidence never establishes attestation at the geographic coordinate itself.
- Deduplicate repeated paths to the same semantic point by stable point identity and union the context arrays. Different members sharing physical coordinates retain separate semantic records; existing coordinate clustering may combine their visible marker. Distinct source records or geographic meanings at one coordinate must retain their provenance. Aggregate coverage reports registered members with approved geography, members still pending/blocked, and filter-hidden points separately.
- A selected aggregate expands its approved registered members recursively, regardless of linguistic kind. Detect cycles and resolve individual points before aggregating. The default group view includes contextual members; an explicit evidence-only filter removes owner-unattested points and explains any resulting empty map. Selecting an individual shows its approved individual geography without acquiring unrelated sibling locations.
- The dictionary overview starts with evidenced individual concepts and aggregates that have direct dictionary evidence. Expand those directly evidenced aggregates into contextual member points even when the members have no evidence. An ancestor's inclusive evidence alone must not cause its entire unevidenced family to be added to the overview. Merge overlapping contributions with the same ownership and context rules used in selected maps. Expose the same evidence-only filter; toggling it changes map inclusion, never dictionary counts or language evidence scope.
- External component records used in an individual editorial profile remain source records, not invented registry member nodes. A Persian editorial point sourced from Dari remains owned by `fa` and must not claim Dari-specific dictionary evidence. Its source and limited geographic meaning remain visible.

Implementation must update `language-registry.xqm`, `language-map.xqm`, `language-summary-build.xqm` (including the reduced map-projection field whitelist and prepared map responses), and the frontend's `dictionaryMapProfile()` in `language-explorer-model.mjs`. Update request/default-filter handling, location provenance rendering, and relevant schema/version compatibility checks together. Keeping aggregates out of `effectiveLocations` without updating the overview would lose umbrella-only evidence geography; copying aggregates into that array would produce duplicate umbrella/child points. The current selected map and overview use different paths, so checking only one is insufficient.

| Required fixture | Selected aggregate map and dictionary overview with contextual members enabled | Evidence-only view |
| --- | --- | --- |
| Only generic `cu` has direct evidence | Accepted recension/Old Church Slavonic member points appear once each, with their original owners and `cu` evidence context. Members remain owner-unattested. | Context-only points disappear; explain that the umbrella is evidenced but no mapped member is evidenced. |
| Only `cu-x-srp` has direct evidence | Its point appears once in the overview, even though several ancestors have inclusive evidence. Selected `cu` may additionally show contextual members; it retains the same Serbian recension point identity/provenance. | The Serbian recension point remains; unevidenced contextual members are hidden. |
| Both `cu` and `cu-x-srp` have direct evidence | No duplicate Serbian recension record through `cu-x-church` or `cu`; preserve owner evidence and umbrella context separately. | Owner-evidenced records remain without changing any counts. |
| Two recensions share a coordinate | Two semantic records, one clustered marker; each retains its own evidence and proxy/source provenance. | Filter each record by its own evidence, then rebuild the marker group. |
| Some members are blocked or lack locations | Render the remaining approved members and disclose incomplete coverage; no fabricated fallback or centroid. | Distinguish missing geography from geography hidden by the filter. |

Require live and regenerated prepared responses to agree on point ownership, context, evidence flags, missing-member coverage, and deduplication. Browser verification must exercise both selected maps and the dictionary overview with these fixtures.

## Batch C: distinct geography for Church Slavonic and its recensions

The four recensions remain under Church Slavonic in the classification tree. Give each its own historically supported location or locations when available; otherwise allow an explicitly reviewed geographic proxy from the corresponding modern language. These links express approximate geographic context, not exact language identity, genealogical parentage, or equality of historical and modern distributions. They must be declared in the registry, never inferred from a label or tag suffix.

| Registry concept | Proposed geography | Acceptance condition |
| --- | --- | --- |
| Russian Church Slavonic `cu-x-rus` | Historical centres appropriate to the represented period; otherwise Russian `ru` as an explicit geographic proxy. | Review the donor point's regional suitability; do not treat the modern language's entire distribution as the recension's territory. |
| Serbian Church Slavonic `cu-x-srp` | Documented centres of the Serbian recension; otherwise Serbian `sr` as an explicit geographic proxy. | Preserve the recension's Church Slavonic parentage and label the modern-language fallback. |
| Bulgarian Church Slavonic `cu-x-bul` | Historical literary centres; otherwise Bulgarian `bg` as an explicit geographic proxy. | Keep this treatment distinct from the historical geography of Old Church Slavonic. |
| Croatian Church Slavonic (Glagolitic) `cu-Glag-x-hrv` | Prefer specific Glagolitic centres along the Adriatic; Croatian `hr` is a provisional geographic proxy only. | Review regional suitability before accepting the generic Croatian point; prioritize historically documented locations in the relevant coastal regions. |
| Generic Church Slavonic `cu-x-church` | Union of accepted locations of its registered recensions. | Retain each contributing recension and its location/proxy provenance; report partial coverage when some recensions remain unlocated. Do not create a centroid. |
| Old Church Slavonic `cu-x-old` | Own, separately reviewed historical profile. | Do not automatically inherit the umbrella point or modern Bulgarian's coordinates. Keep this node unresolved until historical locations and their intended meaning are reviewed. |
| Old Church Slavonic and Church Slavonic, ISO umbrella `cu` | Union of the accepted Old Church Slavonic profile and recension locations represented through generic Church Slavonic. | Deduplicate repeated contributions while preserving contributing concept IDs and provenance. The umbrella is an aggregate map, never a coordinate donor to its children. |

The regional qualification matters particularly for Croatian Church Slavonic: the Old Church Slavonic Institute describes the Glagolitic chant tradition in Dalmatia, the Littoral, and Istria. This supports a focused historical/regional profile rather than equating it with modern Croatian's generic point. [Institute overview](https://stin.hr/en/glagolitic-chant/).

Implement an explicit block on automatic coordinate inheritance from `cu` and `cu-x-church`. A recension without its own accepted location or valid proxy must remain unlocated even if an umbrella has stored source coordinates or an aggregate map. Resolve the recension locations independently before computing parent aggregates so there is no parent/child dependency cycle. Geographic aggregation must be available independently of semantic kind; changing `cu` into a family merely to activate existing group-map behavior would alter the wrong contract.

Use a relationship-specific message, for example: “Approximate geographic context borrowed from Serbian; historical distribution of the recension is not represented.” Localize it in Serbian, English, and German, and retain the proxy donor's source record. A popup qualification accompanies a reviewed proxy; it does not justify using the rejected umbrella point.

Completion is per node: a reviewed proxy or historical profile resolves a recension; a populated aggregate resolves an umbrella's map but must still disclose missing members. All seven nodes count as resolved only when all four recensions, Old Church Slavonic, and both aggregates meet their respective criteria. No historical coordinate pair is approved merely by inclusion in this plan.

## Minimum research backlog beyond A + B

The following twenty nodes require separate treatment even if the nine A source points, seven unblocked A fallback candidates, and eight B profiles are approved. They comprise seven C nodes, the two blocked A children, and eleven other research cases. This is a minimum research backlog, not a complete post-task residual forecast: failed reviews of other A/B candidates and blocks imposed by D must also appear in the final generated list. Three of the eleven other cases are chronological umbrellas suited to member geography; the other eight need historical, regional, or reconstruction decisions.

| Registry ID | Name | Why not assign a point in A + B? | Next strategy |
| --- | --- | --- | --- |
| `obt` | Old Breton | The proposed British ancestor point is geographically unsuitable and blocked. | Review a historical location or explicit Breton `br` proxy; do not count it as resolved by A's source restoration. |
| `grc-x-doric` | Doric Greek | The proposed Ancient North Greek point is geographically unsuitable and blocked. | Review historical dialect locations or a specifically supported proxy; do not count it as resolved by A's source restoration. |
| `cu` | Old Church Slavonic and Church Slavonic (ISO umbrella) | A single source point cannot represent the combined historical and recension geography. | C: aggregate accepted Old Church Slavonic and recension profiles; no donation to children. |
| `cu-x-church` | Church Slavonic | Generic coverage requires the locations of its registered recensions. | C: aggregate accepted recension profiles, with partial-coverage reporting. |
| `cu-x-old` | Old Church Slavonic | Neither the umbrella point nor modern Bulgarian is an automatic historical donor. | C: establish an independently reviewed historical profile. |
| `cu-x-rus` | Russian Church Slavonic | Umbrella inheritance is prohibited. | C: own historical locations or an explicit, reviewed `ru` geographic proxy. |
| `cu-x-srp` | Serbian Church Slavonic | Umbrella inheritance is prohibited. | C: own historical locations or an explicit, reviewed `sr` geographic proxy. |
| `cu-x-bul` | Bulgarian Church Slavonic | Umbrella inheritance is prohibited. | C: own historical locations or an explicit, reviewed `bg` geographic proxy. |
| `cu-Glag-x-hrv` | Croatian Church Slavonic (Glagolitic) | Umbrella inheritance is prohibited; regional specificity needs review. | C: Glagolitic historical centres, or a provisionally reviewed `hr` geographic proxy. |
| `ine-x-proto` | Proto-Indo-European | Reconstructed concept; no reviewed point or broader-language donor. | Keep unlocated by default. A later reconstruction layer can show named, cited, dated homeland hypotheses as areas; never derive a homeland from modern descendants' mean coordinates. |
| `gem-x-proto` | Proto-Germanic | Reconstructed concept; no reviewed point or eligible donor. | Same explicit hypothesis treatment, with a distinct regional and chronological review. |
| `sla-x-proto` | Proto-Slavic | Reconstructed concept; no reviewed point or eligible donor. | Same hypothesis treatment. Do not use an arbitrary modern Slavic language as the donor. |
| `inc-x-old` | Old Indo-Aryan | A chronological umbrella currently typed as a historical stage; `inc` is a family, and Sanskrit is a sibling. Retired `oldi1244` is not an exact replacement. | Review collective geography with registered Sanskrit `sa` and Vedic Sanskrit `vsn`; share the existing coordinate where appropriate and label this as partial member coverage. A Sanskrit point does not represent every Old Indo-Aryan variety or period. |
| `ira-x-old` | Old Iranian languages | A chronological collection, currently typed as a historical stage, with no member links. | Review aggregation of registered `ae`, `ae-x-old`, `ae-x-young`, and `peo`; use member effective locations and their historical qualifications. Do not substitute the modern Iranian distribution. |
| `ira-x-middle` | Middle Iranian languages | Same temporal-collection problem. | Review registered `pal`, `xpr`, `sog`, and `kho` as an initial partial member set. Keep each member's point and period; no mean coordinate. |
| `ira-x-sarmat` | Sarmatian | Fragmentary historical concept without exact geographic source alignment. | Review the intended period and scope, then select sourced historical attestation anchors or an explicitly approximate region. Do not inherit modern Ossetian merely because of a historical relationship. |
| `xsc` | Scythian | Unplaced registry concept with no reviewed donor; historically and geographically broad evidence. | Keep Scythian distinct from Sarmatian and Khotanese. Review time-bounded attestation locations or an area before assigning a representative marker. |
| `zle-x-polesian` | Polesian | Registry placement is the East Slavic family, not a particular broader language; regional scope needs review. | Resolve whether the concept covers West, Central, East, or wider Polesian dialects. Use a dialect atlas to select documented survey localities or an area. Do not automatically inherit Ukrainian, Belarusian, or Russian. |
| `wen-x-old` | Old Sorbian | Parent `wen` is a family; modern Upper/Lower Sorbian are not broader historical donors. | Review the earlier Sorbian dialect area and select dated documentary or toponymic anchors. A qualified modern-Lusatian context profile is possible, but should not be presented as the historical distribution. |
| `otk` | Old Turkic (registry English label: Old Turkish) | Its former `oldt1247` alignment is reviewed as retired/Bookkeeping. The old CSV still has `37 59`, but that is not an approved point for this concept. | Source historical inscription sites, such as the Orkhon or Tonyukuk monuments, as historical attestation anchors. Verify the original site and WGS84 coordinates, not a museum, replica, photo-camera position, or the centre of an entire heritage landscape. |

The historical cautions have concrete source support: Iranica distinguishes the fragmentary and chronologically different [Scythian evidence](https://www.iranicaonline.org/articles/scythian-language/) from its later successors, and distinguishes the languages within the [Old, Middle, and New Iranian periods](https://www.iranicaonline.org/articles/iran-vi2-documentation/). The [Encyclopedia of Ukraine dialect overview](https://www.encyclopediaofukraine.com/display.asp?linkpath=pages%5CD%5CI%5CDialects.htm) distinguishes multiple Polesian regions. Heinz Schuster-Šewc's [Sorbian Institute abstract](https://www.serbski-institut.de/wp-content/uploads/2021/11/abstracts13-2.2196.pdf) describes an earlier Old Sorbian area wider than the surviving modern language area. The [Tonyukuk monument survey](https://www.cipaheritagedocumentation.org/wp-content/uploads/2018/11/Yildiz-e.a.-Photogrammetric-works-on-Tonyukuk-monuments-in-Mongolia.pdf) identifies the monument context; the [UNESCO Orkhon landscape record](https://whc.unesco.org/en/list/1081) describes a broad cultural landscape, not a verified coordinate for an individual inscription. These establish research directions, not approved coordinate pairs.

Successful C work removes its seven concepts from this twenty-node research backlog, leaving thirteen, including Old Breton and Doric. If those two receive reviewed replacements and the three chronological umbrellas acquire approved member geography, eight of these research cases would remain: the three proto-languages, Sarmatian, Scythian, Polesian, Old Sorbian, and Old Turkic. Actual missing-profile totals may be higher because of other rejected candidates or D's blocks. Final reporting must name all remaining unlocated concepts and unresolved groups from the accepted implementation state; no fixed target count overrides geographic suitability.

## Empty group profiles

Under the old availability-only simulation, A would populate North Greek and B would populate Laki-Kurdish, Pashto, Modern Southwestern Iranian, and Farsic-Caucasian Tat, leaving ten groups empty. Those outcomes now depend on approval of the contributing geographic profiles and application of the shared aggregation contract. A group with one approved point and several blocked members has partial coverage, not complete coverage. Do not assign coordinates directly to any of these groups.

| Currently empty group(s) | Expected result and structural work |
| --- | --- |
| North Greek `und-x-glot-nort3405` | Candidate coverage through A, conditional on approval of Ancient North Greek and any contributing varieties; Doric remains blocked pending a replacement. |
| Laki-Kurdish `und-x-glot-laki1246` | Candidate coverage through B if Kurdish's editorial profile is approved. |
| Pashto `und-x-glot-pash1269` | Candidate coverage through B if Nuclear Pashto's profile is approved. |
| Modern Southwestern Iranian `und-x-glot-mode1259`; Farsic-Caucasian Tat `und-x-glot-fars1254` | Both can acquire representative coverage through B if Persian's profile is approved. |
| Arabian `und-x-glot-arab1394`; Arabic `ar` | No nongroup Arabic members exist in the registry. These stay empty under a registered-members-only rule. A later scoped registry expansion could add reviewed Standard Arabic `arb` / `stan1318` (`27.9625 43.8525`) and further relevant varieties; it must not infer which variety generic `ar` evidence denotes. |
| Luvo-Lydian `und-x-glot-luvo1234`; Luvo-Palaic `und-x-glot-luvo1235`; Luvic `und-x-glot-luvi1234`; Luwian `ine-x-luwian` | All four currently terminate in a childless Luwian umbrella. A separate member expansion could add Cuneiform Luwian `xlu` / `cune1239` (`38 36`) and Hieroglyphic Luwian `hlu` / `hier1240` (`40.019722 34.615278`). These are already supporting concepts in the umbrella's notes, but are not registered nodes. |
| Baltic languages `bat` | Relevant registered languages exist elsewhere: `lt`, `lv`, `prg`, with `olt` under `lt`. Add reviewed geographic membership for East Baltic and Old Prussian while preserving the primary display tree and exact identities. This can close the empty map without importing languages. |
| Pomeranian `zlw-x-pomeran` | Review the intended Lechitic/historical scope first. `csb` and its Slovincian child `zlw-x-slovinc` are plausible member candidates, not already approved members of this ambiguous umbrella. Keep the missing-members explanation until reviewed. |
| Tocharian languages `ine-x-tochar` | No individual A/B nodes exist. A separate scoped expansion could add Tocharian A `xto` / `tokh1242` (`42.98 89.18`) and B `txb` / `tokh1243` (`41.65 82.9`). Preserve generic umbrella evidence rather than assigning it to either child. |
| Gallo-Romance `roa-x-gallo` | Relevant French, Occitan, and other Romance nodes occur elsewhere. Review a precise membership set against this umbrella's definition; do not treat all of `shif1234` or `gall1280` as exact. Add geographic member links for approved registered nodes only. |

Geographic membership may support an umbrella map without extending dictionary evidence scope. The response and UI must call these mapped members, distinguish actual descendant/evidence membership, and avoid marking them attested merely because the umbrella has direct evidence. If editorial policy instead changes the classification tree or semantic kinds, that is an explicit classification change and needs corresponding evidence-resolution tests.

## Batch D: required review of existing inherited profiles

All fifty nodes in the existing inheritance inventory are in this batch. Each must receive an individual recorded disposition before this geography task is complete: an approved own location, an approved explicit proxy, approval to retain the existing donor for a stated geographic/temporal scope, or a block with a reason and next research step. No reviewed disposition exists merely because the node is already mapped. Do not invent a point to meet a coverage target; a deliberate block completes the disposition but leaves the concept in the named missing-geography report.

- American English `en-US` currently inherits `53 -1` from English, in England. Austrian German `de-AT` inherits `48.649 12.4676` from Standard German, outside Austria. These two existing point assignments must be replaced by reviewed own locations/proxies or blocked; a disclosure alone cannot authorize retaining them. Neither should be placed at a national capital just by default.
- Vegliot `dlm-x-vegliot` inherits Dalmatian's `42.7095 18.0238`; Triestine `vec-x-trieste` inherits Venetian's `45.503581 12.214167`; Tuscan `it-x-tuscan` inherits Italian's `43.0464 12.6489`. Review each specific regional/historical scope now and assign an approved own location/proxy or a block where the current point is unsuitable. Do not defer these dispositions until after the task is declared complete.
- Chakavian, Shtokavian and its dialects, Ikavian, and several Serbian regional varieties inherit the broad Serbo-Croatian point `44.15 18.81`. Give documented dialect regions their own anchors when available. Avoid using a modern national standard's position as proof of dialect territory.
- Vedic Sanskrit, historical Avestan stages, older European stages, and the Latin periods inherit modern/broader or temporally broad points. Retain the inheritance label and audit temporal fit. Late, Medieval, and Neo-Latin in particular should not be interpreted as geographically confined to Latin's one point.
- Review every other entry in the fifty-node inventory, including historical stages and the remaining Slavic, Germanic, Romance, and Greek varieties. Retaining a broader-language point is an acceptable outcome only with recorded geographic suitability and an honest fallback label. Old Breton, Doric, and the other newly affected A children are reviewed in A, not counted among these fifty; Church Slavonic has its separate C dispositions.

Record recipient ID, disposition, geographic mechanism, donor or owned location IDs, represented period/region, source reference, review date, and rationale in the TEI authority. Tie approvals to the actual donor location identities and source versions; changing a donor point or recipient scope invalidates the dependent approval until reviewed. Keep pending and blocked candidates available to the audit without projecting them as approved map points.

D is complete only when all fifty initial inheritance rows have a disposition, every known unsuitable point has been replaced or suppressed, and selected maps, parent aggregates, and the dictionary overview respect those outcomes. An approved profile is distinct from a completed but blocked review. Report both totals and the complete missing-node list. Do not claim that all 105 pre-existing own profiles have undergone a geographic review unless that additional work is actually performed; their baseline count establishes coordinate presence only.

## Implementation sequence and acceptance

1. Add a read-only geography audit command that separates coordinate availability from geographic review status and reports own, inherited, proxy, aggregate, and missing mechanisms. Include donor/location identities, pending or blocked decisions, reasons, incomplete members, and remaining research actions. Keep public registry inventory separate from dictionary evidence. Freeze the 44 missing and 50 inherited baseline inventories as review cohorts, not permanent coverage targets.
2. Before activating A or any new fallback, implement reviewed geographic relationships and dispositions in the TEI authority, offline validation, and backend projection. Use schema-supported TEI links/references validated against the pinned Lex-0 schema; do not add unvalidated custom attributes or a frontend side catalogue. Encode recipient-specific approvals, source/version dependencies, explicit proxies, inheritance blocks, and aggregate behavior independent of semantic kind. Define migration handling for the 105 pre-existing own profiles explicitly: preserve their baseline provenance/status without inventing review approvals, and report any suppressed unreviewed profiles as additional gaps.
3. Validate referential integrity, eligible individual donors, geographic/temporal scope, deterministic precedence, and cycles. A pending or blocked fallback produces no marker and cannot silently resume ancestor traversal. Resolve individual profiles before aggregates; neither a family nor any other aggregate may donate member locations as an individual's fallback. Tie approvals to donor location identities so source changes cannot silently reuse an outdated decision.
4. Implement the shared selected-map, dictionary-overview, and prepared-summary contract before enabling aggregate profiles. Update the reduced projection whitelist, aggregate expansion, stable point ownership, context/evidence fields, deduplication, and explicit evidence-only filter together. Derive attribution from actual point sources instead of the unconditional `Glottolog <version>` suffix. Localize proxy, partial-coverage, pending/blocked, and filter-hidden explanations without changing evidence counts, exact identity, or illustration/reading-link bindings.
5. Review A's nine exact source candidates for their owners and all nine potentially affected children. Keep Old Breton's British fallback and Doric's Ancient North Greek fallback blocked; record decisions for the other seven before activation. Restore only accepted source records with provenance and revision history after, or atomically with, resolver gating. Exclude `chur1257` and verify that all seven Church Slavonic nodes remain unresolved through A. No standards refresh, identifier promotion, or reparenting is needed.
6. Review and implement B's eight editorial/aggregate proposals and C's seven distinct treatments. Complete D's individual dispositions for all fifty existing fallbacks; replace or suppress the known unsuitable locations, including American English and Austrian German. Research replacements for Old Breton and Doric. Review Baltic/Gallo-Romance membership and the three chronological umbrellas under the same aggregate contract. Keep Pomeranian and absent-member expansions separately identifiable; unresolved research cases remain in the final named report.
7. Add focused registry/backend tests for approved own-location precedence, approved broader-language and proxy fallbacks, pending/blocked decisions, changed donor locations, multiple places, absent donors, invalid ranges, provenance, cycles, and forbidden aggregate donation. Assert that A cannot place Old Breton in Britain or Doric at the rejected ancestor point. For each recension verify own historical location → approved declared proxy → no marker; adding umbrella coordinates must never change that result. Verify Old Church Slavonic has no implicit umbrella or modern Bulgarian fallback. Cover D's replacement/block outcomes in individual and parent maps. Exercise every shared-map fixture above, including umbrella-only evidence, mixed evidence, duplicate aggregation paths, co-located different members, partial coverage, and live/prepared response parity.
8. Run registry `make check` and `make package`; backend `scripts/test-language-registry-projection.sh`, `scripts/test-language-map.sh`, and applicable installed-registry/summary tests. Run frontend `npm run test:language-explorer` and `npm run build` when frontend changes are made. Browser-check both selected maps and the dictionary overview: accepted A profiles and blocked children, every recension's proxy/missing state, Old Church Slavonic, both Church Slavonic aggregates, D's corrected or suppressed points, unevidenced contextual members, evidence-only filtering, empty groups, and unresolved historical/reconstructed concepts. No application changes were made in this audit, so it does not claim runtime verification of proposed behavior.
9. Before declaring implementation complete, generate a final report naming every nongroup concept without usable geography and every unresolved or partial group, with review status, blocking reason, and next strategy. Reconcile all A–D cohort dispositions and distinguish mapped availability, reviewed suitability, partial aggregation, and completed-but-blocked reviews. Include additional gaps caused by rejected candidates or migration decisions; do not enforce the old numeric forecast as an acceptance target.
10. For an authorized rollout, publish the registry and required backend/frontend changes through their own release workflows in an order that never exposes new coordinates through the old resolver. Rebuild prepared language summaries for every enabled dictionary, clear RESTXQ caches, and verify selected and overview map behavior and the final coverage report. A local XAR build alone does not change explorer geography.

## Audit provenance and reproducibility

Inspected registry commit: `c9c76d08e75327ede80be794869257b770dc8e20` (version `2026.9.8-1`); backend commit: `92979e21ce305db1bad4751056f028ef6bc132a3`; frontend base commit: `5b1fa9cc92f41f0d1a89e207bfb9a332b17a2cef`. The frontend had existing uncommitted explorer/enrichment changes and was inspected read-only. Registry data and backend worktrees were clean at the start.

Pinned `geo.csv`: 1,072,964 bytes, SHA-256 `e1b68f09acadda3610ecb6704ffe573fcf5b73411ad1ad1f6396a3ff9754e702`. Pinned `languoid.csv`: 1,960,973 bytes, SHA-256 `4d9a78cb328b5f8754ad73c2575eb89ae5131077a85cf2ac794285e04c429368`. Both were read with `git show 2f63dc0:upstream/glottolog/5.3/<file>` and checked against the current TEI source-file records. Online Glottolog pages can be cached at another version; the tabulated restoration values come from the pinned local bytes.

The original audit inspected only direct `settingDesc/place/location/geo` records for own locations, excluded semantic `family`/`collective` nodes from individual donors, traversed ancestors nearest first, and simulated additions without writing to the TEI master. Group emptiness was evaluated over all registered descendants without a dictionary-evidence filter. No current node changed kind or was added in those calculations. This models the old resolver's coordinate availability, not geographic suitability or the proposed aggregate contract.

The original audit verified snapshot checksums and equality of all ten candidate coordinate pairs between the two pinned CSVs. Nine remain A candidates requiring owner review; the Church Slavonic umbrella point is excluded. The complete 44/50-node baseline inventories are unchanged. The old A and A+B simulations left 26 and 18 nodes without coordinates and produced group-empty counts of 15 → 14 → 10; those are historical availability-only results, not accepted coverage forecasts. Blocking the two identified A child fallbacks leaves at least 28 initially missing nodes after A, 20 after B, and 13 after C, conditional on acceptance of every other candidate and before replacement work. D may add gaps among previously mapped nodes. The unchanged registry passed `make check` (13 tests) and `make package` during the original audit and again for this document revision. The revised inventories were rechecked against the TEI, and candidate counts, conditional arithmetic, and Markdown table structure were checked. Those checks do not validate unimplemented review decisions, editorial profiles, proxies, historical locations, or future application behavior.

## Complete initial missing-node inventory

The following 44 rows account for every nongroup node initially without effective coordinates. A fallback entries are candidates requiring explicit recipient review; the Old Breton and Doric candidate relationships are blocked. None of these proposed results is an implemented approval. Structural/nonselectable nodes are included because they can supply locations to selectable descendants.

| ID | English registry label | Kind | Required disposition / candidate treatment |
| --- | --- | --- | --- |
| `ine-x-proto` | Proto-Indo-European | reconstructed-language | Residual: see strategy above |
| `und-x-glot-oldw1239` | Old-Middle Welsh | language | A: source point candidate; owner suitability review required |
| `owl` | Old Welsh | language | A: pending review of fallback from `und-x-glot-oldw1239` |
| `wlm` | Middle Welsh | variety | A: pending review of fallback from `und-x-glot-oldw1239` |
| `und-x-glot-oldc1252` | Old South-West British | language | A: source point candidate; owner suitability review required |
| `obt` | Old Breton | variety | A: British fallback blocked; historical location or reviewed `br` proxy required |
| `oco` | Old Cornish | language | A: pending review of fallback from `und-x-glot-oldc1252` |
| `sga` | Old Irish | historical-stage | A: source point candidate; owner suitability review required |
| `mga` | Middle Irish (10-12th century) | variety | A: pending review of fallback from `sga` |
| `gem-x-proto` | Proto-Germanic | reconstructed-language | Residual: see strategy above |
| `de-x-high-new` | New High German | historical-stage | B: proposed registered-member aggregate; review required |
| `gmh` | Middle High German | historical-stage | A: source point candidate; owner suitability review required |
| `und-x-glot-oldd1237` | Old Dutch-Old Frankish | language | A: source point candidate; owner suitability review required |
| `inc-x-old` | Old Indo-Aryan | historical-stage | Residual: see strategy above |
| `ira-x-middle` | Middle Iranian languages | historical-stage | Residual: see strategy above |
| `ira-x-old` | Old Iranian languages | historical-stage | Residual: see strategy above |
| `ira-x-sarmat` | Sarmatian | language | Residual: see strategy above |
| `ku` | Kurdish | language | B: proposed editorial profile |
| `ira-x-ossetic` | Ossetian | language | B: proposed registered-member aggregate; review required |
| `ps` | Nuclear Pashto | language | B: proposed editorial profile |
| `fa` | Persian | language | B: proposed editorial profile |
| `sla-x-proto` | Proto-Slavic | reconstructed-language | Residual: see strategy above |
| `zle-x-polesian` | Polesian | variety | Residual: see strategy above |
| `cu` | Old Church Slavonic and Church Slavonic (ISO 639 umbrella) | language | C: aggregate Old Church Slavonic and recension profiles |
| `cu-x-church` | Church Slavonic | historical-stage | C: aggregate registered recension profiles |
| `cu-Glag-x-hrv` | Croatian Church Slavonic (Glagolitic) | variety | C: own historical profile or reviewed `hr` proxy; umbrella inheritance blocked |
| `cu-x-bul` | Bulgarian Church Slavonic | variety | C: own historical profile or reviewed `bg` proxy; umbrella inheritance blocked |
| `cu-x-rus` | Russian Church Slavonic | variety | C: own historical profile or reviewed `ru` proxy; umbrella inheritance blocked |
| `cu-x-srp` | Serbian Church Slavonic | variety | C: own historical profile or reviewed `sr` proxy; umbrella inheritance blocked |
| `cu-x-old` | Old Church Slavonic | historical-stage | C: separately reviewed historical profile; no implicit umbrella or modern-language fallback |
| `wen-x-old` | Old Sorbian | historical-stage | Residual: see strategy above |
| `la-x-old` | Old Latin | historical-stage | A: source point candidate; owner suitability review required |
| `und-x-glot-occi1239` | Occitan | language | A: source point candidate; owner suitability review required |
| `und-x-glot-sout2612` | Southern Occitan | variety | A: pending review of fallback from `und-x-glot-occi1239` |
| `sq` | Albanian | language | B: proposed registered-member aggregate; review required |
| `grc-x-middle` | Medieval Greek | historical-stage | A: source point candidate; owner suitability review required |
| `und-x-glot-anci1249` | Ancient North Greek | language | A: source point candidate; owner suitability review required |
| `grc-x-aeolic` | Aeolic Greek | variety | A: pending review of fallback from `und-x-glot-anci1249` |
| `und-x-glot-west2995` | West Ancient Greek | variety | A: pending review of fallback from `und-x-glot-anci1249` |
| `grc-x-doric` | Doric Greek | variety | A: Ancient North Greek fallback blocked; historical locations or reviewed proxy required |
| `otk` | Old Turkish | historical-stage | Residual: see strategy above |
| `mn` | Mongolian | language | B: proposed editorial profile |
| `et` | Estonian | language | B: proposed editorial profile |
| `xsc` | Scythian | language | Residual: see strategy above |

## Complete existing inheritance inventory

These 50 nodes already have an effective geographic fallback before any proposed changes. They are all required D review items; the current values record availability, not approval. Every row is pending an individual disposition. American English and Austrian German must receive replacements or blocks; the other rows require explicit suitability review before retention. Listing them prevents missing direct `<geo>` elements from being mistaken for unmapped concepts.

| ID | English registry label | Current donor | Current effective coordinates |
| --- | --- | --- | --- |
| `xbm` | Middle Breton | `br` | `48.2452 -3.78934` |
| `sv-x-old` | Old Swedish | `sv` | `59.800634 17.389526` |
| `da-x-old` | Old Danish | `da` | `54.8655 9.36284` |
| `is-x-middle` | Middle Icelandic | `is` | `63.4837 -19.0212` |
| `is-x-old` | Old Icelandic | `is` | `63.4837 -19.0212` |
| `de-AT` | Austrian German | `de` | `48.649 12.4676` |
| `en-US` | American English | `en` | `53 -1` |
| `vsn` | Vedic Sanskrit | `sa` | `20 77` |
| `ae-x-old` | Old Avestan | `ae` | `34.217 62.112` |
| `ae-x-young` | Younger Avestan | `ae` | `34.217 62.112` |
| `be-x-old` | Old Belarusian | `be` | `53.2307 25.6038` |
| `uk-x-old` | Old Ukrainian | `uk` | `49.796 29.945` |
| `ckm` | Chakavski | `sh` | `44.15 18.81` |
| `sh-x-shtokav` | Shtokavian | `sh` | `44.15 18.81` |
| `sh-x-shtakav` | Shtakavian | `sh` | `44.15 18.81` |
| `sr-x-ikavsk` | Ikavian | `sh` | `44.15 18.81` |
| `und-x-glot-news1236` | New Shtokavian | `sh` | `44.15 18.81` |
| `sr-x-kos-res` | Kosovo-Resava dialect | `sh` | `44.15 18.81` |
| `sr-x-priz-tim` | Prizren-Timok dialect | `sh` | `44.15 18.81` |
| `sr-x-smed-vrs` | Smederevo-Vršac dialect | `sh` | `44.15 18.81` |
| `sr-x-sum-voj` | Šumadija-Vojvodina dialect | `sh` | `44.15 18.81` |
| `sr-x-zeta-sjen` | Zeta-Sjenica dialect | `sh` | `44.15 18.81` |
| `und-x-glot-east2821` | Eastern Herzegovinian Shtokavian | `sh` | `44.15 18.81` |
| `hr-x-old` | Old Croatian | `hr` | `45.555 15.982` |
| `sr-ekavsk` | Ekavian | `sr` | `44.3238 21.9192` |
| `sr-ijekavsk` | Ijekavian | `sr` | `44.3238 21.9192` |
| `sr-x-old` | Old Serbian | `sr` | `44.3238 21.9192` |
| `sr-x-slavserb` | Slavonic-Serbian | `sr` | `44.3238 21.9192` |
| `sl-x-old` | Old Slovene | `sl` | `46.2543 14.7766` |
| `bg-x-middle` | Middle Bulgarian | `bg` | `43.3646 25.047` |
| `cs-x-moravian` | Moravian | `cs` | `49.873398 15.10437` |
| `cs-x-old` | Old Czech | `cs` | `49.873398 15.10437` |
| `zlw-x-slovinc` | Slovincian | `csb` | `54.2996 18.6163` |
| `pl-x-old` | Old Polish | `pl` | `51.8439 18.6255` |
| `dsb-x-old` | Old Lower Sorbian | `dsb` | `51.6621 13.9407` |
| `olt` | Old Lithuanian | `lt` | `55.1429 23.9601` |
| `la-x-late` | Late Latin | `la` | `41.9026 12.4502` |
| `la-x-middle` | Medieval Latin | `la` | `41.9026 12.4502` |
| `la-x-new` | Neo-Latin | `la` | `41.9026 12.4502` |
| `la-x-vulgar` | Vulgar Latin | `la` | `41.9026 12.4502` |
| `ro-x-old` | Old Romanian | `ro` | `46.3913 24.2256` |
| `dlm-x-vegliot` | Vegliot | `dlm` | `42.7095 18.0238` |
| `vec-x-old` | Old Venetian | `vec` | `45.503581 12.214167` |
| `vec-x-trieste` | Triestine | `vec` | `45.503581 12.214167` |
| `it-x-old` | Old Italian | `it` | `43.0464 12.6489` |
| `it-x-tuscan` | Tuscan | `it` | `43.0464 12.6489` |
| `grc-x-attic` | Attic Greek | `grc` | `39.8155 21.9129` |
| `grc-x-homeric` | Homeric Greek | `grc` | `39.8155 21.9129` |
| `grc-x-ionic` | Ionic Greek | `grc` | `39.8155 21.9129` |
| `ota` | Ottoman Turkish | `tr` | `39.8667 32.8667` |
