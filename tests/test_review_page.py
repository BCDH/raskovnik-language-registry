"""Review snapshots must never promote historical decisions into current proposals."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('review_page', ROOT / 'scripts/build-review-page.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ReviewPageTests(unittest.TestCase):
    def setUp(self):
        self.candidates = json.loads((ROOT / 'dist/registry-candidates.json').read_text())

    def test_split_history_is_comparison_only(self):
        old = [{'recordType':'tag-profile','id':'os','proposedLabelEn':'Old combined identity','proposedExactGlottocode':'osse1245'}]
        with tempfile.TemporaryDirectory() as directory:
            previous = Path(directory) / 'old.html'
            previous.write_text('<script id="audit-data" type="application/json">'+json.dumps(old)+'</script>')
            rows, _ = module.build(self.candidates, previous)
        rows = {r['recordType']+':'+r['id']:r for r in rows}
        iron, generic = rows['tag-profile:os'], rows['tag-profile:ira-x-ossetic']
        self.assertEqual(iron['proposedExactGlottocode'], 'iron1242')
        self.assertEqual(iron['proposedLabelEn'], 'Iron Ossetian')
        self.assertEqual(generic['proposedExactGlottocode'], '')
        self.assertEqual(generic['proposedWikidataQid'], 'Q33968')
        self.assertEqual(generic['legacyReviewKeys'], ['tag-profile:os'])
        for row in (iron, generic):
            self.assertEqual(row['approval'], 'APPROVED')
            self.assertEqual(row['legacyProposal']['proposedLabelEn'], 'Old combined identity')

    def test_complete_snapshot_and_missing_labels(self):
        rows, _ = module.build(self.candidates)
        self.assertEqual(len(rows),len(self.candidates['profiles'])+len(self.candidates['ancestorCandidates']))
        row = next(r for r in rows if r['id']=='afro1255')
        self.assertEqual(row['proposedLabelDe'],'Afroasiatische Sprachen')
        self.assertNotIn('missing-label-de',row['remainingReviewReasons'])

    def test_previous_embedded_source_hash_is_migratable(self):
        rows, _ = module.build(self.candidates)
        with tempfile.TemporaryDirectory() as d:
            previous=Path(d)/'previous.html'
            previous.write_text('<script id="audit-data" type="application/json">'+json.dumps(rows)+'</script><script id="review-meta" type="application/json">'+json.dumps({'sourceHash':'a'*64,'legacySourceHashes':['b'*64]})+'</script>')
            _,meta=module.build(self.candidates,previous)
        self.assertIn('a'*64,meta['legacySourceHashes'])
        self.assertIn('b'*64,meta['legacySourceHashes'])

    def test_snapshot_change_changes_storage_identity(self):
        _, before = module.build(self.candidates)
        self.candidates['profiles'][0]['preferredLabels']['en']='Changed proposal'
        _, after = module.build(self.candidates)
        self.assertNotEqual(before['sourceHash'],after['sourceHash'])
        self.assertNotEqual(before['proposalHash'],after['proposalHash'])

    def test_previous_audit_scope_and_queues_are_preserved(self):
        baseline = [
            {'recordType':'tag-profile','id':'ae','reviewQueue':'READY_TO_CONFIRM','proposedLabelDe':'Reviewed label','proposalFingerprint':'original'},
            {'recordType':'ancestor','id':'afro1255','reviewQueue':'POLICY_RESOLVED','proposedLabelSr':'Reviewed ancestor','proposalFingerprint':'ancestor'},
            {'recordType':'tag-profile','id':'pl-x-karpat','reviewQueue':'EDITORIAL_JUDGMENT','proposalFingerprint':'removed'},
        ]
        with tempfile.TemporaryDirectory() as directory:
            previous = Path(directory) / 'old.html'
            previous.write_text('<script id="audit-data">'+json.dumps(baseline)+'</script>')
            rows, _ = module.build(self.candidates, previous)
        self.assertEqual(rows[:2], baseline[:2])
        self.assertNotIn('pl-x-karpat', [r['id'] for r in rows])
        self.assertEqual([r['id'] for r in rows[2:]], ['sh','ira-x-ossetic'])
        self.assertTrue(all(r['reviewQueue']=='EDITORIAL_JUDGMENT' for r in rows[2:]))

    def test_script_embedding_escapes_markup(self):
        value = {'note':'</script><script>alert(1)</script>'}
        encoded = module.encoded(value)
        self.assertNotIn('<',encoded)
        self.assertEqual(json.loads(encoded),value)

if __name__=='__main__':
    unittest.main()
