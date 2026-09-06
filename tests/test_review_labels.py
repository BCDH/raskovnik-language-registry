import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from review_labels import enrich

class ReviewLabelTests(unittest.TestCase):
    def test_only_blanks_change_without_reopening_decisions(self):
        row={'id':'x','recordType':'tag-profile','reviewQueue':'EDITORIAL_JUDGMENT','proposedLabelSr':'old','proposedLabelDe':''}
        state={'decision':'changed','values':{'labelSr':'My Serbian','labelDe':'','canonicalCode':'x','wikidataQid':'Q1'},'note':'keep','updatedAt':'2026-09-06'}
        baseline={'schema':'raskovnik-language-review-v5','review':{'tag-profile:x':state}}
        supplement={'labels':{'tag-profile:x':{'sr':'Replacement forbidden','de':'German','method':'test','source':'https://example.org','note':'test'}},'exceptions':{}}
        original=copy.deepcopy(baseline)
        rows,meta=enrich([row],{},baseline,supplement)
        self.assertEqual(baseline,original)
        self.assertEqual(rows[0]['reviewQueue'],'EDITORIAL_JUDGMENT')
        self.assertEqual(rows[0]['proposedLabelSr'],'My Serbian')
        expected=copy.deepcopy(state);expected['values']['labelDe']='German'
        self.assertEqual(meta['seedReview']['tag-profile:x'],expected)
        self.assertEqual(len(meta['labelSupplements']),1)

    def test_ancestor_translation_is_not_an_editorial_approval(self):
        row={'id':'node','recordType':'ancestor','reviewQueue':'POLICY_RESOLVED','proposedLabelSr':'','proposedLabelDe':'Existing'}
        s={'labels':{'ancestor:node':{'sr':'Translation','de':'Overwrite forbidden','method':'project-descriptive-translation','source':'https://example.org','note':'test'}},'exceptions':{'other':'pending'}}
        rows,meta=enrich([row],{}, {'schema':'raskovnik-language-review-v5','review':{}},s)
        self.assertEqual(rows[0]['proposedLabelDe'],'Existing')
        self.assertEqual(rows[0]['reviewQueue'],'POLICY_RESOLVED')
        self.assertEqual(meta['seedReview'],{})
        self.assertEqual(meta['labelExceptions'],s['exceptions'])
