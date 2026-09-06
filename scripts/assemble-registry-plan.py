#!/usr/bin/env python3
"""Assemble the production compiler input from the closed registry ledger."""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

from registry_build import PLAN_SCHEMA, RegistryBuildError, build_artifacts, load_sources, plan_payload_sha256, validate_production_plan_provenance
from registry_overrides import parse_overrides
from registry_sources import parse_effective_persj_catalog, sha256
from importlib import import_module

ROOT=Path(__file__).resolve().parents[1]


def compatibility_from_backend(backend, dictionary_ids):
    manifest=json.loads((backend/'metadata/dictionary-version-manifest.json').read_text())
    result=[]
    for ident in sorted(set(dictionary_ids)):
        data=(backend/f'dictionaries/{ident}/src/main/xar-resources/{ident}.pcified.xml').read_bytes()
        # Exactly the backend dictionary_resource_hash contract: omit the XML declaration.
        data=re.sub(br'^(?:\xef\xbb\xbf)?<\?xml[^>]*>\s*',b'',data)
        actual='sha256:'+hashlib.sha256(data).hexdigest()
        if manifest[ident].get('resource_hash')!=actual:
            raise RegistryBuildError('backend resource/manifest hash mismatch: '+ident)
        result.append(dict(id=ident,resourceHash=actual))
    return result


def identifiers(item, ancestor=False):
    result={}
    if ancestor:result['Glottolog']=item['glottocode']
    elif item.get('glottolog',{} ) and item['glottolog']['relationship']=='exact':result['Glottolog']=item['glottolog']['glottocode']
    bare=ancestor or item['id']==item['iana']['primary']
    iso=item.get('iso639') if bare else None
    if iso:
        result.update({kind:iso[key] for kind,key in [('ISO639-1','part1'),('ISO639-2B','part2B'),('ISO639-2T','part2T'),('ISO639-3','part3')] if iso.get(key)})
    if (item.get('ianaScope') if ancestor else item['iana']['scope'] if bare else None)=='collection':
        result['ISO639-5']=item.get('canonicalCodeCandidate',item.get('id'))
    if item.get('wikidataQidCandidate'):result['Wikidata']=item['wikidataQidCandidate']
    return [dict(type=k,value=v) for k,v in sorted(result.items())]


def assemble(candidates, source_records, source_ids, compatibility, version, reviewed_on, evidence_notes=None):
    commit=candidates['sources']['persjCommit']
    catalog_source='src-persj-catalog-'+commit[:7]
    provenance={'raskovnik-review':'src-raskovnik-review','persj-conversion-catalog':catalog_source,
                'glottolog-5.3':'src-glottolog-5-3','cldr-48.2':'src-cldr-48-2','cldr-exact':'src-cldr-48-2','iana-2026-08-08':'src-iana-2026-08-08'}
    nodes={};glot_codes={a['glottocode']:a['canonicalCodeCandidate'] for a in candidates['ancestorCandidates']}
    for item in candidates['profiles']:
        if item.get('glottolog') and item['glottolog']['relationship']=='exact':glot_codes[item['glottolog']['glottocode']]=item['id']
    for ancestor, items in [(True,candidates['ancestorCandidates']),(False,candidates['profiles'])]:
        for item in items:
            code=item['canonicalCodeCandidate'] if ancestor else item['id']
            if ancestor and glot_codes.get(item['glottocode'])!=code:continue
            if not code:raise RegistryBuildError('unresolved canonical ancestor')
            parent=item.get('parentCandidate')
            if parent is None:
                if ancestor:parent=glot_codes.get(item['parentGlottocode'])
                elif item.get('glottolog'):
                    path=[x['canonicalCode'] for x in item['lineage'] if x['canonicalCode']!=code]
                    parent=path[-1] if path else None
            labels=item['preferredLabels']
            label_sources={l:provenance.get(item['labelProvenance'][l]) if labels[l] else None for l in ('sr','en','de')}
            for l in ('sr','en','de'):
                if labels[l] and label_sources[l] not in source_ids:raise RegistryBuildError('unresolved label provenance: '+code+'/'+l)
            aliases={l:[dict(value=a['value'],sourceId=provenance[a['source']]) for a in item['aliasCandidates'][l]] for l in ('sr','en','de')}
            note=dict(sr=None,en=evidence_notes[code],de=None) if evidence_notes and code in evidence_notes else None
            if code=='und-x-glot-book1242':note=dict(sr=None,en='Administrative Glottolog Bookkeeping node; not a linguistic family.',de=None)
            node=dict(id=code,parentId=parent,kind=item['kindCandidate'],selectable=item['selectableCandidate'],classificationNote=note,
                      classificationStatus='reviewed',labels=labels,labelSources=label_sources,aliases=aliases,identifiers=identifiers(item,ancestor),
                      locations=[],alternateLineages=[],directTagProfileIds=[] if ancestor else [code])
            glot=item.get('glottolog') if not ancestor else None
            if glot and glot['relationship']=='exact' and node['kind'] in ('language','variety') and glot.get('latitude') is not None and glot.get('longitude') is not None:
                node['locations']=[dict(type='representative',latitude=glot['latitude'],longitude=glot['longitude'],sourceId='src-glottolog-5-3',sourceNodeId=glot['glottocode'])]
            nodes[code]=node
    children=defaultdict(list)
    for code,node in nodes.items():
        if node['parentId'] is not None and node['parentId'] not in nodes:raise RegistryBuildError('unresolved parent: '+code)
        children[node['parentId']].append(code)
    ordered=[];visited=set()
    def visit(code):
        if code in visited:raise RegistryBuildError('classification cycle: '+code)
        visited.add(code);ordered.append(nodes[code])
        for child in sorted(children[code]):visit(child)
    for code in sorted(children[None]):visit(code)
    if len(visited)!=len(nodes):raise RegistryBuildError('classification contains unreachable cycle')
    profiles=[dict(id=p['id'],tag=p['id'],displayNodeId=p['id'],labels=p['preferredLabels'],sourceRecordIds=sorted(p['sourceRecordIds'])) for p in sorted(candidates['profiles'],key=lambda p:p['id'])]
    records=[]
    for source in sorted(source_records,key=lambda s:s.identifier):
        labels=dict(nodes[source.tag]['labels']);labels['sr']=source.meaning_sr
        records.append(dict(id=source.identifier,kind='compound-language-label' if source.kind=='compound' else 'language-label',labels=labels,
                            abbreviation=None if source.kind=='full-name' else source.label,mappedTagProfileId=source.tag,
                            note=dict(sr=None,en=source.reason,de=None) if source.reason else None,sourceId=catalog_source,catalogId='catalog-isj-persj',sourceLabel=source.label))
    return dict(schemaVersion=PLAN_SCHEMA,approval=dict(mode='release',reviewedBy='Codex',reviewedOn=reviewed_on,candidatesSha256='',editorialReportSha256='',overridesSha256='',planPayloadSha256=''),
                registryVersion=version,releasedAt=reviewed_on+'T00:00:00Z',displayClassificationId='classification-glottolog-5-3',
                classifications=[dict(id='classification-glottolog-5-3',labels=dict(sr='Глотологова класификација',en='Glottolog classification',de='Glottolog-Klassifikation'),version='5.3',sourceIds=['src-glottolog-5-3','src-raskovnik-review'])],
                catalogs=[dict(id='catalog-isj-persj',dictionaryId='ISJ.PERSJ',sourceId=catalog_source)],compatibleDictionaries=compatibility,nodes=ordered,tagProfiles=profiles,sourceRecords=records)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend',type=Path,required=True)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    try:
        for command in [('check-inputs.py',),('generate-candidates.py','--check'),('check-editorial-gate.py',)]:
            subprocess.run([sys.executable,str(ROOT/'scripts'/command[0]),*command[1:]],check=True)
        candidates=json.loads((ROOT/'dist/registry-candidates.json').read_text())
        ledger=parse_overrides(ROOT/'registry/raskovnik-overrides.xml')
        sources=load_sources(json.loads((ROOT/'upstream/sources.json').read_text()),json.loads((ROOT/'registry/source-publication-metadata.json').read_text()),ROOT)
        _, records=parse_effective_persj_catalog(ROOT/'upstream/persj'/candidates['sources']['persjCommit'][:7]/'effective-language-catalog.xml')
        compatibility=compatibility_from_backend(args.backend, ['ISJ.PERSJ','MBRT.RDG'])
        evidence_notes={}
        for record in ET.parse(ROOT/'registry/raskovnik-overrides.xml').getroot().findall('{https://raskovnik.org/ns/language-registry/overrides}reviewRecord'):
            if record.get('status')!='applied':continue
            payload=json.loads(record.find('{https://raskovnik.org/ns/language-registry/overrides}payload').text)
            values=payload['values']
            if values.get('relatedIdentifiers'):
                evidence_notes[values['canonicalCode']]='Supporting identifiers only; no exact equivalence inferred: '+values['relatedIdentifiers']
        plan=assemble(candidates,records,{s['manifestId'] for s in sources},compatibility,ledger.version,max(n.reviewed_on for n in ledger.nodes.values()),evidence_notes)
        for field,path in [('candidatesSha256','dist/registry-candidates.json'),('editorialReportSha256','dist/editorial-review.tsv'),('overridesSha256','registry/raskovnik-overrides.xml')]:plan['approval'][field]=sha256(ROOT/path)
        plan['approval']['planPayloadSha256']=plan_payload_sha256(plan)
        validate_production_plan_provenance(plan,ROOT)
        build_artifacts(plan,json.loads((ROOT/'upstream/sources.json').read_text()),json.loads((ROOT/'registry/source-publication-metadata.json').read_text()),ROOT)
        output=(json.dumps(plan,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode();target=ROOT/'dist/effective-registry-plan.json'
        if args.check:
            if not target.exists() or target.read_bytes()!=output:raise RegistryBuildError('effective plan differs from approved inputs')
        else:
            # Reuse the importer's atomic single-file installation primitive.
            import_module('import-review').atomic_write(target,output)
        print('effective registry plan verified' if args.check else 'effective registry plan assembled')
        return 0
    except (OSError,ValueError,RegistryBuildError,subprocess.CalledProcessError) as error:
        parser.exit(1,str(error)+'\n')

if __name__=='__main__':raise SystemExit(main())
