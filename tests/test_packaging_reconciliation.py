import copy
import importlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
MIGRATION=importlib.import_module('reconcile-packaging-review')
GEN=importlib.import_module('generate-candidates')
ASSEMBLE=importlib.import_module('assemble-registry-plan')
from registry_overrides import approved_iso_scope_exceptions, RegistryOverrideError
from registry_build import build_artifacts, RegistryBuildError, load_sources
from registry_sources import parse_effective_persj_catalog
NS=MIGRATION.NS

class PackagingReconciliationTests(unittest.TestCase):
    def sandbox(self,directory):
        root=Path(directory)
        (root/'upstream').symlink_to(ROOT/'upstream',target_is_directory=True)
        shutil.copytree(ROOT/'review/sessions',root/'review/sessions')
        shutil.copytree(ROOT/'registry',root/'registry')
        (root/'dist').mkdir()
        shutil.copy2(ROOT/'dist/registry-candidates.json',root/'dist/registry-candidates.json')
        return root

    def test_migration_report_and_human_history_are_preserved(self):
        manifest,_=MIGRATION.validated_migration(ROOT)
        self.assertEqual({'cel-x-gaulish':'xtg','ga-x-old':'sga','lt-x-old':'olt','vel':'dlm-x-vegliot'},{r['from']:r['to'] for r in manifest['migrations']})
        data,_=MIGRATION.reconcile(ROOT)
        self.assertEqual(data,(ROOT/'registry/raskovnik-overrides.xml').read_bytes())
        old=ET.parse(ROOT/MIGRATION.SESSION/'baseline-ledger.xml').getroot()
        new=ET.fromstring(data)
        human=[n for n in old.findall(NS+'reviewRecord') if n.get('reviewer')=='ttasovac']
        self.assertEqual(25,len(human))
        for n in human:
            actual=next(r for r in new.findall(NS+'reviewRecord') if r.get('key')==n.get('key') and r.get('source')==n.get('source'))
            self.assertEqual(n.findtext(NS+'payload'),actual.findtext(NS+'payload'))

    def test_unrelated_ledger_changes_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.sandbox(d)
            path=root/'registry/raskovnik-overrides.xml'
            path.write_text(path.read_text().replace('Mittelhochdeutsch','Changed by user'))
            with self.assertRaisesRegex(ValueError,'refusing overwrite'):MIGRATION.reconcile(root)

    def test_stale_snapshot_and_conflicting_source_ids_fail(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.sandbox(d)
            path=root/'dist/registry-candidates.json';data=json.loads(path.read_text());data['sources']['persjCommit']='stale';path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'stale source'):MIGRATION.reconcile(root)
        _,records=parse_effective_persj_catalog(GEN.PERSJ_SNAPSHOT)
        with patch.object(MIGRATION,'parse_effective_persj_catalog',side_effect=[({},records),({},records[:-1])]):
            with self.assertRaisesRegex(ValueError,'conflicting source identities'):MIGRATION.validated_migration(ROOT)

    def test_scope_exception_requires_approval_and_current_pinned_evidence(self):
        self.assertEqual(frozenset({('hr-x-kajkav','kajk1237','kjv')}),approved_iso_scope_exceptions(ROOT))
        for field,value,pattern in [('reviewStatus','pending','unapproved'),('node','sr','invalid'),('reviewedOn','invalid','date')]:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as d:
                root=self.sandbox(d);path=root/'registry/raskovnik-overrides.xml';tree=ET.parse(path);tree.find(NS+'isoScopeException').set(field,value);tree.write(path)
                with self.assertRaisesRegex(RegistryOverrideError,pattern):approved_iso_scope_exceptions(root)
        with tempfile.TemporaryDirectory() as d:
            root=self.sandbox(d);path=root/'registry/raskovnik-overrides.xml';tree=ET.parse(path);tree.find(NS+'isoScopeException/'+NS+'evidence').set('sha256','0'*64);tree.write(path)
            with self.assertRaisesRegex(RegistryOverrideError,'stale'):approved_iso_scope_exceptions(root)

    def test_scope_cannot_be_silently_inferred(self):
        with patch.object(GEN,'approved_iso_scope_exceptions',return_value=frozenset()):
            data=GEN.build_candidates()
        profile=next(p for p in data['profiles'] if p['id']=='hr-x-kajkav')
        self.assertIsNone(profile['approval'])
        self.assertIn('exact-iso-scope-review',profile['reviewReasons'])

    def test_native_compilation_rejects_missing_exception_and_narrower_promotion(self):
        candidates=json.loads((ROOT/'dist/registry-candidates.json').read_text())
        _,records=parse_effective_persj_catalog(GEN.PERSJ_SNAPSHOT)
        lock=json.loads((ROOT/'upstream/sources.json').read_text());publication=json.loads((ROOT/'registry/source-publication-metadata.json').read_text())
        sources=load_sources(lock,publication,ROOT)
        plan=ASSEMBLE.assemble(candidates,records,{s['manifestId'] for s in sources},[], '2026.9.6-1','2026-09-06')
        plan['approval'].update(mode='fixture',candidatesSha256=None,editorialReportSha256=None,overridesSha256=None,planPayloadSha256=None)
        with tempfile.TemporaryDirectory() as d:
            root=self.sandbox(d);path=root/'registry/raskovnik-overrides.xml';tree=ET.parse(path);tree.getroot().remove(tree.find(NS+'isoScopeException'));tree.write(path)
            with self.assertRaisesRegex(RegistryBuildError,'incomplete Glottolog/ISO'):build_artifacts(plan,lock,publication,root)
        node=next(n for n in plan['nodes'] if n['id']=='hr-x-kajkav');node['identifiers'].append(dict(type='ISO639-3',value='kjv'));node['identifiers'].sort(key=lambda x:x['type'])
        with self.assertRaisesRegex(RegistryBuildError,'narrower ISO'):build_artifacts(plan,lock,publication,ROOT)

if __name__=='__main__':unittest.main()
