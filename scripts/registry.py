#!/usr/bin/env python3
"""Validate the editable TEI master and derive deployment metadata offline."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from xml.etree import ElementTree as E
from registry_integrity import validate_registry
from registry_standards import parse_iana_registry, parse_iso639_3, validate_registered_tag

ROOT = Path(__file__).resolve().parents[1]
T = '{http://www.tei-c.org/ns/1.0}'
X = '{http://www.w3.org/XML/1998/namespace}'
M = '{https://raskovnik.org/ns/language-registry/manifest}'
POLICY = 'language-tag-coverage-v1'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checked(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise ValueError((result.stderr or result.stdout).strip())


def standards():
    lock = json.loads((ROOT/'registry/standards-lock.json').read_text())
    for source in lock['sources']:
        for record in source['files']:
            data = (ROOT/record['path']).read_bytes()
            if len(data) != record['bytes'] or digest(data) != record['sha256']:
                raise ValueError('pinned standard changed: '+record['path'])
    return lock


def validate(data):
    standards()
    root = E.fromstring(data)
    change = root.find(T+'teiHeader/'+T+'revisionDesc/'+T+'change[@type="registryVersion"]')
    nodes = [n for n in root.iter() if n.tag in (T+'language', T+'languageGrp')]
    if change is None:
        raise ValueError('registry version missing')
    validate_registry(data)
    ids = {n.get(X+'id'): n for n in root.iter() if n.get(X+'id')}
    for n in root.iter():
        for attr in ('source','ana','corresp','target','resp','who'):
            for pointer in n.get(attr,'').split():
                if pointer.startswith('#') and pointer[1:] not in ids:
                    raise ValueError('unresolved '+attr+' pointer: '+pointer)
    for n in root.iter():
        if n.get('source'):
            source=ids.get(n.get('source').removeprefix('#'))
            if source is None or source.tag!=T+'bibl' or source.get('type')!='registrySource':
                raise ValueError('source pointer must resolve to a registry source')
        if n.tag==T+'ref' and n.get('type') in ('classificationSource','catalogSource'):
            source=ids.get(n.get('target','').removeprefix('#'))
            if source is None or source.get('type')!='registrySource':
                raise ValueError('bibliographic source reference has the wrong target type')
        if n.tag==T+'note' and n.get('type')=='alternateClassification':
            classification=ids.get(n.get('ana','').removeprefix('#'))
            if classification is None or classification.get('type')!='classification':
                raise ValueError('alternate classification must reference a classification record')
        if n.tag==T+'ref' and n.get('type')=='alternatePathNode':
            target=ids.get(n.get('target','').removeprefix('#'))
            if target is None or target.tag!=T+'ident' or target.get('type')!='BCP47':
                raise ValueError('alternate path must reference a canonical node identifier')
    _, iana = parse_iana_registry(ROOT/'upstream/iana/2026-08-08/language-subtag-registry')
    iso, _, _ = parse_iso639_3(ROOT/'upstream/iso-639-3/2026-07-22/iso-639-3.tab')
    exact = {}
    for n in nodes:
        code = n.get('ident')
        if code.startswith('x-'):
            raise ValueError('private tags require a registered base: '+code)
        validate_registered_tag(code,iana)
        claims = n.findall(T+'ident')
        if len({c.get('type') for c in claims}) != len(claims):
            raise ValueError('duplicate identifier type: '+code)
        for c in claims:
            key = (c.get('type'), c.text)
            if c.get('type') in ('Glottolog','Wikidata'):
                pattern = r'[a-z0-9]{8}' if c.get('type')=='Glottolog' else r'Q[1-9][0-9]*'
                if not re.fullmatch(pattern,c.text or '') or key in exact:
                    raise ValueError('invalid or duplicate exact identifier: '+str(key))
                exact[key] = code
        for exclusion in n.findall(T+'note[@type="excludedExactIdentifier"]'):
            if any(c.get('type')==exclusion.get('subtype') and c.text==exclusion.text for c in claims):
                raise ValueError('reviewed narrower identifier cannot be promoted: '+code)
        iso_claim = n.findtext(T+'ident[@type="ISO639-3"]')
        if iso_claim:
            record = iso.get(iso_claim)
            if record is None:
                raise ValueError('unknown ISO 639-3: '+iso_claim)
            expected = {'ISO639-1':record.part1,'ISO639-2B':record.part2b,'ISO639-2T':record.part2t,'ISO639-3':record.identifier}
            actual = {c.get('type'):c.text for c in claims if c.get('type') in expected}
            if actual != {k:v for k,v in expected.items() if v}:
                raise ValueError('incomplete or inconsistent ISO inventory: '+code)
            if '-x-' not in code and code != (record.part1 or record.identifier):
                raise ValueError('canonical code disagrees with exact ISO identity: '+code)
        elif any(c.get('type') in ('ISO639-1','ISO639-2B','ISO639-2T') for c in claims):
            raise ValueError('ISO identifiers require their ISO 639-3 identity: '+code)
        profiles = n.findall(T+'note[@type="tagProfile"]')
        if len(profiles)>1 or any(c.get('subtype')!='direct' for c in profiles):
            raise ValueError('invalid direct profile inventory: '+code)
        for name in n.findall(T+'name'):
            if name.get('type') in ('languageName','sourceLabel','sourceRecordLabel'):
                if not name.get(X+'id') or ids.get(name.get('source','').removeprefix('#')) is None:
                    raise ValueError('name identity/provenance missing: '+code)
        own_records={c.get(X+'id') for c in n.findall(T+'name[@type="sourceLabel"]')}
        for c in n:
            if c.get('type') in ('sourceRecordLabel','sourceRecordNote') and c.get('corresp','').removeprefix('#') not in own_records:
                raise ValueError('source-record label/note must reference its own source record: '+code)
        points=set()
        for place in n.findall(T+'settingDesc/'+T+'place'):
            location=place.find(T+'location')
            if location is None:raise ValueError('place requires a location: '+code)
            point=(location.get('type'),location.get('source'),place.findtext(T+'idno[@type="sourceNode"]'))
            if point in points or any(':' in (x or '').removeprefix('#') for x in point):
                raise ValueError('ambiguous location identity: '+code)
            points.add(point)
        for source in n.findall(T+'name[@type="sourceLabel"]'):
            catalog = next((ids.get(t[1:]) for t in source.get('ana','').split() if t.startswith('#catalog-')),None)
            if catalog is None or catalog.get('type') != 'dictionaryLanguageCatalog':
                raise ValueError('source record catalog is not a catalog: '+code)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/'registry.xml';path.write_bytes(data)
        checked(['jing',str(ROOT/'registry/schema/lex-0-f6d51f29.rng'),str(path)])
        checked(['xmllint','--noout','--schematron',str(ROOT/'registry/schema/language-registry.sch'),str(path)])
    return root


def manifest(data, root):
    change = root.find(T+'teiHeader/'+T+'revisionDesc/'+T+'change[@type="registryVersion"]')
    displays = root.findall('.//'+T+'bibl[@type="classification"][@subtype="display"]')
    if len(displays)!=1:
        raise ValueError('exactly one display classification is required')
    result = E.Element(M+'registryManifest',dict(formatVersion='2',compatibilityPolicy=POLICY,registryVersion=change.get('n'),builtAt=change.get('when'),contentSha256=digest(data),displayClassificationId=displays[0].get(X+'id')))
    lex = next(s for s in standards()['sources'] if s['id']=='lex-0')
    E.SubElement(result,M+'schema',dict(id='tei-lex-0',version=lex['version'],revision=lex['revision'],sha256=lex['files'][0]['sha256']))
    sources = E.SubElement(result,M+'sources')
    for b in root.findall('.//'+T+'bibl[@type="registrySource"]'):
        attrs = {X+'id':b.get(X+'id'),'title':b.findtext(T+'title'),'url':b.find(T+'ref[@type="sourceURL"]').get('target')}
        for key in ('upstreamId','version','revision'):
            value = b.findtext(T+'idno[@type="'+key+'"]')
            if value is not None:attrs[key]=value
        s = E.SubElement(sources,M+'source',attrs)
        lic = b.find(T+'ref[@type="licence"]')
        if lic is not None:E.SubElement(s,M+'licence',name=lic.text,url=lic.get('target'))
        E.SubElement(s,M+'attribution').text=b.findtext(T+'note[@type="attribution"]')
        for f in b.findall(T+'ref[@type="sourceFile"]'):
            E.SubElement(s,M+'file',path=f.get('target'),bytes=f.get('n'),sha256=f.text)
    classifications = E.SubElement(result,M+'classifications')
    for b in root.findall('.//'+T+'bibl[@type="classification"]'):
        c = E.SubElement(classifications,M+'classification',{X+'id':b.get(X+'id')})
        version = b.findtext(T+'idno[@type="version"]')
        if version:c.set('version',version)
        for lang in ('sr','en','de'):
            E.SubElement(c,M+'label',{X+'lang':lang}).text=b.findtext(T+'title[@'+X+'lang="'+lang+'"]')
        for ref in b.findall(T+'ref[@type="classificationSource"]'):E.SubElement(c,M+'source',ref=ref.get('target'))
    catalogs = E.SubElement(result,M+'catalogs')
    for b in root.findall('.//'+T+'bibl[@type="dictionaryLanguageCatalog"]'):
        c=E.SubElement(catalogs,M+'catalog',{X+'id':b.get(X+'id'),'dictionaryId':b.findtext(T+'idno[@type="dictionaryId"]')})
        E.SubElement(c,M+'source',ref=b.find(T+'ref[@type="catalogSource"]').get('target'))
    E.register_namespace('',M[1:-1]);E.indent(result,space='  ')
    output=b'<?xml version="1.0" encoding="UTF-8"?>\n'+E.tostring(result,encoding='utf-8')+b'\n'
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'manifest.xml';path.write_bytes(output)
        checked(['jing',str(ROOT/'registry/schema/registry-manifest.rng'),str(path)])
    return output


def release_metadata(xar):
    with zipfile.ZipFile(xar) as archive:
        names=archive.namelist()
        required={'registry.xml','manifest.xml','post-install.xq','expath-pkg.xml','repo.xml','exist.xml','cxan.xml'}
        if set(names)!=required or len(names)!=len(required):raise ValueError('unexpected XAR inventory')
        data=archive.read('registry.xml');r=validate(data);m=manifest(data,r)
        if data!=(ROOT/'registry/registry.xml').read_bytes() or archive.read('manifest.xml')!=m:raise ValueError('XAR differs from validated master')
        pkg=E.fromstring(archive.read('expath-pkg.xml'));version=pkg.get('version')
        if pkg.get('name')!='http://raskovnik.org/raskovnik-language-registry':raise ValueError('incorrect XAR package URI')
        if xar.name!='raskovnik-language-registry-'+version+'.xar':raise ValueError('incorrect XAR filename')
        return dict(id='raskovnik-language-registry',package_uri=pkg.get('name'),version=version,filename=xar.name,artifact_sha256='sha256:'+digest(xar.read_bytes()),registry_version=r.find(T+'teiHeader/'+T+'revisionDesc/'+T+'change[@type="registryVersion"]').get('n'),registry_content_sha256='sha256:'+digest(data))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['check','build','release'])
    parser.add_argument('--registry',type=Path,default=ROOT/'registry/registry.xml')
    parser.add_argument('--xar',type=Path)
    args=parser.parse_args()
    try:
        data=args.registry.read_bytes();root=validate(data);output=manifest(data,root)
        if args.command=='build':
            (ROOT/'dist').mkdir(exist_ok=True)
            (ROOT/'dist/registry.xml').write_bytes(data);(ROOT/'dist/manifest.xml').write_bytes(output)
        if args.command=='release':
            if args.xar is None:raise ValueError('--xar is required')
            metadata=release_metadata(args.xar)
            (ROOT/'dist/release.json').write_text(json.dumps(metadata,indent=2)+'\n')
        print('Registry '+args.command+' passed')
        return 0
    except (ValueError,RuntimeError,OSError,E.ParseError,AttributeError,TypeError) as error:
        print('Registry validation failed: '+str(error),file=sys.stderr)
        return 1

if __name__=='__main__':sys.exit(main())
