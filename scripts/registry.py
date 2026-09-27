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
SCHEMA_ROOT = ROOT/'registry/schema'
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


def validate_glottolog(root):
    review = json.loads((ROOT/'registry/glottolog-review.json').read_text())
    source = root.find('.//'+T+'bibl[@'+X+'id="src-glottolog-5-3"]')
    if source is None or source.findtext(T+'idno[@type="version"]') != review['version']:
        raise ValueError('Glottolog review version disagrees with registry provenance')
    if not any(f.get('target') == review['source'] and f.text == review['sha256']
               for f in source.findall(T+'ref[@type="sourceFile"]')):
        raise ValueError('Glottolog review snapshot disagrees with registry provenance')
    records = review['records']
    for node in root.iter():
        if node.tag not in (T+'language', T+'languageGrp'):
            continue
        code = node.findtext(T+'ident[@type="Glottolog"]')
        if node.get('ident') == 'und-x-glot-book1242':
            raise ValueError('Bookkeeping cannot be a display node')
        if code is None:
            continue
        record = records.get(code)
        if record is None:
            raise ValueError('Glottolog identifier requires snapshot review: '+code)
        if record['status'] != 'active' or 'book1242' in record['ancestors']:
            raise ValueError('retired or Bookkeeping Glottolog identifier: '+code)


def validate(data):
    standards()
    root = E.fromstring(data)
    from registry_geography import validate_geography
    validate_geography(root)
    change = root.find(T+'teiHeader/'+T+'revisionDesc/'+T+'change[@type="registryVersion"]')
    nodes = [n for n in root.iter() if n.tag in (T+'language', T+'languageGrp')]
    if change is None:
        raise ValueError('registry version missing')
    validate_registry(data)
    validate_glottolog(root)
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
        if n.tag==T+'ref' and n.get('type')=='classificationSource':
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
        if n.tag==T+'note' and n.get('type')=='editorialReview' and n.get('corresp'):
            target=ids.get(n.get('corresp').removeprefix('#'))
            if (target is None or target.tag!=T+'change' or target.get('type')!='editorialReview' or not (target.text or '').strip()
                    or (n.text or '').strip() or len(n)):
                raise ValueError('shared editorial review must reference one nonempty review change')
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
            if any(c.get('type') in ('ISO639-1','ISO639-2B','ISO639-2T') for c in claims):
                raise ValueError('ISO 639-1/2 equivalents are derived from the pinned ISO 639-3 table: '+code)
            if '-x-' not in code and code != (record.part1 or record.identifier):
                raise ValueError('canonical code disagrees with exact ISO identity: '+code)
        elif any(c.get('type') in ('ISO639-1','ISO639-2B','ISO639-2T') for c in claims):
            raise ValueError('ISO identifiers require their ISO 639-3 identity: '+code)
        profiles = n.findall(T+'note[@type="tagProfile"]')
        if len(profiles)>1 or any(c.get('subtype')!='direct' or c.get(X+'id') is not None or (c.text or '').strip() or len(c) for c in profiles):
            raise ValueError('invalid direct profile inventory: '+code)
        for name in n.findall(T+'name'):
            if name.get('type') in ('languageName','sourceLabel','sourceRecordLabel'):
                if ((name.get('type')=='sourceLabel') != bool(name.get(X+'id'))
                        or ids.get(name.get('source','').removeprefix('#')) is None):
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
            if source.get('ana') is not None:
                raise ValueError('source record profile is determined by its containing node: '+code)
            profile=n.find(T+'note[@type="tagProfile"][@subtype="direct"]')
            if profile is None:
                raise ValueError('source record requires a direct tag profile: '+code)
            cited=ids.get(source.get('source','').removeprefix('#'))
            if cited is None or cited.get('type')!='registrySource' or len(cited.findall(T+'idno[@type="dictionaryId"]'))!=1 or not (cited.findtext(T+'idno[@type="dictionaryId"]') or '').strip():
                raise ValueError('source record requires a dictionary-owned registry source: '+code)
            overrides=[c for c in n.findall(T+'name[@type="sourceRecordLabel"]') if c.get('corresp')=='#'+source.get(X+'id')]
            preferred={c.get(X+'lang'):''.join(c.itertext()) for c in n.findall(T+'name[@type="languageName"][@role="languageReferenceName"]')}
            if (len({c.get(X+'lang') for c in overrides})!=len(overrides)
                    or any(c.get('role')!='sourceRecordName' or c.get(X+'lang') not in ('sr','en','de') or c.get('source')!=source.get('source') or not (c.text or '').strip()
                           or c.text==preferred.get(c.get(X+'lang')) or c.get(X+'id') is not None for c in overrides)):
                raise ValueError('catalog translation overrides must be unique, nonempty and differ from node names: '+code)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/'registry.xml';path.write_bytes(data)
        checked(['jing',str(ROOT/'registry/schema/lex-0-f6d51f29.rng'),str(path)])
        checked(['xmllint','--noout','--schematron',str(SCHEMA_ROOT/'language-registry.sch'),str(path)])
    return root


def manifest(data, root):
    change = root.find(T+'teiHeader/'+T+'revisionDesc/'+T+'change[@type="registryVersion"]')
    displays = root.findall('.//'+T+'bibl[@type="classification"][@subtype="display"]')
    if len(displays)!=1:
        raise ValueError('exactly one display classification is required')
    result = E.Element(M+'registryManifest',dict(formatVersion='4',compatibilityPolicy=POLICY,registryVersion=change.get('n'),builtAt=change.get('when'),contentSha256=digest(data),displayClassificationId=displays[0].get(X+'id')))
    if root.find('.//'+T+'change[@type="geographyPolicy"][@n="reviewed-v1"]') is not None:
        result.set('geographyPolicy','reviewed-v1')
    lex = next(s for s in standards()['sources'] if s['id']=='lex-0')
    E.SubElement(result,M+'schema',dict(id='tei-lex-0',version=lex['version'],revision=lex['revision'],sha256=lex['files'][0]['sha256']))
    sources = E.SubElement(result,M+'sources')
    for b in root.findall('.//'+T+'bibl[@type="registrySource"]'):
        attrs = {X+'id':b.get(X+'id'),'title':b.findtext(T+'title'),'url':b.find(T+'ref[@type="sourceURL"]').get('target')}
        for key in ('upstreamId','version','revision'):
            value = b.findtext(T+'idno[@type="'+key+'"]')
            if value is not None:attrs[key]=value
        dictionary_id=b.findtext(T+'idno[@type="dictionaryId"]')
        if dictionary_id is not None:attrs['dictionaryId']=dictionary_id
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
    E.register_namespace('',M[1:-1]);E.indent(result,space='  ')
    output=b'<?xml version="1.0" encoding="UTF-8"?>\n'+E.tostring(result,encoding='utf-8')+b'\n'
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'manifest.xml';path.write_bytes(output)
        checked(['jing',str(SCHEMA_ROOT/'registry-manifest.rng'),str(path)])
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
