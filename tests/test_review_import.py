import copy
import importlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
IMPORT=importlib.import_module('import-review')
ASSEMBLE=importlib.import_module('assemble-registry-plan')
GEN=importlib.import_module('generate-candidates')
from registry_sources import parse_glottolog,parse_wikidata_evidence
from registry_build import RegistryBuildError,validate_plan,PLAN_SCHEMA

class ReviewImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data,cls.records=IMPORT.reconcile()
        cls.by_key={r['key']:r for r in cls.records}

    def test_idempotent_and_all_user_decisions_preserved(self):
        self.assertEqual(self.data,(ROOT/'registry/raskovnik-overrides.xml').read_bytes())
        tree=ET.fromstring(self.data)
        saved=json.loads((IMPORT.SESSION/'labels-completed.json').read_text())['review']
        self.assertEqual(25,len(saved))
        for key,record in saved.items():
            self.assertEqual(record,self.by_key[key]['savedDecision'])
            self.assertEqual(record['values'],self.by_key[key]['values'])
            self.assertEqual('applied',self.by_key[key]['status'])
            self.assertEqual('ttasovac',self.by_key[key]['reviewer'])
            node=tree.find(IMPORT.NS+"node[@ident='"+record['values']['canonicalCode']+"']")
            self.assertEqual('true',node.get('selectable'))
            names={n.get(IMPORT.XML+'lang'):n.text for n in node.findall(IMPORT.NS+'name')}
            for language,suffix in [('sr','Sr'),('en','En'),('de','De')]:
                self.assertEqual(record['values']['label'+suffix],names[language])

    def test_packaging_conflicts_are_resolved_with_explicit_history(self):
        self.assertFalse([r for r in self.records if r['status']=='pending'])
        self.assertEqual('Codex',self.by_key['tag-profile:cs-x-old']['reviewer'])
        self.assertEqual('ttasovac',self.by_key['tag-profile:hr-x-kajkav']['reviewer'])
        self.assertEqual('superseded',self.by_key['tag-profile:cel-x-gaulish']['status'])
        self.assertEqual('applied',self.by_key['tag-profile:xtg']['status'])

    def test_related_identifiers_are_not_exact_and_blank_qid_stays_blank(self):
        tree=ET.fromstring(self.data)
        node=tree.find(IMPORT.NS+"node[@ident='zle-x-polesian']")
        self.assertEqual('broader',node.get('alignment'))
        self.assertEqual('east1426',node.get('glottocode'))
        self.assertIn('west2977',' '.join(n.text or '' for n in node.findall(IMPORT.NS+'note')))
        self.assertEqual('',tree.find(IMPORT.NS+"node[@ident='gmh']").get('wikidata'))
        for key in ('book1242','nort3208','shif1234'):
            n=tree.find(IMPORT.NS+"node[@ident='und-x-glot-"+key+"']")
            self.assertEqual('false',n.get('selectable'))
            names={n.get(IMPORT.XML+'lang'):n.text for n in n.findall(IMPORT.NS+'name')}
            self.assertTrue(names['en']);self.assertFalse(names['sr']);self.assertFalse(names['de'])

    def test_archive_tampering_and_stale_sources_fail(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);session=root/'session';shutil.copytree(IMPORT.SESSION,session)
            (root/'dist').mkdir();current=json.loads((ROOT/'dist/registry-candidates.json').read_text())
            current['sources']['persjCommit']='stale'
            (root/'dist/registry-candidates.json').write_text(json.dumps(current))
            with patch.object(IMPORT,'ROOT',root):
                with self.assertRaisesRegex(ValueError,'stale source'):IMPORT.load_session(session)
            (session/'user-review.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'archive hash mismatch'):IMPORT.load_session(session)

    def test_explicit_broader_bridge_does_not_allow_exact_equivalence(self):
        glot,_=parse_glottolog(ROOT/'upstream/glottolog/5.3/languoid.csv')
        items,*_=parse_wikidata_evidence(ROOT/'upstream/wikidata/2026-09-06/language-items.json')
        args=dict(ident='sr-x-priz-tim',qid='Q19894249',items=items,alignment=glot['news1236'],iso=None)
        self.assertEqual('Q19894249',GEN.validate_reviewed_wikidata_assignment(**args,relationship='broader').qid)
        with self.assertRaisesRegex(RuntimeError,'Glottolog alignment'):GEN.validate_reviewed_wikidata_assignment(**args,relationship='exact')

class PlanAssemblyTests(unittest.TestCase):
    def test_full_inventory_compiles_without_omitting_profiles(self):
        from registry_build import build_artifacts,load_sources
        from registry_sources import parse_effective_persj_catalog
        data=json.loads((ROOT/'dist/registry-candidates.json').read_text())
        excluded={p['id'] for p in data['profiles'] if p['reviewReasons'] and not p['approval']}
        self.assertEqual(set(),excluded)
        data['profiles']=[p for p in data['profiles'] if p['id'] not in excluded]
        data['ancestorCandidates']=[a for a in data['ancestorCandidates'] if a['canonicalCodeCandidate'] not in excluded]
        codes={p['id'] for p in data['profiles']}
        _,records=parse_effective_persj_catalog(GEN.PERSJ_SNAPSHOT)
        records=tuple(s for s in records if s.tag in codes)
        lock=json.loads((ROOT/'upstream/sources.json').read_text());publication=json.loads((ROOT/'registry/source-publication-metadata.json').read_text())
        sources=load_sources(lock,publication,ROOT)
        plan=ASSEMBLE.assemble(data,records,{s['manifestId'] for s in sources},[], '2026.9.6-1','2026-09-06')
        plan['approval'].update(mode='fixture',candidatesSha256=None,editorialReportSha256=None,overridesSha256=None,planPayloadSha256=None)
        registry,manifest=build_artifacts(plan,lock,publication,ROOT)
        self.assertTrue(registry);self.assertTrue(manifest)
        self.assertEqual(214,len(plan['tagProfiles']))
        self.assertEqual({p['id'] for p in data['profiles']},{p['id'] for p in plan['tagProfiles']})
        kajkavian=next(n for n in plan['nodes'] if n['id']=='hr-x-kajkav')
        self.assertEqual([{'type':'Glottolog','value':'kajk1237'}],kajkavian['identifiers'])
        from registry_build import validate_production_plan_provenance, plan_payload_sha256
        from registry_sources import sha256
        plan['approval'].update(mode='release',candidatesSha256=sha256(ROOT/'dist/registry-candidates.json'),editorialReportSha256=sha256(ROOT/'dist/editorial-review.tsv'),overridesSha256=sha256(ROOT/'registry/raskovnik-overrides.xml'))
        plan['approval']['planPayloadSha256']=plan_payload_sha256(plan)
        if data['summary']['ancestorExceptions']:
            with self.assertRaisesRegex(RegistryBuildError,'unapproved exceptions'):
                validate_production_plan_provenance(plan,ROOT)
        else:
            validate_production_plan_provenance(plan,ROOT)
        for ancestor in data['ancestorCandidates']:
            profile=next((p for p in data['profiles'] if p['id']==ancestor['canonicalCodeCandidate']),None)
            if profile and profile.get('glottolog') and profile['glottolog']['relationship']=='exact':
                self.assertEqual(profile['selectableCandidate'],ancestor['selectableCandidate'])
                self.assertEqual(profile['kindCandidate'],ancestor['kindCandidate'])
                self.assertEqual(profile['preferredLabels'],ancestor['preferredLabels'])


    def test_backend_compatibility_rejects_drift(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'metadata').mkdir();(root/'metadata/dictionary-version-manifest.json').write_text(json.dumps({'TEST':{'resource_hash':'sha256:'+'0'*64}}))
            path=root/'dictionaries/TEST/src/main/xar-resources/TEST.pcified.xml';path.parent.mkdir(parents=True);path.write_text('<TEI/>')
            with self.assertRaisesRegex(RegistryBuildError,'hash mismatch'):ASSEMBLE.compatibility_from_backend(root,['TEST'])

    def test_deterministic_source_inverse_and_cycle_rejection(self):
        data=json.loads((ROOT/'dist/registry-candidates.json').read_text())
        profile=copy.deepcopy(next(p for p in data['profiles'] if p['id']=='sr'))
        profile['parentCandidate']=None;profile['lineage']=[];profile['sourceRecordIds']=[]
        data['profiles']=[profile];data['ancestorCandidates']=[]
        kwargs=dict(source_records=(),source_ids={'src-raskovnik-review','src-glottolog-5-3','src-iana-2026-08-08','src-cldr-48-2','src-persj-catalog-'+GEN.PERSJ_COMMIT[:7]},compatibility=[],version='2026.9.6-1',reviewed_on='2026-09-06')
        plan=ASSEMBLE.assemble(data,**kwargs)
        self.assertEqual(plan,ASSEMBLE.assemble(copy.deepcopy(data),**kwargs))
        self.assertEqual(['sr'],plan['nodes'][0]['directTagProfileIds'])
        self.assertEqual([],plan['sourceRecords'])
        fixture=copy.deepcopy(plan);fixture['approval'].update(mode='fixture',candidatesSha256=None,editorialReportSha256=None,overridesSha256=None,planPayloadSha256=None)
        validate_plan(fixture,kwargs['source_ids'])
        profile['parentCandidate']='sr'
        with self.assertRaisesRegex(RegistryBuildError,'cycle'):ASSEMBLE.assemble(data,**kwargs)

if __name__=='__main__':unittest.main()
