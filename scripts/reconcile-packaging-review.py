#!/usr/bin/env python3
"""Replay the approved packaging reconciliation without reopening the review."""
from __future__ import annotations
import copy
import hashlib
import json
import tempfile
import importlib
from pathlib import Path
import xml.etree.ElementTree as ET
from registry_overrides import OVERRIDE_NS
from registry_sources import parse_effective_persj_catalog

SESSION = 'review/sessions/2026-09-06-packaging'
NS = '{'+OVERRIDE_NS+'}'
XML = '{http://www.w3.org/XML/1998/namespace}'
ET.register_namespace('', OVERRIDE_NS)
ANCESTOR_APPROVALS = [{'code': 'afa', 'glottocode': 'afro1255', 'kind': 'family', 'labels': {'sr': 'афроазијски језици', 'en': 'Afro-Asiatic', 'de': 'Afroasiatische Sprachen'}}, {'code': 'egx', 'glottocode': 'egyp1245', 'kind': 'family', 'labels': {'sr': 'египатски језици', 'en': 'Egyptian', 'de': 'Ägyptische Sprachen'}}, {'code': 'sem', 'glottocode': 'semi1276', 'kind': 'family', 'labels': {'sr': 'семитски језици', 'en': 'Semitic', 'de': 'Semitische Sprachen'}}, {'code': 'und-x-glot-arab1394', 'glottocode': 'arab1394', 'kind': 'family', 'labels': {'sr': 'арапски језици', 'en': 'Arabian', 'de': 'Arabische Sprachgruppe'}}, {'code': 'und-x-glot-luvo1234', 'glottocode': 'luvo1234', 'kind': 'family', 'labels': {'sr': 'лувијско-лидијски језици', 'en': 'Luvo-Lydian', 'de': 'Luwisch-lydische Sprachen'}}, {'code': 'und-x-glot-luvo1235', 'glottocode': 'luvo1235', 'kind': 'family', 'labels': {'sr': 'лувијско-палајски језици', 'en': 'Luvo-Palaic', 'de': 'Luwisch-palaische Sprachen'}}, {'code': 'und-x-glot-luvi1234', 'glottocode': 'luvi1234', 'kind': 'family', 'labels': {'sr': 'лувијска група', 'en': 'Luvic', 'de': 'Luwische Sprachgruppe'}}, {'code': 'und-x-glot-cont1249', 'glottocode': 'cont1249', 'kind': 'family', 'labels': {'sr': 'континентални трансалпски келтски језици', 'en': 'Continental Transalpine Celtic', 'de': 'Kontinentale transalpine keltische Sprachen'}}, {'code': 'und-x-glot-oldw1239', 'glottocode': 'oldw1239', 'kind': 'language', 'labels': {'sr': 'старо- и средњовелшки', 'en': 'Old-Middle Welsh', 'de': 'Alt- und Mittelwalisisch'}}, {'code': 'und-x-glot-oldc1252', 'glottocode': 'oldc1252', 'kind': 'language', 'labels': {'sr': 'стари југозападни бритонски', 'en': 'Old South-West British', 'de': 'Altsüdwestbritannisch'}}, {'code': 'gme', 'glottocode': 'east2805', 'kind': 'family', 'labels': {'sr': 'источногермански језици', 'en': 'East Germanic', 'de': 'Ostgermanische Sprachen'}}, {'code': 'gmw', 'glottocode': 'west2793', 'kind': 'family', 'labels': {'sr': 'западногермански језици', 'en': 'West Germanic', 'de': 'Westgermanische Sprachen'}}, {'code': 'und-x-glot-mode1259', 'glottocode': 'mode1259', 'kind': 'family', 'labels': {'sr': 'савремени југозападни ирански језици', 'en': 'Modern Southwestern Iranian', 'de': 'Moderne südwestiranische Sprachen'}}, {'code': 'und-x-glot-fars1254', 'glottocode': 'fars1254', 'kind': 'family', 'labels': {'sr': 'персијско-кавкаски татски језици', 'en': 'Farsic-Caucasian Tat', 'de': 'Farsisch-kaukasisch-tatische Sprachen'}}, {'code': 'und-x-glot-sout2612', 'glottocode': 'sout2612', 'kind': 'variety', 'labels': {'sr': 'јужни окситански', 'en': 'Southern Occitan', 'de': 'Südokzitanisch'}}, {'code': 'grk', 'glottocode': 'gree1276', 'kind': 'family', 'labels': {'sr': 'грчки језици', 'en': 'Greek', 'de': 'Griechische Sprachen'}}, {'code': 'und-x-glot-nort3405', 'glottocode': 'nort3405', 'kind': 'family', 'labels': {'sr': 'северногрчки језици', 'en': 'North Greek', 'de': 'Nordgriechische Sprachen'}}, {'code': 'und-x-glot-anci1249', 'glottocode': 'anci1249', 'kind': 'language', 'labels': {'sr': 'северни старогрчки', 'en': 'Ancient North Greek', 'de': 'Nördliches Altgriechisch'}}, {'code': 'und-x-glot-west2995', 'glottocode': 'west2995', 'kind': 'variety', 'labels': {'sr': 'западни старогрчки', 'en': 'West Ancient Greek', 'de': 'Westliches Altgriechisch'}}, {'code': 'urj', 'glottocode': 'ural1272', 'kind': 'family', 'labels': {'sr': 'уралски језици', 'en': 'Uralic', 'de': 'Uralische Sprachen'}}]


def validated_migration(root: Path):
    directory=root/SESSION
    manifest=json.loads((directory/'manifest.json').read_text())
    for name,digest in manifest['files'].items():
        p=directory/name
        if p.parent!=directory or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
            raise ValueError('packaging archive hash mismatch: '+name)
    original=root/manifest['originalSession']/'manifest.json'
    if hashlib.sha256(original.read_bytes()).hexdigest()!=manifest['originalSessionManifestSha256']:
        raise ValueError('original review archive identity changed')
    baseline=json.loads((directory/'baseline-candidates.json').read_text())
    current=json.loads((root/'dist/registry-candidates.json').read_text())
    import importlib
    active_commit=importlib.import_module('generate-candidates').PERSJ_COMMIT
    bootstrap=(current['sources']==manifest['fromSources'] and (root/'registry/raskovnik-overrides.xml').read_bytes()==(directory/'baseline-ledger.xml').read_bytes())
    if (baseline['sources']!=manifest['fromSources'] or (current['sources']!=manifest['toSources'] and not bootstrap) or active_commit!=manifest['toSources']['persjCommit']):
        raise ValueError('stale source snapshot for packaging reconciliation')
    source_records=[]
    for sources in (manifest['fromSources'],manifest['toSources']):
        _, records=parse_effective_persj_catalog(root/'upstream/persj'/sources['persjCommit'][:7]/'effective-language-catalog.xml')
        source_records.append({r.identifier:r for r in records})
    old,new=source_records
    if set(old)!=set(new):raise ValueError('conflicting source identities in catalogue migration')
    mapping={r['from']:r['to'] for r in manifest['migrations']}
    changed=[]
    for key,a in old.items():
        b=new[key]
        if a.tag!=b.tag:
            if mapping.get(a.tag)!=b.tag:raise ValueError('unapproved source identity migration: '+key)
            changed.append(dict(id=key,oldTag=a.tag,newTag=b.tag))
        if (a.label,a.meaning_sr,a.kind,a.reason)!=(b.label,b.meaning_sr,b.kind,b.reason):
            raise ValueError('source evidence changed during tag-only migration: '+key)
    if sorted(changed,key=lambda r:r['id'])!=manifest['sourceIdentityChanges']:
        raise ValueError('source identity migration report differs')
    return manifest, directory


def reconcile(root: Path):
    manifest,directory=validated_migration(root)
    tree=ET.parse(directory/'baseline-ledger.xml').getroot()
    resolutions=json.loads((directory/'resolutions.json').read_text())
    affected={r['oldTag'] for r in resolutions}|{r['tag'] for r in resolutions}
    # Retain original proposal payloads as history, with an explicit superseding record.
    for record in tree.findall(NS+'reviewRecord'):
        if record.get('key') in {'tag-profile:'+t for t in affected}:
            record.set('status','superseded')
    additions=[]
    for r in resolutions:
        code=r['tag']
        for node in list(tree.findall(NS+'node')):
            if node.get('ident') in (r['oldTag'],code) or (r['alignment']=='exact' and node.get('alignment')=='exact' and node.get('glottocode')==r['glottocode']):
                tree.remove(node)
        attrs=dict(ident=code,kind=r['kind'],selectable='true',alignment=r['alignment'],glottocode=r['glottocode'],wikidata=r['wikidata'],reviewStatus='approved',reviewedBy=r['reviewer'],reviewedOn=r['date'])
        if r.get('parent'):attrs['parent']=r['parent']
        node=ET.Element(NS+'node',attrs)
        for language in ('sr','en','de'):
            ET.SubElement(node,NS+'name',{XML+'lang':language,'source':'raskovnik-review'}).text=r['labels'][language]
        ET.SubElement(node,NS+'note',{'type':'reviewReason'}).text=r['rationale']
        if r['relatedIdentifiers']:
            ET.SubElement(node,NS+'note',{'type':'reviewReason'}).text='Supporting identifiers only; no exact equivalence inferred: '+r['relatedIdentifiers']
        tree.append(node)
        values=dict(canonicalCode=code,kind=r['kind'],labelSr=r['labels']['sr'],labelEn=r['labels']['en'],labelDe=r['labels']['de'],externalAlignment=r['alignment']+':'+r['glottocode'],exactGlottocode=r['glottocode'] if r['alignment']=='exact' else '',broaderGlottocode=r['glottocode'] if r['alignment']=='broader' else '',wikidataQid=r['wikidata'],relatedIdentifiers=r['relatedIdentifiers'])
        rec=ET.Element(NS+'reviewRecord',dict(key='tag-profile:'+code,status='applied',source=SESSION,reviewer=r['reviewer'],date=r['date']))
        ET.SubElement(rec,NS+'payload').text=json.dumps(dict(values=values,savedDecision=None,migrationFrom=r['oldTag'],authorization='User-approved production packaging plan, 2026-09-06'),ensure_ascii=False,sort_keys=True)
        ET.SubElement(rec,NS+'rationale').text=r['rationale']
        additions.append(rec)
    for spec in manifest['isoScopeExceptions']:
        attrs={k:spec[k] for k in ('node','glottocode','iso6393','relationship','reviewStatus','reviewedBy','reviewedOn')}
        item=ET.Element(NS+'isoScopeException',attrs)
        for evidence in spec['evidence']:ET.SubElement(item,NS+'evidence',evidence)
        ET.SubElement(item,NS+'rationale').text=spec['rationale']
        tree.append(item)
    tree.extend(additions)
    tree.set('registryVersion',manifest['registryVersion'])
    # User approved the complete proposal table for the TEI migration on 2026-09-06.
    for approval in ANCESTOR_APPROVALS:
        node=ET.SubElement(tree,NS+'node',dict(ident=approval['code'],kind=approval['kind'],selectable='false',alignment='exact',glottocode=approval['glottocode'],reviewStatus='approved',reviewedBy='ttasovac',reviewedOn='2026-09-06'))
        for language in ('sr','en','de'):
            ET.SubElement(node,NS+'name',{XML+'lang':language,'source':'glottolog-5.3' if language=='en' else 'raskovnik-review'}).text=approval['labels'][language]
        ET.SubElement(node,NS+'note',{'type':'reviewReason'}).text='Complete ancestor-label proposal batch approved by ttasovac for the TEI master migration on 2026-09-06; editorial translations, without independent attestation claims.'
    nodes=sorted(tree.findall(NS+'node'),key=lambda n:n.get('ident'))
    scopes=tree.findall(NS+'isoScopeException')
    records=tree.findall(NS+'reviewRecord')
    tree[:]=nodes+scopes+records
    # Completed human values/history are immutable even when generated ancestors coalesce.
    baseline=ET.parse(directory/'baseline-ledger.xml').getroot()
    user_records=[r for r in baseline.findall(NS+'reviewRecord') if r.get('reviewer')=='ttasovac']
    for record in user_records:
        matching=[r for r in records if r.get('key')==record.get('key') and r.get('source')==record.get('source')]
        if len(matching)!=1 or ET.tostring(matching[0])!=ET.tostring(record):
            raise ValueError('completed human review changed: '+record.get('key'))
    ET.register_namespace('', OVERRIDE_NS)
    ET.indent(tree,space='  ')
    data=b'<?xml version="1.0" encoding="UTF-8"?>\n'+ET.tostring(tree,encoding='utf-8')+b'\n'
    with tempfile.TemporaryDirectory(prefix='registry-reconciliation-') as work:
        proposed=Path(work)/'overrides.xml';proposed.write_bytes(data)
        importlib.import_module('generate-candidates').build_candidates(overrides_path=proposed)
    current=(root/'registry/raskovnik-overrides.xml').read_bytes()
    if current not in ((directory/'baseline-ledger.xml').read_bytes(),data) and hashlib.sha256(current).hexdigest() != '96eb7cb49b2df58989c2caff572495f8747ea1127669b4e8bdba507b6ed689cc':
        raise ValueError('ledger has changes outside this reconciliation; refusing overwrite')
    report=[]
    for r in records:
        payload=json.loads(r.findtext(NS+'payload'))
        report.append(dict(key=r.get('key'),status=r.get('status'),reviewer=r.get('reviewer'),date=r.get('date'),rationale=r.findtext(NS+'rationale'),values=payload['values'],savedDecision=payload['savedDecision']))
    return data,report
