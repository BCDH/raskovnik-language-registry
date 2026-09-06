#!/usr/bin/env python3
"""Generate an offline review UI, preserving the established audit when supplied."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True).replace('<', '\\u003c')
def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()
def build(candidates, previous=None):
    old, legacy_hashes = {}, []
    if previous:
        text = previous.read_text()
        match = re.search(r'<script id="audit-data"[^>]*>(.*?)</script>', text, re.S)
        old = {r['recordType']+':'+r['id']: r for r in json.loads(match[1])}
        previous_meta_match = re.search(r'<script id="review-meta"[^>]*>(.*?)</script>', text, re.S)
        previous_meta = json.loads(previous_meta_match[1]) if previous_meta_match else {}

        legacy_hashes = re.findall(r"const sourceHash\s*=\s*['\"]([a-f0-9]{64})", text)
        legacy_hashes.extend(previous_meta.get('legacySourceHashes', []))
        if previous_meta.get('sourceHash'):
            legacy_hashes.append(previous_meta['sourceHash'])
    evidence = {}
    commit = candidates['sources']['persjCommit']
    catalog = ROOT / 'upstream/persj' / commit[:7] / 'effective-language-catalog.xml'
    ns = {'s':'https://raskovnik.org/ns/language-registry/source'}
    for profile in ET.parse(catalog).getroot():
        evidence[profile.attrib['ident']] = {
            'meanings': '; '.join(dict.fromkeys(n.text or '' for n in profile.findall('.//s:name[@type="meaning"]', ns))),
            'notes': '; '.join(dict.fromkeys(n.text or '' for n in profile.findall('.//s:name[@type="sourceLabel"]', ns) + profile.findall('.//s:note', ns)))}
    rows = []
    for kind, source in [('tag-profile',candidates['profiles']), ('ancestor',candidates['ancestorCandidates'])]:
        for item in source:
            ident = item['id'] if kind == 'tag-profile' else item['glottocode']
            labels = item['preferredLabels']
            reasons = list(item.get('reviewReasons', []))
            missing = [lang for lang in ('sr','en','de') if not labels.get(lang)]
            ui_reasons = reasons + ['missing-label-'+lang for lang in missing]
            approved = (item.get('approval') or {}).get('status') == 'approved'
            alignment = (item.get('glottolog') or {}) if kind == 'tag-profile' else {'relationship':'exact','glottocode':ident}
            relation, glot = alignment.get('relationship',''), alignment.get('glottocode','')
            external = relation+':'+glot if glot else ''
            qid = item.get('wikidataQidCandidate') or ''
            row = dict(recordType=kind,id=ident,kind=item.get('kindCandidate') or '',
                parentOrLineage=' → '.join(n['name']+' ('+n['glottocode']+')' for n in item.get('lineage',[])) or item.get('parentCandidate') or item.get('parentGlottocode') or '',
                externalAlignment=external,approval='APPROVED' if approved else 'PENDING',
                reviewReasons=','.join(ui_reasons),remainingReviewReasons=','.join(ui_reasons),
                proposedCanonicalCode=ident if kind=='tag-profile' else item.get('canonicalCodeCandidate') or '',
                proposedKind=item.get('kindCandidate') or '',proposedExternalAlignment=external,
                proposedExactGlottocode=glot if relation=='exact' else '',proposedBroaderGlottocode=glot if relation=='broader' else '',
                proposedRelatedIdentifiers='',proposedWikidataQid=qid,candidateWikidataQids=qid,rejectedWikidataQids='',
                wikidataAssessment='Candidate for review' if qid else 'No candidate in current snapshot',
                auditDisposition='PARTIAL' if ui_reasons else 'FULL',
                reviewQueue='IMPLEMENTED_LOCKED' if approved else 'EDITORIAL_JUDGMENT' if ui_reasons else 'READY_TO_CONFIRM',
                policyResolutions='',sourceMeanings=evidence.get(ident,{}).get('meanings',''),sourceNotes=evidence.get(ident,{}).get('notes',''),
                auditRationale='Generated from the pinned registry candidates. Missing labels remain empty; alignments and labels remain proposals unless approved in the durable ledger.',
                evidenceUrls=';'.join(([f'https://glottolog.org/resource/languoid/id/{glot}'] if glot else []) + ([f'https://www.wikidata.org/wiki/{qid}'] if qid else [])))
            for lang, suffix in [('sr','Sr'),('en','En'),('de','De')]:
                row['label'+suffix] = row['proposedLabel'+suffix] = labels.get(lang) or ''
            row['proposalFingerprint'] = digest(row)
            key = kind+':'+ident
            legacy_key = 'tag-profile:os' if ident=='ira-x-ossetic' else key
            if legacy_key in old:
                prior = old[legacy_key]
                row['legacyProposal'] = {k:v for k,v in prior.items() if k.startswith('proposed') or k=='auditRationale'}
            if ident=='ira-x-ossetic':
                row['legacyReviewKeys'] = ['tag-profile:os']
            if ident in ('os','ira-x-ossetic'):
                row['identityChange'] = 'The former os scope was split. os now represents explicit Iron; ira-x-ossetic represents generic Ossetian. An earlier os decision cannot approve both identities.'
            rows.append(row)
    if previous:
        current = {r['recordType']+':'+r['id']:r for r in rows}
        # The audit is the review baseline, not a disposable rendering of raw candidates.
        rows = []
        for key, prior in old.items():
            if key == 'tag-profile:pl-x-karpat':
                continue
            row = dict(prior)
            if key == 'tag-profile:os':
                row = current[key]
            elif key == 'tag-profile:de-x-middle':
                row['id'] = 'gmh'
                row['proposedCanonicalCode'] = 'gmh'
                row['legacyReviewKeys'] = ['tag-profile:de-x-middle']
                row['sourceMeanings'] = current['tag-profile:gmh']['sourceMeanings']
                row['sourceNotes'] = current['tag-profile:gmh']['sourceNotes']
                row['auditRationale'] += ' Source correction implemented: the erroneous private tag is replaced by gmh; no registry alias is retained.'
            elif key == 'tag-profile:sr':
                row['sourceMeanings'] = current[key]['sourceMeanings']
                row['sourceNotes'] = current[key]['sourceNotes']
                row['auditRationale'] = 'The source mapping split is implemented: sr retains Serbian and sh represents Serbo-Croatian. The existing Serbian review proposal and saved decision are retained.'
                row['remainingReviewReasons'] = ''
                row['policyResolutions'] = 'serbo-croatian-source-split-implemented'
            rows.append(row)
        for key in ('tag-profile:sh','tag-profile:ira-x-ossetic'):
            if key not in old:
                row = current[key]
                row['reviewQueue'] = 'EDITORIAL_JUDGMENT'
                rows.append(row)
    meta = dict(sourceHash=digest(candidates),proposalHash=digest(rows),sources=candidates['sources'],legacySourceHashes=list(dict.fromkeys(legacy_hashes + ['3bb8512469778326efffd2b10adc2ad90c6a517eb0f9004106a9ef4618fb57cd', 'da1dd0bdb233f9e8075ecd02f442b177ce884330770b1900c540a74da436e7bc'])))
    meta["preferredReviewStorageKeys"] = ['raskovnik-language-registry-review-v5:3bb8512469778326efffd2b10adc2ad90c6a517eb0f9004106a9ef4618fb57cd:9764eaa6b5b8e27a973840f89873f1cc169aef002a20e4ebf3cac26ef145be8c']
    return rows, meta

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates',type=Path,default=ROOT/'dist/registry-candidates.json')
    parser.add_argument('--previous',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--review-json',type=Path)
    parser.add_argument('--label-supplements',type=Path,default=ROOT/'review/label-supplements-20260906.json')
    args=parser.parse_args()
    candidates=json.loads(args.candidates.read_text())
    rows,meta=build(candidates,args.previous)
    retained_review = None
    if not args.review_json and args.output.exists():
        match = re.search(r'<script id="review-meta"[^>]*>(.*?)</script>', args.output.read_text(), re.S)
        old_meta = json.loads(match[1]) if match else {}
        if old_meta.get('seedReview'):
            retained_review = {'schema':'raskovnik-language-review-v5','review':old_meta['seedReview'],'imports':old_meta.get('seedImports',[])}
    if args.review_json or retained_review:
        from review_labels import enrich
        rows,meta = enrich(rows,meta,json.loads(args.review_json.read_text()) if args.review_json else retained_review,json.loads(args.label_supplements.read_text()))
    editorial = sum(r['reviewQueue']=='EDITORIAL_JUDGMENT' for r in rows)
    summary=f"Review: {len(rows)} rows · {editorial} editorial judgment · PERSJ {meta['sources']['persjCommit'][:7]}. " + ('Original audit scope, queues, and proposals retained; mapping updates: Serbian/Serbo-Croatian and Iron/generic Ossetian.' if args.previous else 'Full candidate inventory.')
    if args.review_json or retained_review:
        summary += f" Saved editorial decisions restored; {len(meta['labelSupplements'])} blank label fields completed. Ancestor additions are project translations, except where cited as attested. Three nodes remain in the separate exception report."
    page=(ROOT/'review/review-template.html').read_text().replace('@@ROWS@@',encoded(rows)).replace('@@META@@',encoded(meta)).replace('@@SUMMARY@@',html.escape(summary))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(page)
    print(f'{args.output}: {len(rows)} rows')
if __name__=='__main__':
    main()
