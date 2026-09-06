#!/usr/bin/env python3
"""Reconcile an archived review with the durable ledger; default is a dry run."""
from __future__ import annotations
import argparse
from collections import Counter
import copy
from functools import lru_cache
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

from registry_overrides import OVERRIDE_NS, parse_overrides
from registry_sources import canonical_language_tag, parse_glottolog, parse_iana_registry, validate_registered_tag

ROOT = Path(__file__).resolve().parents[1]
NS = '{' + OVERRIDE_NS + '}'
XML = '{http://www.w3.org/XML/1998/namespace}'
SESSION = ROOT / 'review/sessions/2026-09-06'
ET.register_namespace('', OVERRIDE_NS)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).replace('<', '\\u003c').encode()).hexdigest()


def load_session(directory):
    manifest = json.loads((directory / 'manifest.json').read_text())
    for name, expected in manifest['files'].items():
        path = directory / name
        if path.parent != directory or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('archive hash mismatch: ' + name)
    review = json.loads((directory / 'labels-completed.json').read_text())
    baseline = json.loads((directory / 'baseline-candidates.json').read_text())
    rows = json.loads((directory / 'audit-rows.json').read_text())
    if digest(baseline) != review['sourceHash'] or review['sources'] != baseline['sources']:
        raise ValueError('review snapshot identity does not match archived candidates')
    current = json.loads((ROOT / 'dist/registry-candidates.json').read_text())
    if current['sources'] != baseline['sources']:
        raise ValueError('stale source snapshot; explicit reconciliation required')
    original = json.loads((directory / 'user-review.json').read_text())
    for key, record in original['review'].items():
        actual = copy.deepcopy(review['review'][key])
        for field, value in record.get('values', {}).items():
            if value or not field.startswith('label'):
                if actual['values'].get(field) != value:
                    raise ValueError('saved user value changed: ' + key + '/' + field)
        if {k:v for k,v in actual.items() if k != 'values'} != {k:v for k,v in record.items() if k != 'values'}:
            raise ValueError('saved user history changed: ' + key)
    return review, baseline, rows


def proposed(row):
    return {field:row.get('proposed'+field[0].upper()+field[1:], '') for field in
            ('canonicalCode','kind','labelSr','labelEn','labelDe','externalAlignment','exactGlottocode','broaderGlottocode','wikidataQid','relatedIdentifiers')}


def serialized(root):
    ET.indent(root, space='  ')
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='utf-8') + b'\n'


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as target:
        tmp = Path(target.name)
        target.write(data)
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def reconcile(directory=SESSION):
    review, baseline, rows = load_session(directory)
    tree = ET.parse(ROOT/'registry/raskovnik-overrides.xml').getroot()
    for record in list(tree.findall(NS+'reviewRecord')):
        if record.get('source') == directory.relative_to(ROOT).as_posix():
            tree.remove(record)
    by_id = {n.get('ident'):n for n in tree.findall(NS+'node')}
    candidates = {p['id']:p for p in baseline['profiles']}
    ancestors = {p['glottocode']:p for p in baseline['ancestorCandidates']}
    glottolog, _ = parse_glottolog(ROOT/'upstream/glottolog/5.3/languoid.csv')
    _, iana = parse_iana_registry(ROOT/'upstream/iana/2026-08-08/language-subtag-registry')
    spec = importlib.util.spec_from_file_location('candidate_import_validation', ROOT/'scripts/generate-candidates.py')
    generator = importlib.util.module_from_spec(spec); spec.loader.exec_module(generator)
    for name in ('parse_effective_persj_catalog','parse_iana_registry','parse_iso639_3','parse_glottolog','parse_wikidata_evidence','parse_cldr_german'):
        setattr(generator,name,lru_cache(maxsize=None)(getattr(generator,name)))
    records = []
    keyed = {r['recordType']+':'+r['id']:r for r in rows}
    for key in review['review']:
        if key not in keyed:
            raise ValueError('unmatched current saved decision: '+key)
    # Source consolidation is already explicitly authorized in the conversation.
    p = candidates['pl']
    keyed['tag-profile:pl'] = dict(id='pl',recordType='tag-profile',reviewQueue='READY_TO_CONFIRM',
        proposedCanonicalCode='pl',proposedKind=p['kindCandidate'],proposedLabelSr='пољски',proposedLabelEn='Polish',
        proposedLabelDe='Polnisch',proposedExternalAlignment='exact:poli1260',proposedWikidataQid=p['wikidataQidCandidate'],
        auditRationale='User explicitly consolidated Carpathian Polish into Polish on 2026-09-06; source labels remain catalogue evidence.')
    for key,row in sorted(keyed.items(),key=lambda pair:(pair[1]['recordType']=='ancestor',pair[0])):
        saved = review['review'].get(key)
        item = candidates.get(row['id']) if row['recordType']=='tag-profile' else ancestors.get(row['id'])
        if item is None:
            continue
        if not saved and row['reviewQueue'] not in ('READY_TO_CONFIRM','POLICY_RESOLVED'):
            continue
        if not saved and row['recordType']=='tag-profile' and item.get('approval'):
            continue
        values = copy.deepcopy(saved['values'] if saved else proposed(row))
        code = values.get('canonicalCode') or row['id']
        if row['recordType']=='ancestor':
            code = item['canonicalCodeCandidate']
        reviewer = 'ttasovac' if saved else 'Codex'
        date = (saved.get('updatedAt','2026-09-06')[:10] if saved else '2026-09-06')
        rationale = row.get('auditRationale','') or 'Pinned Glottolog classification and established ancestor display policy.'
        result = dict(key=key,canonicalCode=code,reviewer=reviewer,date=date,status='applied',rationale=rationale,
                      savedDecision=copy.deepcopy(saved),values=values)
        if row['recordType']=='ancestor':
            owner=next((n for n in tree.findall(NS+'node') if n.get('alignment')=='exact' and n.get('glottocode')==row['id'] and (n.get('ident')!=code or code in candidates)),None)
            if owner is not None:
                result['canonicalCode']=owner.get('ident')
                result['rationale']='Structural ancestor coalesces with exact reviewed profile '+owner.get('ident')+'; profile labels take precedence. '+rationale
                records.append(result)
                continue
        old = by_id.get(code)
        node = None
        try:
            validate_registered_tag(canonical_language_tag(code), iana)
            if row['recordType']=='tag-profile' and code != row['id']:
                raise ValueError('Canonical source migration required: '+row['id']+' → '+code+'; preserve proposal pending a provenance-pinned catalogue update.')
            if row['id']=='vel':
                raise ValueError('Source meaning вељотски denotes Vegliot, but registered vel / velu1238 denotes Dutch Low Saxon Veluws. Source mapping must be corrected; the proposed Veluws identity is not approved. Evidence: https://glottolog.org/resource/languoid/id/velu1238 ; https://hrcak.srce.hr/file/265826')
            exact = values.get('exactGlottocode','') or ''
            broader = values.get('broaderGlottocode','') or ''
            if exact and broader:
                raise ValueError('both exact and broader Glottolog assignments supplied')
            alignment = 'exact' if exact else 'broader' if broader else 'none'
            glot = exact or broader
            if not glot and values.get('externalAlignment'):
                alignment, glot = values['externalAlignment'].split(':',1)
            if row['recordType']=='ancestor':
                alignment,glot='exact',row['id']
            if glot and glot not in glottolog:
                raise ValueError('alignment absent from pinned Glottolog: '+glot)
            attrs=dict(ident=code,kind=values.get('kind') or item['kindCandidate'],selectable=str(item['selectableCandidate']).lower(),
                       alignment=alignment,reviewStatus='approved',reviewedBy=reviewer,reviewedOn=date)
            if glot: attrs['glottocode']=glot
            if old is not None and old.get('parent'): attrs['parent']=old.get('parent')
            attrs['wikidata']=values.get('wikidataQid') or ''
            if row['recordType']=='ancestor' and (any(n.get('wikidata')==attrs['wikidata'] and n.get('ident')!=code for n in tree.findall(NS+'node')) or any(p.get('wikidataQidCandidate')==attrs['wikidata'] and p['id']!=code for p in candidates.values())):
                attrs['wikidata']=''
                rationale += ' Wikidata evidence belongs to the reviewed language profile; the structural ancestor receives no exact QID.'

            node = ET.Element(NS+'node', attrs)
            additions = {v['language']:v for v in review.get('labelSupplements',[]) if v['key']==key}
            for language,suffix in [('sr','Sr'),('en','En'),('de','De')]:
                label = values.get('label'+suffix) or (additions.get(language,{}).get('value',''))
                if not label and row['recordType']=='ancestor' and language=='en':label=item['name']
                ET.SubElement(node,NS+'name',{XML+'lang':language,'source':'raskovnik-review'}).text=label or ''
            if old is not None:
                for alias in old.findall(NS+'alias'):
                    if alias.text != next(n.text for n in node.findall(NS+'name') if n.get(XML+'lang')==alias.get(XML+'lang')):
                        node.append(copy.deepcopy(alias))
            ET.SubElement(node,NS+'note',{'type':'reviewReason'}).text=rationale
            if values.get('relatedIdentifiers'):
                ET.SubElement(node,NS+'note',{'type':'reviewReason'}).text='Supporting identifiers only; no exact equivalence inferred: '+values['relatedIdentifiers']
            if saved and saved.get('note'):
                ET.SubElement(node,NS+'note',{'type':'reviewReason'}).text=saved['note']
            if row['id']=='book1242':
                ET.SubElement(node,NS+'note',{'type':'reviewReason'}).text='Administrative Glottolog Bookkeeping node, not a linguistic family; nonselectable and retained as classification context.'
            if old is not None: tree.remove(old)
            tree.append(node)
            with tempfile.TemporaryDirectory() as work:
                check=Path(work)/'overrides.xml';check.write_bytes(serialized(tree))
                parsed=parse_overrides(check)
                generator.parse_overrides=lambda *args, **kwargs:parsed
                generator.build_candidates()
            by_id[code]=node
        except (ValueError,RuntimeError) as error:
            if node is not None and node in list(tree):tree.remove(node)
            if old is not None and old not in list(tree):tree.append(old)
            result['status']='pending';result['rationale']=str(error)
        records.append(result)
    ordered = sorted(tree.findall(NS+'node'), key=lambda n:n.get('ident'))
    for n in tree.findall(NS+'node'):tree.remove(n)
    tree[:0]=ordered
    for result in records:
        record=ET.SubElement(tree,NS+'reviewRecord',dict(key=result['key'],status=result['status'],source=directory.relative_to(ROOT).as_posix(),reviewer=result['reviewer'],date=result['date']))
        ET.SubElement(record,NS+'payload').text=json.dumps({'values':result['values'],'savedDecision':result['savedDecision']},ensure_ascii=False,sort_keys=True)
        ET.SubElement(record,NS+'rationale').text=result['rationale']
    return serialized(tree), records


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session',type=Path,default=SESSION)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--apply',action='store_true');mode.add_argument('--check',action='store_true');mode.add_argument('--dry-run',action='store_true')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    try:
        data, records=reconcile(args.session)
        report=(json.dumps(records,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
        if args.report:atomic_write(args.report,report)
        print(json.dumps(dict(Counter(r['status'] for r in records)),sort_keys=True))
        for record in records:
            if record['status']=='pending':print(record['key']+': '+record['rationale'])
        target=ROOT/'registry/raskovnik-overrides.xml'
        if args.check and target.read_bytes()!=data:raise ValueError('ledger differs from reproducible review import')
        if args.apply:atomic_write(target,data)
        return 0
    except (ValueError,RuntimeError,OSError,KeyError) as error:
        parser.exit(1,str(error)+'\n')

if __name__=='__main__':raise SystemExit(main())
