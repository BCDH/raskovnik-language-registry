#!/usr/bin/env python3
"""Source-preserving registry editing. JSON in/out; XML remains the authority.

The caller supplies an isolated draft path, never the published installation.
All writes are locked, revision checked, validated, and atomically replaced.
"""
import argparse
import csv
import datetime
import difflib
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import subprocess
import tempfile
import uuid
from xml.etree import ElementTree as ET
from xml.parsers import expat
from xml.sax.saxutils import escape, quoteattr

from registry import validate

T = '{http://www.tei-c.org/ns/1.0}'
X = '{http://www.w3.org/XML/1998/namespace}'
LOCALES = ('sr', 'en', 'de')
KINDS = ('family', 'language', 'variety', 'historical-stage', 'reconstructed-language', 'collective')
SOURCE = '#src-raskovnik-review'


class EditorError(ValueError):
    def __init__(self, message, field='registry', code='validation'):
        super().__init__(message)
        self.field, self.code = field, code


def revision(data):
    return hashlib.sha256(data).hexdigest()


def text(element):
    return ''.join(element.itertext()) if element is not None else ''


def tag(name, value='', **attributes):
    attrs = ''.join(' ' + k.replace('_', ':') + '=' + quoteattr(str(v)) for k, v in attributes.items() if v is not None)
    return '<' + name + attrs + '>' + escape(str(value)) + '</' + name + '>'


class Span:
    def __init__(self, start, open_end, parent):
        self.start, self.open_end, self.parent = start, open_end, parent
        self.children = []
        self.element = None


class Document:
    """Pair parsed elements with lexical byte ranges, including unknown markup."""
    def __init__(self, data):
        if b'<!DOCTYPE' in data or b'<!ENTITY' in data:
            raise EditorError('Document type declarations and entities are not allowed.')
        self.data, self.spans, stack = data, [], []
        parser = expat.ParserCreate(namespace_separator='}')

        def start(_name, _attributes):
            offset = parser.CurrentByteIndex
            # A quoted attribute can contain >; scan until the unquoted delimiter.
            quote, end = None, offset
            while end < len(data):
                c = data[end:end + 1]
                if quote:
                    if c == quote:
                        quote = None
                elif c in (b'"', b"'"):
                    quote = c
                elif c == b'>':
                    break
                end += 1
            span = Span(offset, end + 1, stack[-1] if stack else None)
            if stack:
                stack[-1].children.append(span)
            self.spans.append(span)
            stack.append(span)

        def end(_name):
            span = stack.pop()
            empty = data[span.start:span.open_end].rstrip().endswith(b'/>')
            span.close_start = span.open_end if empty else parser.CurrentByteIndex
            span.end = span.open_end if empty else data.index(b'>', span.close_start) + 1

        parser.StartElementHandler, parser.EndElementHandler = start, end
        parser.Parse(data, True)
        self.root = ET.fromstring(data)
        for span, element in zip(self.spans, self.root.iter()):
            span.element = element
        self.nodes = {s.element.get('ident'): s for s in self.spans if s.element.tag in (T + 'language', T + 'languageGrp')}

    def get(self, identifier):
        if identifier not in self.nodes:
            raise EditorError('Unknown registry node: ' + str(identifier), 'id', 'not_found')
        return self.nodes[identifier]

    def indent(self, span):
        return self.data[self.data.rfind(b'\n', 0, span.start) + 1:span.start].decode()

    def raw(self, span):
        return self.data[span.start:span.end]

    def apply(self, patches):
        data, last = self.data, len(self.data) + 1
        for start, end, replacement in sorted(patches, reverse=True):
            if end > last:
                raise EditorError('Overlapping XML edits were refused.')
            data = data[:start] + replacement + data[end:]
            last = start
        return data

    def replace_children(self, span, predicate, fragments):
        """Replace only owned children, retaining every other byte."""
        old = [s for s in span.children if predicate(s.element)]
        patches = []
        remaining = list(fragments)
        for s in old:
            if remaining:
                fragment = remaining.pop(0).encode()
                if fragment != self.raw(s):
                    patches.append((s.start, s.end, fragment))
            else:
                start = s.start
                line_start = self.data.rfind(b'\n', 0, start) + 1
                if not self.data[line_start:start].strip():
                    start = line_start
                end = s.end + (1 if self.data[s.end:s.end + 1] == b'\n' else 0)
                patches.append((start, end, b''))
        if remaining:
            # Metadata precedes nested languages in the display tree.
            child = next((c for c in span.children if c.element.tag in (T+'language', T+'languageGrp')), None)
            offset = child.start if child else span.close_start
            indent = self.indent(span) + '  '
            prefix = '' if child else '  '
            insertion = prefix + ('\n' + indent).join(remaining) + '\n' + (indent if child else self.indent(span))
            patches.append((offset, offset, insertion.encode()))
        return self.apply(patches)


def node_record(document, span):
    node = span.element
    names = node.findall(T+'name')
    notes = node.findall(T+'note')
    parent = span.parent
    while parent and parent.element.tag not in (T+'language', T+'languageGrp'):
        parent = parent.parent
    locations = []
    for place in node.findall(T+'settingDesc/'+T+'place'):
        for location in place.findall(T+'location'):
            locations.append({'id': location.get(X+'id'), 'type': location.get('type'),
                'source': location.get('source'), 'sourceNode': place.findtext(T+'idno[@type="sourceNode"]', ''),
                'coordinates': location.findtext(T+'geo', '')})
    return {
        'id': node.get('ident'), 'kind': node.get('type'), 'parentId': parent.element.get('ident') if parent else None,
        'children': [c.element.get('ident') for c in span.children if c.element.tag in (T+'language', T+'languageGrp')],
        'labels': {n.get(X+'lang'): text(n) for n in names if n.get('type')=='languageName' and n.get('role')=='languageReferenceName'},
        'aliases': {lang: [text(n) for n in names if n.get('role')=='languageAlias' and n.get(X+'lang')==lang] for lang in LOCALES},
        'identifiers': {n.get('type'): text(n) for n in node.findall(T+'ident')},
        'selectable': any(n.get('type')=='selectionStatus' and n.get('subtype')=='selectable' for n in notes),
        'classificationStatus': next((n.get('subtype') for n in notes if n.get('type')=='classificationStatus'), 'tentative'),
        'classificationNotes': {n.get(X+'lang'): text(n) for n in notes if n.get('type')=='classificationNote'},
        'exclusions': [{'type': n.get('subtype'), 'value': text(n), 'source': n.get('source')} for n in notes if n.get('type')=='excludedExactIdentifier'],
        'alternateClassifications': [{'classification': n.get('ana'), 'status': n.get('subtype'), 'nodes': [r.get('target', '').removeprefix('#lang-') for r in n.findall(T+'ref')]} for n in notes if n.get('type')=='alternateClassification'],
        'sourceLabels': [{'id': n.get(X+'id'), 'label': text(n), 'source': n.get('source'), 'catalog': n.get('ana'), 'kind': n.get('role'), 'abbreviation': n.get('subtype'),
            'labels': {s.get(X+'lang'): text(s) for s in names if s.get('type')=='sourceRecordLabel' and s.get('corresp')=='#'+n.get(X+'id','')}} for n in names if n.get('type')=='sourceLabel'],
        'directProfile': bool(node.findall(T+'note[@type="tagProfile"]')),
        'locations': locations,
        'geography': geography_record(node,document.root),
        'history': [text(n) for n in notes if n.get('type')=='editorialReview'] + [n.get('when','')+' · '+n.get('who','')+' · '+text(n) for n in document.root.findall('.//'+T+'change[@type="editorial"]') if n.get('n')==node.get('ident')],
        'supportingNotes': [{'type':n.get('type'), 'text':text(n), 'source':n.get('source')} for n in notes if n.get('type') not in ('selectionStatus','classificationStatus','classificationNote','tagProfile','geographyProfile','geographyDecision')],
    }


def geography_record(node,root):
    from registry_geography import decision_current
    profile = node.find(T+'note[@type="geographyProfile"]')
    return {'mode': profile.get('subtype') if profile is not None else ('aggregate' if node.get('type') in ('family','collective') else 'individual'),
        'explicit': profile is not None,
        'decisions': [{'status': n.get('subtype'), 'stale':not decision_current(root,node,n), 'mechanism': n.get('n'), 'source': n.get('source'),
            'nodeId': n.find(T+'ref[@type="geographyNode"]').get('target','').removeprefix('#lang-') if n.find(T+'ref[@type="geographyNode"]') is not None else None,
            'locations': [r.get('target','').removeprefix('#') for r in n.findall(T+'ref[@type="geographyLocation"]')],
            **{key: n.findtext(T+'seg[@type="'+key+'"]','') for key in ('region','period','rationale','reviewedAt')}}
            for n in node.findall(T+'note[@type="geographyDecision"]')]}


def inventory(data):
    doc = Document(data)
    worklists=Path(__file__).resolve().parents[1]/'registry/geography-worklists.json'
    return {'revision': revision(data), 'worklists':json.loads(worklists.read_text())['batches'] if worklists.exists() else {}, 'nodes': [node_record(doc, s) for s in doc.nodes.values()],
        'sources': [{'id': '#'+s.element.get(X+'id'), 'title': s.element.findtext(T+'title',''),
            'url': s.element.find(T+'ref[@type="sourceURL"]').get('target','') if s.element.find(T+'ref[@type="sourceURL"]') is not None else '',
            'version': s.element.findtext(T+'idno[@type="version"]',''), 'revision': s.element.findtext(T+'idno[@type="revision"]',''),
            'attribution': s.element.findtext(T+'note[@type="attribution"]','')}
            for s in doc.spans if s.element.tag==T+'bibl' and s.element.get('type')=='registrySource'],
        'classifications': [{'id':'#'+s.element.get(X+'id'), 'title':text(s.element.find(T+'title'))} for s in doc.spans if s.element.tag==T+'bibl' and s.element.get('type')=='classification']}


def update_attributes(document, span, changes):
    opening = document.data[span.start:span.open_end].decode()
    for key, value in changes.items():
        pattern = r'\s+' + re.escape(key) + r'=(?:"[^"]*"|\x27[^\x27]*\x27)'
        replacement = '' if value is None else ' '+key+'='+quoteattr(str(value))
        if re.search(pattern, opening):
            opening = re.sub(pattern, lambda _: replacement, opening, count=1)
        else:
            opening = opening[:-1]+replacement+'>'
    return document.apply([(span.start, span.open_end, opening.encode())])


def wrappers(data):
    doc = Document(data)
    patches = []
    for span in doc.nodes.values():
        group = any(c.element.tag in (T+'language', T+'languageGrp') for c in span.children)
        desired = 'languageGrp' if group else 'language'
        if span.element.tag == T+desired:
            continue
        opening = doc.data[span.start:span.open_end].decode()
        opening = re.sub(r'^<language(?:Grp)?', '<'+desired, opening)
        opening = re.sub(r'\s+role="[^"]*"', '', opening)
        if not group:
            opening = opening[:-1]+' role="objectLanguage">'
        patches.extend([(span.start, span.open_end, opening.encode()), (span.close_start,span.end,('</'+desired+'>').encode())])
    return doc.apply(patches)


def update_node(data, identifier, values):
    doc = Document(data)
    span = doc.get(identifier)
    current = node_record(doc, span)
    if values.get('id', identifier) != identifier:
        raise EditorError('Canonical identifiers cannot be renamed in ordinary edits.', 'id')
    if 'kind' in values and values['kind'] != current['kind']:
        if values['kind'] not in KINDS:
            raise EditorError('Unsupported concept kind.', 'kind')
        data = update_attributes(doc, span, {'type':values['kind']})
    for field, role in (('labels', 'languageReferenceName'), ('aliases','languageAlias')):
        if field not in values or values[field] == current[field]:
            continue
        doc = Document(data); span = doc.get(identifier)
        fragments = []
        for lang in LOCALES:
            existing=[s for s in span.children if s.element.tag==T+'name' and s.element.get('type')=='languageName' and s.element.get('role')==role and s.element.get(X+'lang')==lang]
            entries = [values[field].get(lang,'')] if field=='labels' else values[field].get(lang,[])
            if not isinstance(entries, list):
                raise EditorError('Aliases must be a list.', 'aliases')
            for i, value in enumerate(entries):
                if value.strip():
                    match=next((s for s in existing if text(s.element)==value.strip()),None)
                    if match:
                        fragments.append(doc.raw(match).decode())
                    else:
                        fragments.append(tag('name',value.strip(),type='languageName',role=role,source=SOURCE,
                            xml_id='name-'+identifier+'-'+lang+('-preferred' if field=='labels' else '-alias-'+uuid.uuid4().hex[:12]),xml_lang=lang))
        data = doc.replace_children(span,lambda e:e.tag==T+'name' and e.get('type')=='languageName' and e.get('role')==role and e.get(X+'lang') in LOCALES,fragments)
    if 'identifiers' in values and values['identifiers'] != current['identifiers']:
        ids = dict(values['identifiers'])
        if ids.get('BCP47',identifier) != identifier:
            raise EditorError('The canonical BCP47 identifier is immutable.', 'identifiers')
        ids['BCP47'] = identifier
        allowed = {'BCP47','ISO639-1','ISO639-2B','ISO639-2T','ISO639-3','Glottolog','Wikidata'}
        if set(ids)-allowed:
            raise EditorError('Unsupported exact identifier type.', 'identifiers')
        for exclusion in current['exclusions']:
            if ids.get(exclusion['type']) == exclusion['value']:
                raise EditorError('This identifier has a reviewed exclusion.', 'identifiers')
        fragments = [tag('ident',value,type=key,xml_id='lang-'+identifier if key=='BCP47' else None) for key,value in ids.items() if value]
        doc=Document(data); data=doc.replace_children(doc.get(identifier),lambda e:e.tag==T+'ident',fragments)
    for field, note_type in (('selectable','selectionStatus'),('classificationStatus','classificationStatus')):
        if field not in values or values[field] == current[field]:
            continue
        value = ('selectable' if values[field] else 'nonselectable') if field=='selectable' else values[field]
        doc=Document(data); data=doc.replace_children(doc.get(identifier),lambda e:e.tag==T+'note' and e.get('type')==note_type,
            [tag('note',value,type=note_type,subtype=value,source=SOURCE)])
    if 'classificationNotes' in values and values['classificationNotes'] != current['classificationNotes']:
        doc=Document(data); data=doc.replace_children(doc.get(identifier),lambda e:e.tag==T+'note' and e.get('type')=='classificationNote',
            [tag('note',value,type='classificationNote',source=SOURCE,xml_lang=lang) for lang,value in values['classificationNotes'].items() if lang in LOCALES and value.strip()])
    if 'alternateClassifications' in values and values['alternateClassifications'] != current['alternateClassifications']:
        fragments=[]
        for path in values['alternateClassifications']:
            fragments.append('<note type="alternateClassification" source='+quoteattr(SOURCE)+' ana='+quoteattr(path['classification'])+' subtype='+quoteattr(path['status'])+'>'+''.join(tag('ref',n,type='alternatePathNode',target='#lang-'+n) for n in path['nodes'])+'</note>')
        doc=Document(data); data=doc.replace_children(doc.get(identifier),lambda e:e.tag==T+'note' and e.get('type')=='alternateClassification',fragments)
    if 'sourceLabels' in values and values['sourceLabels'] != current['sourceLabels']:
        # Existing stable source IDs, catalogue binding and source provenance stay fixed.
        old={s['id']:s for s in current['sourceLabels']}
        for record in values['sourceLabels']:
            original=old.get(record['id'])
            if not original:
                raise EditorError('A source label must refer to an existing source record.', 'sourceLabels')
            doc=Document(data); span=doc.get(identifier)
            targets=[s for s in span.children if s.element.tag==T+'name' and s.element.get(X+'id')==record['id']]
            target=targets[0]
            if original['label']!=record['label']:
                data=doc.apply([(target.open_end,target.close_start,escape(record['label']).encode())])
            for lang in LOCALES:
                if record['labels'].get(lang)==original['labels'].get(lang): continue
                doc=Document(data); span=doc.get(identifier)
                target=next(s for s in span.children if s.element.tag==T+'name' and s.element.get('type')=='sourceRecordLabel' and s.element.get('corresp')=='#'+record['id'] and s.element.get(X+'lang')==lang)
                data=doc.apply([(target.open_end,target.close_start,escape(record['labels'].get(lang,'')).encode())])
    if 'parentId' in values and values['parentId'] != current['parentId']:
        doc=Document(data); span=doc.get(identifier); parent=doc.get(values['parentId']) if values['parentId'] else next(s for s in doc.spans if s.element.tag==T+'langUsage')
        p=parent
        while p:
            if p is span: raise EditorError('A node cannot be moved beneath itself or a descendant.', 'parentId')
            p=p.parent
        raw=doc.raw(span).decode()
        old_indent=doc.indent(span); new_indent=doc.indent(parent)+'  '
        raw=raw.replace('\n'+old_indent,'\n'+new_indent)
        data=doc.apply([(span.start,span.end,b''),(parent.close_start,parent.close_start,('  '+raw+'\n'+doc.indent(parent)).encode())])
        data=wrappers(data)
    return data


def create_node(data, values):
    identifier=values.get('id','')
    if not re.fullmatch(r'[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*', identifier):
        raise EditorError('Supply a canonical language tag.', 'id')
    doc=Document(data)
    if identifier in doc.nodes: raise EditorError('That identifier already exists.', 'id')
    parent=doc.get(values['parentId']) if values.get('parentId') else next(s for s in doc.spans if s.element.tag==T+'langUsage')
    kind=values.get('kind','language')
    if kind not in KINDS: raise EditorError('Unsupported concept kind.', 'kind')
    labels=values.get('labels',{})
    children=[tag('ident',identifier,type='BCP47',xml_id='lang-'+identifier)]
    children += [tag('name',labels.get(lang,''),type='languageName',role='languageReferenceName',source=SOURCE,xml_id='name-'+identifier+'-'+lang+'-preferred',xml_lang=lang) for lang in LOCALES if labels.get(lang)]
    children += [tag('note','selectable' if values.get('selectable',True) else 'nonselectable',type='selectionStatus',subtype='selectable' if values.get('selectable',True) else 'nonselectable',source=SOURCE),tag('note','tentative',type='classificationStatus',subtype='tentative',source=SOURCE)]
    if values.get('directProfile',False):
        children.append(tag('note',identifier,type='tagProfile',subtype='direct',source=SOURCE,xml_id='profile-'+identifier))
    indent=doc.indent(parent)+'  '
    fragment='<language ident='+quoteattr(identifier)+' type='+quoteattr(kind)+' role="objectLanguage">\n'+''.join(indent+'  '+c+'\n' for c in children)+indent+'</language>'
    data=doc.apply([(parent.close_start,parent.close_start,('  '+fragment+'\n'+doc.indent(parent)).encode())])
    data=wrappers(data)
    return update_node(data,identifier,{k:v for k,v in values.items() if k not in ('parentId','directProfile')})


def delete_node(data, identifier):
    doc=Document(data); span=doc.get(identifier)
    record=node_record(doc,span)
    if record['children']:
        raise EditorError('Move or remove child concepts before deleting this node.', 'id')
    # Removal of covered tags is a separate, backend-verified migration. Fail closed.
    if record['directProfile'] or record['sourceLabels']:
        raise EditorError('This node has a language-tag profile or source mappings. A coverage-verified migration is required before deletion.', 'id', 'coverage_required')
    ids={e.get(X+'id') for e in span.element.iter() if e.get(X+'id')}
    subtree=set(span.element.iter())
    for e in doc.root.iter():
        if e in subtree: continue
        for attr in ('source','ana','corresp','target','resp','who'):
            if any(p.removeprefix('#') in ids for p in e.get(attr,'').split()):
                raise EditorError('Another registry record still references this concept.', 'id')
    return wrappers(doc.apply([(span.start,span.end,b'')]))


def add_revision(data, actor, rationale, identifier=None):
    if not rationale.strip():
        raise EditorError('Explain the editorial change.', 'rationale')
    doc=Document(data); span=next(s for s in doc.spans if s.element.tag==T+'revisionDesc')
    today=datetime.date.today().isoformat()
    fragment=tag('change',rationale.strip(),type='editorial',when=today,who=actor,n=identifier)
    return doc.replace_children(span,lambda e:False,[fragment])


def edit(data, request):
    if request.get('expectedRevision') != revision(data):
        raise EditorError('The draft changed after this form was opened. Reload and review the newer version.', 'revision', 'conflict')
    operation=request.get('operation')
    if operation=='update': candidate=update_node(data,request['id'],request['values'])
    elif operation=='create': candidate=create_node(data,request['values'])
    elif operation=='delete': candidate=delete_node(data,request['id'])
    elif operation=='geography':
        from registry_geography import edit_geography
        candidate=edit_geography(data,request['id'],request['values'])
    elif operation=='source': candidate=edit_source(data,request['values'])
    elif operation=='exclusions':
        doc=Document(data);span=doc.get(request['id']);fragments=[]
        for item in request['values']['exclusions']:
            if item.get('type') not in ('ISO639-1','ISO639-2B','ISO639-2T','ISO639-3','Glottolog','Wikidata') or not item.get('value','').strip():
                raise EditorError('An exclusion needs an identifier type and value.', 'exclusions')
            match=next((s for s in span.children if s.element.tag==T+'note' and s.element.get('type')=='excludedExactIdentifier' and s.element.get('subtype')==item['type'] and text(s.element)==item['value'] and s.element.get('source')==item['source']),None)
            fragments.append(doc.raw(match).decode() if match else tag('note',item['value'].strip(),type='excludedExactIdentifier',subtype=item['type'],source=item['source']))
        candidate=doc.replace_children(span,lambda e:e.tag==T+'note' and e.get('type')=='excludedExactIdentifier',fragments)
    else: raise EditorError('Unsupported editorial operation.', 'operation')
    if candidate != data:
        candidate=add_revision(candidate,request.get('actor','registry-editor'),request.get('rationale',''),request.get('id') or request.get('values',{}).get('id'))
        validate(candidate)
    return candidate


def edit_source(data, values):
    identifier=values.get('id','').removeprefix('#')
    if not re.fullmatch(r'src-[a-zA-Z0-9._-]+',identifier): raise EditorError('A source ID must start with src-.', 'source')
    doc=Document(data)
    old=next((s for s in doc.spans if s.element.get(X+'id')==identifier),None)
    # Pinned upstream source records can only change through a standards review.
    if old and old.element.findall(T+'ref[@type="sourceFile"]'):
        raise EditorError('Pinned source records require the standards-review workflow.', 'source')
    url=values.get('url','')
    if not url.startswith('https://'): raise EditorError('A source needs an HTTPS reference URL.', 'source.url')
    fragments=[tag('title',values.get('title','')),tag('ref',url,type='sourceURL',target=url),tag('note',values.get('attribution',''),type='attribution')]
    if not old: fragments.append(tag('idno',identifier.removeprefix('src-'),type='upstreamId'))
    for field in ('version','revision'):
        if values.get(field): fragments.append(tag('idno',values[field],type=field))
    if old:
        return doc.replace_children(old,lambda e:e.tag==T+'title' or e.tag==T+'ref' and e.get('type')=='sourceURL' or e.tag==T+'note' and e.get('type')=='attribution' or e.tag==T+'idno' and e.get('type') in ('version','revision'),fragments)
    parent=next(s for s in doc.spans if s.element.tag==T+'listBibl' and s.element.get('type')=='registrySources')
    return doc.replace_children(parent,lambda e:False,['<bibl xml:id='+quoteattr(identifier)+' type="registrySource">'+''.join(fragments)+'</bibl>'])


def atomic_write(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as output:
        temp=Path(output.name)
        try:
            output.write(data); output.flush(); os.fsync(output.fileno())
            os.chmod(temp,path.stat().st_mode & 0o777)
            os.replace(temp,path)
        finally:
            temp.unlink(missing_ok=True)


def glottolog_record(root, code):
    if not re.fullmatch(r'[a-z0-9]{8}',code or ''): raise EditorError('Supply a Glottocode.', 'Glottolog')
    review=json.loads((root/'registry/glottolog-review.json').read_text())
    validate((root/'registry/registry.xml').read_bytes())
    match=re.fullmatch(r'https://github.com/BCDH/raskovnik-language-registry/blob/([a-f0-9]+)/(.+)',review['source'])
    if not match: raise EditorError('The Glottolog source is not a pinned registry snapshot.', 'Glottolog')
    result=subprocess.run(['git','show',match[1]+':'+match[2]],cwd=root,capture_output=True)
    if result.returncode or revision(result.stdout)!=review['sha256']:
        raise EditorError('The provenance-pinned Glottolog snapshot is unavailable or has changed.', 'Glottolog')
    rows={row['id']:row for row in csv.DictReader(io.StringIO(result.stdout.decode()))}
    if code not in rows: raise EditorError('The Glottocode is absent from the pinned snapshot.', 'Glottolog')
    row=rows[code]; ancestors=[]; parent=row['parent_id']
    while parent:
        if parent in ancestors or parent not in rows: raise EditorError('Invalid snapshot ancestry.', 'Glottolog')
        ancestors.append(parent); parent=rows[parent]['parent_id']
    if row['bookkeeping']!='False' or 'book1242' in ancestors:
        raise EditorError('Retired and Bookkeeping records cannot be approved as exact identities.', 'Glottolog')
    return {'code':code,'record':{'name':row['name'],'status':'active','ancestors':ancestors},
        'iso639_3':row['iso639P3code'],'level':row['level'],'coordinates':row['latitude']+' '+row['longitude'],
        'source':review['source'],'sourceSha256':review['sha256']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('inventory','edit','validate','diff','inspect-glottolog','review-glottolog'))
    parser.add_argument('--registry',type=Path,required=True)
    parser.add_argument('--base',type=Path)
    args=parser.parse_args()
    # Validate against the draft's pinned standards and review tables.
    import registry as registry_module
    registry_module.ROOT=args.registry.resolve().parents[1]
    try:
        if args.command in ('inspect-glottolog','review-glottolog'):
            request=json.load(sys.stdin)
            result=glottolog_record(registry_module.ROOT,request.get('code'))
            if args.command=='review-glottolog':
                if not request.get('rationale','').strip(): raise EditorError('Record the source-review rationale.', 'rationale')
                table=registry_module.ROOT/'registry/glottolog-review.json'
                with args.registry.with_suffix('.editor.lock').open('a') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX)
                    if request.get('expectedRevision')!=revision(args.registry.read_bytes()) or request.get('expectedReviewRevision')!=revision(table.read_bytes()):
                        raise EditorError('The registry or source-review table changed.', 'revision', 'conflict')
                    value=json.loads(table.read_text())
                    if request['code'] not in value['records']:
                        value['records'][request['code']]={**result['record'],'reviewedAt':datetime.date.today().isoformat(),'reviewer':request.get('actor','registry-editor'),'rationale':request['rationale'].strip()}
                        atomic_write(table,(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())
        elif args.command=='edit':
            request=json.load(sys.stdin)
            with args.registry.with_suffix('.editor.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                data=args.registry.read_bytes(); candidate=edit(data,request)
                if candidate!=data: atomic_write(args.registry,candidate)
            result={'revision':revision(candidate),'changed':candidate!=data}
        elif args.command=='inventory': result=inventory(args.registry.read_bytes())
        elif args.command=='validate':
            data=args.registry.read_bytes(); root=validate(data)
            registry_module.manifest(data,root)
            result={'valid':True,'revision':revision(data)}
        else:
            if not args.base: raise EditorError('A base snapshot is required.')
            before=inventory(args.base.read_bytes());after=inventory(args.registry.read_bytes())
            old={n['id']:n for n in before['nodes']};new={n['id']:n for n in after['nodes']};summary=[]
            for identifier in old.keys()|new.keys():
                if identifier not in old:summary.append(identifier+': created')
                elif identifier not in new:summary.append(identifier+': deleted')
                else:
                    fields=[k for k in new[identifier] if k not in ('history','supportingNotes') and old[identifier].get(k)!=new[identifier][k]]
                    if fields:summary.append(identifier+': '+', '.join(fields))
            if before['sources']!=after['sources']:summary.append('Bibliographic sources changed')
            result={'summary':sorted(summary),'diff':''.join(difflib.unified_diff(args.base.read_text().splitlines(True),args.registry.read_text().splitlines(True),fromfile='base/registry.xml',tofile='draft/registry.xml'))}
        print(json.dumps(result,ensure_ascii=False))
        return 0
    except (ValueError,RuntimeError,OSError,ET.ParseError,expat.ExpatError,KeyError,TypeError) as error:
        print(json.dumps({'errors':[{'field':getattr(error,'field','registry'),'code':getattr(error,'code','validation'),'message':str(error)}]},ensure_ascii=False))
        return 2


if __name__=='__main__':
    sys.exit(main())
