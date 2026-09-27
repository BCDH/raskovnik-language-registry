"""Contract tests for editorial operations on the actual TEI vocabulary."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import registry_editor as editor


class RegistryEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=(Path(__file__).resolve().parents[1]/'registry/registry.xml').read_bytes()

    def change(self,data=None,**request):
        data=self.data if data is None else data
        return editor.edit(data,dict(expectedRevision=editor.revision(data),rationale='Editorial fixture',**request))

    def test_no_op_is_byte_identical(self):
        record=editor.node_record(editor.Document(self.data),editor.Document(self.data).get('got'))
        self.assertEqual(self.data,self.change(operation='update',id='got',values=record))

    def test_catalog_names_inherit_and_editor_round_trips_overrides(self):
        doc=editor.Document(self.data);record=editor.node_record(doc,doc.get('cop'))
        self.assertEqual(record['sourceLabels'][0]['labels'],{'sr':'коптски','en':'Coptic','de':'Koptisch'})
        self.assertEqual([],doc.get('cop').element.findall(editor.T+'name[@type="sourceRecordLabel"]'))
        self.assertEqual(record['identifiers']['ISO639-2B'],'cop')
        changed=record['sourceLabels'][0].copy();changed['labels']={**changed['labels'],'en':'Catalog Coptic'}
        result=self.change(operation='update',id='cop',values={'sourceLabels':[changed]})
        after=editor.Document(result);override=after.get('cop').element.find(editor.T+'name[@type="sourceRecordLabel"]')
        self.assertEqual(override.text,'Catalog Coptic')
        self.assertIsNone(override.get(editor.X+'id'))
        self.assertEqual(editor.node_record(after,after.get('cop'))['sourceLabels'][0]['labels']['en'],'Catalog Coptic')
        changed['labels']['en']='Coptic'
        restored=self.change(result,operation='update',id='cop',values={'sourceLabels':[changed]})
        self.assertEqual([],editor.Document(restored).get('cop').element.findall(editor.T+'name[@type="sourceRecordLabel"]'))

    def test_inherited_catalog_translation_follows_preferred_name(self):
        doc=editor.Document(self.data);record=editor.node_record(doc,doc.get('cop'))
        record['labels']['en']='Coptic language'
        result=self.change(operation='update',id='cop',values={'labels':record['labels']})
        updated=editor.Document(result)
        self.assertEqual(editor.node_record(updated,updated.get('cop'))['sourceLabels'][0]['labels']['en'],'Coptic language')
        self.assertEqual([],updated.get('cop').element.findall(editor.T+'name[@type="sourceRecordLabel"]'))

    def test_shared_review_history_is_resolved(self):
        doc=editor.Document(self.data);span=doc.get('afa')
        note=span.element.find(editor.T+'note[@type="editorialReview"]')
        self.assertIsNotNone(note.get('corresp'))
        self.assertTrue(any('Complete ancestor-label proposal batch' in entry for entry in editor.node_record(doc,span)['history']))

    def test_label_edit_preserves_other_nodes_and_unknown_markup(self):
        original=editor.Document(self.data)
        s=original.get('got')
        data=original.apply([(s.open_end,s.open_end,b'<!-- editorial comment -->\n')])
        before=editor.Document(data)
        record=editor.node_record(before,before.get('got'))
        record['labels']['en']='Gothic language'
        result=self.change(data,operation='update',id='got',values=record)
        after=editor.Document(result)
        self.assertIn(b'<!-- editorial comment -->',result)
        for identifier in ('sr','fa','cu-x-srp'):
            self.assertEqual(before.raw(before.get(identifier)),after.raw(after.get(identifier)))
        for lang in ('sr','de'):
            pred=lambda s:s.element.tag==editor.T+'name' and s.element.get(editor.X+'lang')==lang and s.element.get('role')=='languageReferenceName'
            self.assertEqual(before.raw(next(filter(pred,before.get('got').children))),after.raw(next(filter(pred,after.get('got').children))))

    def test_stale_revision_fails(self):
        with self.assertRaises(editor.EditorError) as error:
            editor.edit(self.data,dict(expectedRevision='stale',operation='delete',id='got'))
        self.assertEqual('conflict',error.exception.code)

    def test_alias_edit_preserves_unexposed_languages_and_their_markup(self):
        doc=editor.Document(self.data);span=doc.get('got')
        alias=b'<name type="languageName" role="languageAlias" source="#src-raskovnik-review" xml:lang="fr">gotique<!-- retain editorial markup --></name>'
        data=doc.apply([(span.open_end,span.open_end,alias)])
        editor.validate(data)
        before=editor.Document(data);record=editor.node_record(before,before.get('got'))
        record['aliases']['en'].append('Gothic fixture alias')
        result=self.change(data,operation='update',id='got',values=record)
        self.assertIn(alias,result)
        self.assertIn(b'Gothic fixture alias',result)
        self.assertEqual(result,self.change(result,operation='update',id='got',values=editor.node_record(editor.Document(result),editor.Document(result).get('got'))))

    def test_create_and_delete_repair_parent_wrapper(self):
        result=self.change(operation='create',values=dict(id='ine-x-editor-test',parentId='ine-x-luwian',labels={'sr':'Проба','en':'Test','de':'Test'},selectable=True))
        doc=editor.Document(result)
        self.assertEqual(editor.T+'languageGrp',doc.get('ine-x-luwian').element.tag)
        self.assertIsNone(doc.get('ine-x-luwian').element.get('role'))
        result=self.change(result,operation='delete',id='ine-x-editor-test')
        self.assertEqual(editor.T+'language',editor.Document(result).get('ine-x-luwian').element.tag)

    def test_cannot_remove_a_covered_tag(self):
        with self.assertRaises(editor.EditorError) as error:
            self.change(operation='delete',id='got')
        self.assertEqual('coverage_required',error.exception.code)

    def test_cannot_move_a_node_into_its_descendant(self):
        with self.assertRaises(editor.EditorError):
            self.change(operation='update',id='cu',values={'parentId':'cu-x-srp'})

    def test_cannot_rename_stable_id(self):
        with self.assertRaises(editor.EditorError):
            self.change(operation='update',id='got',values={'id':'en'})

    def test_invalid_iso_and_unreviewed_glottolog_fail(self):
        for ids in ({'Glottolog':'cune1239'},{'ISO639-3':'invalid'}):
            with self.assertRaises(ValueError):
                self.change(operation='create',values=dict(id='ine-x-editor-test',labels={'en':'Test'},selectable=False,identifiers=ids))

    def test_missing_required_label_does_not_save(self):
        with self.assertRaises(ValueError):
            self.change(operation='update',id='got',values={'labels':{'en':'Gothic'}})

    def test_rejects_entity_declarations(self):
        with self.assertRaises(editor.EditorError):
            editor.Document(b'<!DOCTYPE TEI><TEI/>')


if __name__=='__main__': unittest.main()

class ExclusionReviewTests(unittest.TestCase):
    def test_reviewed_exclusion_cannot_be_promoted_to_exact_identity(self):
        data=(Path(__file__).resolve().parents[1]/'registry/registry.xml').read_bytes()
        values={'exclusions':[{'type':'Glottolog','value':'serb1264','source':'#src-raskovnik-review'}]}
        data=editor.edit(data,{'operation':'exclusions','id':'cu-x-srp','expectedRevision':editor.revision(data),'rationale':'Fixture: modern Serbian is not the exact recension','values':values})
        doc=editor.Document(data);ids=editor.node_record(doc,doc.get('cu-x-srp'))['identifiers'];ids['Glottolog']='serb1264'
        with self.assertRaisesRegex(ValueError,'exclusion'):
            editor.edit(data,{'operation':'update','id':'cu-x-srp','expectedRevision':editor.revision(data),'rationale':'Invalid promotion','values':{'identifiers':ids}})
