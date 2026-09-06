"""Regression checks for editable TEI and independent package construction."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from xml.etree import ElementTree as E

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import registry as R


class TeiRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=(ROOT/'registry/registry.xml').read_bytes()
        cls.root=E.fromstring(cls.data)

    def changed(self,mutate):
        root=copy.deepcopy(self.root);mutate(root)
        return E.tostring(root)

    def node(self,root,code='sr'):
        return next(n for n in root.iter() if n.tag in (R.T+'language',R.T+'languageGrp') and n.get('ident')==code)

    def test_master_validates_and_manifest_is_deterministic(self):
        root=R.validate(self.data)
        first=R.manifest(self.data,root)
        self.assertEqual(first,R.manifest(self.data,root))
        manifest=E.fromstring(first)
        self.assertEqual(manifest.get('contentSha256'),R.digest(self.data))
        self.assertEqual(manifest.get('compatibilityPolicy'),'language-tag-coverage-v1')
        self.assertNotIn('planSha256',manifest.attrib)
        self.assertIsNone(manifest.find(R.M+'compatibility'))

    def test_duplicate_node_or_profile_fails(self):
        for mutation in [lambda r:self.node(r).set('ident','de'),lambda r:self.node(r).append(copy.deepcopy(self.node(r).find(R.T+'note[@type="tagProfile"]')))]:
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):R.validate(self.changed(mutation))

    def test_missing_label_and_dangling_pointer_fail(self):
        for mutation in [lambda r:self.node(r).remove(self.node(r).find(R.T+'name[@'+R.X+'lang="sr"]')),lambda r:self.node(r).find(R.T+'name').set('source','#unknown')]:
            with self.assertRaises(ValueError):R.validate(self.changed(mutation))

    def test_existing_pointer_with_wrong_semantic_target_fails(self):
        with self.assertRaisesRegex(ValueError,'registry source'):
            R.validate(self.changed(lambda r:self.node(r).find(R.T+'name').set('source','#lang-sr')))
        def alternative(root):
            note=E.SubElement(self.node(root),R.T+'note',type='alternateClassification',subtype='reviewed',ana='#catalog-isj-persj',source='#src-raskovnik-review')
            E.SubElement(note,R.T+'ref',type='alternatePathNode',target='#lang-sr')
        with self.assertRaisesRegex(ValueError,'classification record'):R.validate(self.changed(alternative))

    def test_noncanonical_or_unregistered_tags_fail(self):
        for code in ['SR','zz','sr-x','x-private']:
            with self.subTest(code=code),self.assertRaises((ValueError,RuntimeError)):
                R.validate(self.changed(lambda r:self.node(r).set('ident',code)))

    def test_iso_identity_cannot_be_changed_to_narrower_kajkavian(self):
        def mutation(root):
            E.SubElement(self.node(root,'hr-x-kajkav'),R.T+'ident',type='ISO639-3').text='kjv'
        # The existing exact ISO identity or the pinned Lex-0 identifier order rejects this drift.
        with self.assertRaises(ValueError):R.validate(self.changed(mutation))

    def test_family_coordinates_and_invalid_lex0_fail(self):
        def mutation(root):
            node=self.node(root)
            node.set('type','family')
            setting=E.SubElement(node,R.T+'settingDesc')
            place=E.SubElement(setting,R.T+'place');location=E.SubElement(place,R.T+'location')
            E.SubElement(location,R.T+'geo').text='1 2'
        with self.assertRaises(ValueError):R.validate(self.changed(mutation))
        with self.assertRaises(ValueError):R.validate(self.changed(lambda r:E.SubElement(r,R.T+'unexpected')))

    def test_generic_ossetian_and_iron_remain_distinct(self):
        generic=self.node(self.root,'ira-x-ossetic');iron=self.node(self.root,'os')
        self.assertIsNone(generic.find(R.T+'ident[@type="Glottolog"]'))
        self.assertEqual(iron.findtext(R.T+'ident[@type="Glottolog"]'),'iron1242')
        self.assertNotEqual(generic.findtext(R.T+'ident[@type="Wikidata"]'),iron.findtext(R.T+'ident[@type="Wikidata"]'))

    def test_clean_checkout_packages_without_sibling_repositories(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ('registry','scripts','src','upstream'):
                shutil.copytree(ROOT/name,root/name,ignore=shutil.ignore_patterns('__pycache__'))
            for name in ('pom.xml','xar-assembly.xml'):shutil.copy2(ROOT/name,root/name)
            before=(root/'registry/registry.xml').read_bytes()
            result=subprocess.run(['mvn','-o','package'],cwd=root,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(before,(root/'registry/registry.xml').read_bytes())
            metadata=json.loads((root/'dist/release.json').read_text())
            self.assertEqual(metadata['registry_content_sha256'],'sha256:'+R.digest(before))
            import zipfile
            with zipfile.ZipFile(root/'target'/metadata['filename']) as archive:
                self.assertEqual(archive.read('registry.xml'),before)
            # Maven cannot package an invalid master even with stale valid dist files.
            (root/'registry/registry.xml').write_text('<invalid/>')
            invalid=subprocess.run(['mvn','-o','package'],cwd=root,capture_output=True,text=True)
            self.assertNotEqual(invalid.returncode,0)

if __name__=='__main__':unittest.main()
