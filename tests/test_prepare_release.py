"""Release numbering keeps editorial XML intact and behaves on retries."""

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import prepare_release as release


class PrepareReleaseTests(unittest.TestCase):
    def setUp(self):
        self.old_registry = '<revisionDesc>\n  <change type="registryVersion" n="2026.9.18-1" when="2026-09-18T00:00:00Z">First release.</change>\n</revisionDesc>\n'
        self.registry = self.old_registry.replace('<revisionDesc>', '<revisionDesc>\n  <change type="editorialReview">Reviewed source.</change>')
        self.pom = '<project><version>0.1.0</version></project>\n'
        self.now = datetime(2026, 9, 24, 9, 15, tzinfo=timezone.utc)

    def test_advances_both_versions_and_preserves_history(self):
        registry, pom, version, package, changed = release.prepare(self.registry, self.pom, self.old_registry, self.pom, self.now)
        self.assertTrue(changed)
        self.assertEqual((version, package), ('2026.9.24-1', '0.1.1'))
        self.assertIn('when="2026-09-24T09:15:00Z"', registry)
        self.assertIn('<change n="2026.9.18-1" when="2026-09-18T00:00:00Z">First release.</change>', registry)
        self.assertIn('<change type="editorialReview">Reviewed source.</change>', registry)
        self.assertIn('<version>0.1.1</version>', pom)
        self.assertEqual(release.prepare(registry, pom, self.old_registry, self.pom, self.now)[-1], False)

    def test_same_day_increments_sequence(self):
        old = self.old_registry.replace('2026.9.18-1', '2026.9.24-2')
        registry = old.replace('<revisionDesc>', '<revisionDesc>\n  <change type="editorialReview">Another change.</change>')
        self.assertEqual(release.prepare(registry, self.pom, old, self.pom, self.now)[2], '2026.9.24-3')

    def test_rejects_clean_source_and_partial_manual_versioning(self):
        with self.assertRaisesRegex(ValueError, 'No registry source changes'):
            release.prepare(self.old_registry, self.pom, self.old_registry, self.pom, self.now)
        with self.assertRaisesRegex(ValueError, 'advance together'):
            release.prepare(self.registry.replace('2026.9.18-1', '2026.9.24-1'), self.pom, self.old_registry, self.pom, self.now)

    def state(self, registry, version='0.1.0', registry_version='2026.9.18-1'):
        return {'installed': True, 'package_version': version, 'registry_version': registry_version,
                'content_sha256': hashlib.sha256(registry.encode()).hexdigest()}

    def test_local_install_version_decisions(self):
        installed = self.state(self.old_registry)
        self.assertFalse(release.ensure_local(self.old_registry, self.pom, installed, self.now)[-1])
        first = release.ensure_local(self.registry, self.pom, installed, self.now)
        self.assertEqual((first[2], first[3], first[4]), ('2026.9.24-1', '0.1.1', True))
        self.assertFalse(release.ensure_local(first[0], first[1], installed, self.now)[-1])
        # A failed install can retry with the prepared version. After a successful
        # install, another content edit must advance it again.
        next_edit = first[0].replace('Reviewed source.', 'Reviewed source again.')
        second = release.ensure_local(next_edit, first[1], self.state(first[0], '0.1.1', '2026.9.24-1'), self.now)
        self.assertEqual((second[2], second[3]), ('2026.9.24-2', '0.1.2'))

    def test_local_install_rejects_downgrade(self):
        with self.assertRaisesRegex(ValueError, 'downgrade'):
            release.ensure_local(self.registry, self.pom, self.state(self.old_registry, '0.1.1'), self.now)

    def test_first_local_install_uses_release_tag_as_baseline(self):
        absent = {'installed': False}
        with patch.object(release.subprocess, 'run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = self.old_registry.encode()
            self.assertFalse(release.ensure_local(self.old_registry, self.pom, absent, self.now)[-1])
            self.assertEqual(release.ensure_local(self.registry, self.pom, absent, self.now)[3], '0.1.1')


if __name__ == '__main__':
    unittest.main()
