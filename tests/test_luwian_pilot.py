from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import registry
import registry_editor as editor

class LuwianPilotTests(unittest.TestCase):
    def test_reviewed_children_preserve_umbrella_identity(self):
        root=Path(__file__).resolve().parents[1]
        data=(root/'registry/registry.xml').read_bytes()
        original=editor.node_record(editor.Document(data),editor.Document(data).get('ine-x-luwian'))
        with tempfile.TemporaryDirectory() as directory:
            draft=Path(directory)
            for name in ('registry','upstream'):shutil.copytree(root/name,draft/name)
            table=draft/'registry/glottolog-review.json';review=json.loads(table.read_text())
            for code in ('cune1239','hier1240'):
                self.assertNotIn(code,review['records'])
                review['records'][code]=editor.glottolog_record(root,code)['record']
            table.write_text(json.dumps(review))
            with patch.object(registry,'ROOT',draft):
                for code,tag in [('cune1239','xlu'),('hier1240','hlu')]:
                    data=editor.edit(data,{'operation':'create','expectedRevision':editor.revision(data),'rationale':'Reviewed Luwian fixture','values':{'id':tag,'kind':'language','parentId':'ine-x-luwian','labels':{'sr':'Пробни лувијски '+tag,'en':'Luwian fixture '+tag,'de':'Luwisches Beispiel '+tag},'identifiers':{'BCP47':tag,'ISO639-3':tag,'Glottolog':code}}})
                doc=editor.Document(data);umbrella=doc.get('ine-x-luwian')
                self.assertEqual(editor.T+'languageGrp',umbrella.element.tag)
                self.assertEqual(original['identifiers'],editor.node_record(doc,umbrella)['identifiers'])
                self.assertEqual(['xlu','hlu'],editor.node_record(doc,umbrella)['children'])
                registry.manifest(data,registry.validate(data))
