from pathlib import Path
import datetime
import sys
import unittest
from xml.etree import ElementTree as E
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import registry_editor as editor
import registry as registry


class GeographyEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.data=(Path(__file__).resolve().parents[1]/'registry/registry.xml').read_bytes()

    def apply(self,identifier,mode='individual',decisions=None,locations=None,data=None):
        data=self.data if data is None else data
        values={'mode':mode,'decisions':decisions or []}
        if locations is not None: values['locations']=locations
        return editor.edit(data,{'operation':'geography','id':identifier,'values':values,'expectedRevision':editor.revision(data),'rationale':'Geography fixture'})

    def decision(self,mechanism='proxy',nodeId='sr',status='approved',**extra):
        return dict(mechanism=mechanism,nodeId=nodeId,status=status,allLocations=True,source='#src-raskovnik-review',region='Reviewed region',period='Reviewed period',reviewedAt='2026-09-13',rationale='Fixture approval',**extra)

    def test_proxy_is_separate_from_identity_and_requires_v3_manifest(self):
        data=self.apply('cu-x-srp',decisions=[self.decision()])
        doc=editor.Document(data); node=editor.node_record(doc,doc.get('cu-x-srp'))
        self.assertEqual('cu-x-church',node['parentId'])
        self.assertNotIn('ISO639-3',node['identifiers'])
        self.assertEqual('proxy',node['geography']['decisions'][0]['mechanism'])
        manifest=E.fromstring(registry.manifest(data,registry.validate(data)))
        self.assertEqual('3',manifest.get('formatVersion'))
        self.assertEqual('reviewed-v1',manifest.get('geographyPolicy'))

    def test_blocks_can_exist_without_coordinates(self):
        data=self.apply('obt',decisions=[self.decision(nodeId='br',status='blocked')])
        self.assertIn(b'subtype="blocked"',data)

    def test_family_cannot_be_a_proxy(self):
        with self.assertRaises(ValueError): self.apply('cu-x-srp',decisions=[self.decision(nodeId='sla')])

    def test_broader_relationship_requires_ancestry(self):
        with self.assertRaises(ValueError): self.apply('cu-x-srp',decisions=[self.decision(mechanism='broader')])

    def test_aggregate_cannot_keep_own_coordinates(self):
        with self.assertRaises(ValueError): self.apply('sr',mode='aggregate')

    def test_aggregate_cycle_is_rejected(self):
        data=self.apply('cu',mode='aggregate',decisions=[self.decision(mechanism='member',nodeId='cu-x-church')])
        with self.assertRaises(ValueError): self.apply('cu-x-church',mode='aggregate',decisions=[self.decision(mechanism='member',nodeId='cu')],data=data)

    def test_changing_donor_preserves_the_old_binding_for_runtime_staleness(self):
        data=self.apply('cu-x-srp',decisions=[self.decision()])
        before=editor.Document(data)
        decision=before.get('cu-x-srp').element.find(editor.T+'note[@type="geographyDecision"]')
        binding=decision.find(editor.T+'ref[@type="geographyLocation"]').get('n')
        donor=editor.node_record(before,before.get('sr'))
        donor['locations'][0]['coordinates']='44 20'
        changed=self.apply('sr',locations=donor['locations'],data=data)
        after=editor.Document(changed)
        stale=after.get('cu-x-srp').element.find(editor.T+'note[@type="geographyDecision"]')
        self.assertEqual(binding,stale.find(editor.T+'ref[@type="geographyLocation"]').get('n'))


if __name__=='__main__':unittest.main()

class PreservationTests(unittest.TestCase):
    setUpClass=classmethod(GeographyEditorTests.setUpClass.__func__)
    apply=GeographyEditorTests.apply
    decision=GeographyEditorTests.decision
    def test_coordinate_change_preserves_unknown_location_content(self):
        doc=editor.Document(self.data);span=doc.get('sr')
        place=next(s for s in doc.spans if s.element.tag==editor.T+'location' and s.parent.parent.parent is span)
        marker=b'<!-- reviewed manuscript note: retain exactly -->'
        source=doc.apply([(place.close_start,place.close_start,marker)])
        doc=editor.Document(source);locations=editor.node_record(doc,doc.get('sr'))['locations']
        locations[0]['coordinates']='44 20'
        result=self.apply('sr',locations=locations,data=source)
        self.assertIn(marker,result)
        self.assertIn(b'<geo>44 20</geo>',result)

    def test_new_source_and_location_validate_together(self):
        source=editor.edit(self.data,{'operation':'source','values':{'id':'src-fixture','title':'Historical fixture','url':'https://example.org/source','version':'1','attribution':'Fixture'},'expectedRevision':editor.revision(self.data),'rationale':'Source fixture'})
        result=self.apply('obt',locations=[{'type':'historical','source':'#src-fixture','sourceNode':'record-1','coordinates':'48 -4'}],decisions=[self.decision(mechanism='own',nodeId=None)],data=source)
        registry.manifest(result,registry.validate(result))

    def test_worklists_have_expected_initial_members(self):
        worklists=editor.inventory(self.data)['worklists']
        self.assertEqual([18,8,7,50],[len(worklists[k]) for k in 'ABCD'])
        self.assertIn('en-US',worklists['D'])
        self.assertIn('obt',worklists['A'])

class StaleApprovalTests(unittest.TestCase):
    def test_stale_donor_review_requires_explicit_reconfirmation(self):
        fixture=GeographyEditorTests();fixture.data=(Path(__file__).resolve().parents[1]/'registry/registry.xml').read_bytes()
        data=fixture.apply('cu-x-srp',decisions=[fixture.decision()])
        doc=editor.Document(data);locations=editor.node_record(doc,doc.get('sr'))['locations'];locations[0]['coordinates']='44 20'
        data=fixture.apply('sr',locations=locations,data=data)
        doc=editor.Document(data);record=editor.node_record(doc,doc.get('cu-x-srp'))
        self.assertTrue(record['geography']['decisions'][0]['stale'])
        with self.assertRaisesRegex(ValueError,'reconfirm'):fixture.apply('cu-x-srp',decisions=[fixture.decision()],data=data)
        result=editor.edit(data,{'operation':'geography','id':'cu-x-srp','expectedRevision':editor.revision(data),'rationale':'Explicit renewed review','values':{'mode':'individual','reconfirmStale':True,'decisions':[fixture.decision()]}})
        doc=editor.Document(result)
        self.assertFalse(editor.node_record(doc,doc.get('cu-x-srp'))['geography']['decisions'][0]['stale'])
