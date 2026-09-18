"""Reviewed geography vocabulary shared by the editor and offline validation.

Language identity, display nesting and geographic membership remain independent.
Bindings contain normalized source facts rather than implementation-specific XML
serialization hashes, so the XQuery resolver can compare the same values.
"""
import datetime
import re
import uuid
from xml.etree import ElementTree as E
from xml.sax.saxutils import quoteattr

T='{http://www.tei-c.org/ns/1.0}'
X='{http://www.w3.org/XML/1998/namespace}'


def normalized(value):
    return ' '.join((value or '').split())


def subject_binding(node, parent):
    parts=[node.get('ident',''),node.get('type',''),parent.get('ident','') if parent is not None else '']
    parts += [normalized(n.text) for n in node.findall(T+'ident')]
    parts += [normalized(''.join(n.itertext())) for n in node.findall(T+'note[@type="classificationNote"]')]
    return ' | '.join(parts)


def location_binding(location, place, sources):
    source=sources.get(location.get('source',''))
    if source is None: raise ValueError('A geographic location needs a bibliographic source.')
    return ' | '.join([location.get('type',''),location.get('source',''),
        normalized(place.findtext(T+'idno[@type="sourceNode"]')),normalized(location.findtext(T+'geo')),
        normalized(source.findtext(T+'idno[@type="version"]')),normalized(source.findtext(T+'idno[@type="revision"]')),
        ' '.join(n.get('target','') for n in source.findall(T+'ref[@type="sourceURL"]')),
        ' '.join(normalized(n.text) for n in source.findall(T+'ref[@type="sourceFile"]'))])


def indices(root):
    nodes={n.get('ident'):n for n in root.iter() if n.tag in (T+'language',T+'languageGrp')}
    parents={child:parent for parent in root.iter() for child in parent}
    sources={'#'+n.get(X+'id'):n for n in root.findall('.//'+T+'bibl[@type="registrySource"]')}
    locations={n.get(X+'id'):(node,n,place) for node in nodes.values() for place in node.findall(T+'settingDesc/'+T+'place') for n in place.findall(T+'location') if n.get(X+'id')}
    return nodes,parents,sources,locations


def decision_current(root,node,decision):
    nodes,parents,sources,locations=indices(root)
    if decision.findtext(T+'seg[@type="subjectBinding"]')!=subject_binding(node,parents.get(node)): return False
    for ref in decision.findall(T+'ref[@type="geographyNode"]'):
        target=nodes.get(ref.get('target','').removeprefix('#lang-'))
        if target is None or ref.get('n')!=subject_binding(target,parents.get(target)): return False
    for ref in decision.findall(T+'ref[@type="geographyLocation"]'):
        item=locations.get(ref.get('target','').removeprefix('#'))
        if item is None or ref.get('n')!=location_binding(item[1],item[2],sources): return False
    return True


def validate_geography(root):
    nodes,parents,sources,locations=indices(root)
    policies=root.findall('.//'+T+'change[@type="geographyPolicy"]')
    if policies and (len(policies)!=1 or policies[0].get('n')!='reviewed-v1'):
        raise ValueError('Exactly one supported geography policy is required.')
    if not policies and root.findall('.//'+T+'note[@type="geographyProfile"]'):
        raise ValueError('Reviewed profiles require the reviewed-v1 geography policy.')
    edges={identifier:[] for identifier in nodes}
    for identifier,node in nodes.items():
        profiles=node.findall(T+'note[@type="geographyProfile"]')
        decisions=node.findall(T+'note[@type="geographyDecision"]')
        if not profiles and not decisions:
            if node.get('type') in ('family','collective'):
                edges[identifier]=[child.get('ident') for child in node.iter() if child is not node and child.tag in (T+'language',T+'languageGrp')]
            continue
        if len(profiles)!=1 or profiles[0].get('subtype') not in ('individual','aggregate'):
            raise ValueError(identifier+': exactly one individual or aggregate geographic profile is required')
        mode=profiles[0].get('subtype')
        if node.get('type') in ('family','collective') and mode!='aggregate':
            raise ValueError(identifier+': families and collectives require aggregate geography')
        if mode=='aggregate' and node.findall(T+'settingDesc/'+T+'place/'+T+'location'):
            raise ValueError(identifier+': aggregate profiles cannot own or donate locations')
        fallback_count=0
        decision_keys=set()
        for decision in decisions:
            mechanism=decision.get('n'); status=decision.get('subtype')
            if status not in ('pending','approved','blocked') or mechanism not in ('own','broader','proxy','member'):
                raise ValueError(identifier+': invalid geographic mechanism or review status')
            if (mode=='aggregate') != (mechanism=='member'):
                raise ValueError(identifier+': geographic decision does not match profile mode')
            if decision.get('source') not in sources:
                raise ValueError(identifier+': geography review needs a registered source')
            for field in ('region','period','rationale','reviewedAt','subjectBinding'):
                if not normalized(decision.findtext(T+'seg[@type="'+field+'"]')):
                    raise ValueError(identifier+': geography review lacks '+field)
            datetime.date.fromisoformat(decision.findtext(T+'seg[@type="reviewedAt"]'))
            targets=decision.findall(T+'ref[@type="geographyNode"]')
            target=targets[0].get('target','').removeprefix('#lang-') if len(targets)==1 else None
            if mechanism!='own' and (target not in nodes or target==identifier):
                raise ValueError(identifier+': geographic relationship needs a different registered node')
            if mechanism!='own' and not targets[0].get('n'):
                raise ValueError(identifier+': geographic relationship lacks its target identity binding')
            if mechanism=='own' and targets:
                raise ValueError(identifier+': own geography cannot declare a donor')
            if mechanism in ('broader','proxy'):
                fallback_count+=1
                donor=nodes[target]
                profile=donor.find(T+'note[@type="geographyProfile"]')
                if donor.get('type') in ('family','collective') or profile is not None and profile.get('subtype')=='aggregate':
                    raise ValueError(identifier+': an aggregate cannot donate individual geography')
                if mechanism=='broader':
                    ancestors=[]; parent=parents.get(node)
                    while parent is not None:
                        ancestors.append(parent.get('ident')); parent=parents.get(parent)
                    if target not in ancestors:
                        raise ValueError(identifier+': broader-language donor must be a display ancestor; use an explicit proxy otherwise')
            refs=decision.findall(T+'ref[@type="geographyLocation"]')
            if mechanism!='member' and status=='approved' and not refs:
                raise ValueError(identifier+': approved individual geography needs specific locations')
            if mechanism=='member' and refs:
                raise ValueError(identifier+': aggregate membership references nodes, not copied points')
            for ref in refs:
                location_id=ref.get('target','').removeprefix('#')
                item=locations.get(location_id)
                owner=identifier if mechanism=='own' else target
                if item is None or item[0].get('ident')!=owner or not ref.get('n'):
                    raise ValueError(identifier+': geographic location reference has the wrong owner or lacks its source binding')
            key=(mechanism,target,tuple(r.get('target') for r in refs))
            if key in decision_keys: raise ValueError(identifier+': duplicate geographic decision')
            decision_keys.add(key)
            if target and status=='approved': edges[identifier].append(target)
        if fallback_count>1: raise ValueError(identifier+': only one explicit fallback disposition is allowed')
    visited,active=set(),set()
    def visit(identifier):
        if identifier in active: raise ValueError('Geographic relationship cycle at '+identifier)
        if identifier in visited: return
        active.add(identifier)
        for target in edges[identifier]: visit(target)
        active.remove(identifier); visited.add(identifier)
    for identifier in nodes: visit(identifier)


def edit_geography(data,identifier,values):
    from registry_editor import Document,EditorError,tag
    from registry_editor import node_record, update_attributes
    doc=Document(data); span=doc.get(identifier)
    if any(d.get('subtype')=='approved' and not decision_current(doc.root,span.element,d) for d in span.element.findall(T+'note[@type="geographyDecision"]')) and not values.get('reconfirmStale'):
        raise EditorError('Source facts changed since approval. Review and explicitly reconfirm the stale decisions.', 'geography', 'stale_approval')
    current=node_record(doc,span)['locations']
    requested=values.get('locations',current)
    # Give legacy points stable IDs while retaining their lexical source markup.
    for index,item in enumerate(current):
        if not item['id']:
            locid='location-'+identifier+'-'+uuid.uuid4().hex[:12]
            doc=Document(data);span=doc.get(identifier)
            old=[s for s in doc.spans if s.element.tag==T+'location' and s.parent.parent.parent is span][index]
            data=update_attributes(doc,old,{'xml:id':locid})
            item['id']=locid
            if index<len(requested) and requested[index].get('id') is None:
                requested[index]={**requested[index],'id':locid}
            doc=Document(data);span=doc.get(identifier)
    old_by_id={item['id']:item for item in current}
    seen=set()
    for item in requested:
        locid=item.get('id') or 'location-'+identifier+'-'+uuid.uuid4().hex[:12]
        if not re.fullmatch(r'location-[A-Za-z0-9._-]+',locid) or locid in seen:
            raise EditorError('Invalid or duplicate location identifier.', 'locations')
        seen.add(locid)
        old=old_by_id.get(locid)
        if old and item==old: continue
        doc=Document(data);span=doc.get(identifier)
        if old:
            location=next(s for s in doc.spans if s.element.get(X+'id')==locid)
            place=location.parent
            if item.get('sourceNode')!=old.get('sourceNode') and len(place.element.findall(T+'location'))>1:
                raise EditorError('This place shares source metadata across locations; edit its XML explicitly.', 'locations')
            data=update_attributes(doc,location,{'type':item.get('type','representative'),'source':item.get('source','')})
            doc=Document(data); location=next(s for s in doc.spans if s.element.get(X+'id')==locid)
            data=doc.replace_children(location,lambda e:e.tag==T+'geo',[tag('geo',normalized(item.get('coordinates','')))])
            doc=Document(data); location=next(s for s in doc.spans if s.element.get(X+'id')==locid)
            if item.get('sourceNode')!=old.get('sourceNode'):
                data=doc.replace_children(location.parent,lambda e:e.tag==T+'idno' and e.get('type')=='sourceNode',[tag('idno',item.get('sourceNode',''),type='sourceNode')])
        else:
            if item.get('id'): raise EditorError('A location cannot be reassigned from another concept.', 'locations')
            place='<place><location xml:id='+quoteattr(locid)+' type='+quoteattr(item.get('type','representative'))+' source='+quoteattr(item.get('source',''))+'>'+tag('geo',normalized(item.get('coordinates','')))+'</location>'+tag('idno',item.get('sourceNode',''),type='sourceNode')+'</place>'
            setting=next((s for s in span.children if s.element.tag==T+'settingDesc'),None)
            data=doc.replace_children(setting,lambda e:False,[place]) if setting else doc.replace_children(span,lambda e:False,['<settingDesc>'+place+'</settingDesc>'])
    for locid in old_by_id.keys()-seen:
        doc=Document(data);location=next(s for s in doc.spans if s.element.get(X+'id')==locid);place=location.parent
        if len(place.element.findall(T+'location'))>1:
            data=doc.apply([(location.start,location.end,b'')]);continue
        if b'<!--' in doc.raw(place) or any(c.element.tag not in (T+'location',T+'idno') for c in place.children):
            raise EditorError('This location has additional source markup; review its deletion in XML.', 'locations')
        setting=place.parent
        if len(setting.children)==1 and b'<!--' not in doc.raw(setting):
            data=doc.apply([(setting.start,setting.end,b'')])
        else: data=doc.apply([(place.start,place.end,b'')])
    # Donor points receive IDs without changing their coordinates or metadata.
    for owner in {d.get('nodeId') for d in values.get('decisions',[]) if d.get('nodeId')}:
        while True:
            doc=Document(data);owner_span=doc.get(owner)
            location=next((s for s in doc.spans if s.element.tag==T+'location' and s.parent.parent.parent is owner_span and not s.element.get(X+'id')),None)
            if not location: break
            data=update_attributes(doc,location,{'xml:id':'location-'+owner+'-'+uuid.uuid4().hex[:12]})
    doc=Document(data); span=doc.get(identifier)
    nodes,parents,sources,locations=indices(doc.root)
    mode=values.get('mode','individual')
    fragments=[tag('note','',type='geographyProfile',subtype=mode)]
    for item in values.get('decisions',[]):
        mechanism=item.get('mechanism'); owner=identifier if mechanism=='own' else item.get('nodeId')
        children=[]
        if item.get('nodeId'):
            target=nodes[item['nodeId']]
            children.append(tag('ref','',type='geographyNode',target='#lang-'+item['nodeId'],n=subject_binding(target,parents.get(target))))
        locids=item.get('locations',[])
        if item.get('allLocations') and mechanism!='member':
            locids=[key for key,(node,_,_) in locations.items() if node.get('ident')==owner]
        for locid in locids:
            if locid not in locations: raise EditorError('The selected location is missing; reload its source record.', 'geography')
            _,location,place=locations[locid]
            children.append(tag('ref','',type='geographyLocation',target='#'+locid,n=location_binding(location,place,sources)))
        for field in ('region','period','rationale','reviewedAt'):
            children.append(tag('seg',item.get(field,''),type=field))
        children.append(tag('seg',subject_binding(span.element,parents.get(span.element)),type='subjectBinding'))
        fragments.append('<note type="geographyDecision" subtype='+quoteattr(item.get('status','pending'))+' n='+quoteattr(mechanism or '')+' source='+quoteattr(item.get('source','#src-raskovnik-review'))+'>'+''.join(children)+'</note>')
    data=doc.replace_children(span,lambda e:e.tag==T+'note' and e.get('type') in ('geographyProfile','geographyDecision'),fragments)
    # The explicit policy makes a draft opt in to the reviewed resolver as a unit.
    doc=Document(data)
    if not doc.root.findall('.//'+T+'change[@type="geographyPolicy"]'):
        rev=next(s for s in doc.spans if s.element.tag==T+'revisionDesc')
        data=doc.replace_children(rev,lambda e:False,[tag('change','Reviewed geographic relationships; legacy own points retain unreviewed status and automatic ancestor fallbacks are suppressed.',type='geographyPolicy',n='reviewed-v1',when=datetime.date.today().isoformat())])
    return data
