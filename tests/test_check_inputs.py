from __future__ import annotations

import json
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPOSITORY_ROOT / "scripts" / "check-inputs.py"
MODULE_SPEC = importlib.util.spec_from_file_location("check_inputs", MODULE_PATH)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
CHECK_INPUTS = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = CHECK_INPUTS
MODULE_SPEC.loader.exec_module(CHECK_INPUTS)
InputVerificationError = CHECK_INPUTS.InputVerificationError
verify_inputs = CHECK_INPUTS.verify_inputs


class CheckInputsTest(unittest.TestCase):
    def _fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        source = root / "upstream" / "example" / "1" / "input.txt"
        source.parent.mkdir(parents=True)
        source.write_text("pinned input\n", encoding="utf-8")
        manifest = root / "upstream" / "sources.json"
        manifest.write_text(
            json.dumps(
                {
                    "schemaVersion": "raskovnik-language-registry-sources-v1",
                    "sources": [
                        {
                            "id": "example",
                            "title": "Example source",
                            "version": "1",
                            "revision": "revision-1",
                            "url": "https://example.invalid/source",
                            "files": [
                                {
                                    "path": "upstream/example/1/input.txt",
                                    "bytes": 13,
                                    "sha256": "569dcc66411eb4426c8032cd03aeb5b1128c1ad63024377ec80deee1cd215e08",
                                }
                            ],
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return temporary, root, manifest

    def test_repository_manifest_verifies_all_pinned_inputs(self) -> None:
        result = verify_inputs(REPOSITORY_ROOT / "upstream" / "sources.json", REPOSITORY_ROOT)
        self.assertEqual(14, result.source_count)
        self.assertEqual(18, result.file_count)
        self.assertEqual(6596156, result.total_bytes)

    def test_valid_fixture_is_accepted(self) -> None:
        temporary, root, manifest = self._fixture()
        self.addCleanup(temporary.cleanup)
        result = verify_inputs(manifest, root)
        self.assertEqual(1, result.source_count)
        self.assertEqual(1, result.file_count)
        self.assertEqual(13, result.total_bytes)

    def test_changed_input_is_rejected(self) -> None:
        temporary, root, manifest = self._fixture()
        self.addCleanup(temporary.cleanup)
        (root / "upstream" / "example" / "1" / "input.txt").write_text(
            "changed input\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(InputVerificationError, "size drift"):
            verify_inputs(manifest, root)

    def test_undeclared_upstream_file_is_rejected(self) -> None:
        temporary, root, manifest = self._fixture()
        self.addCleanup(temporary.cleanup)
        (root / "upstream" / "extra.txt").write_text("extra\n", encoding="utf-8")
        with self.assertRaisesRegex(InputVerificationError, "undeclared=.*upstream/extra.txt"):
            verify_inputs(manifest, root)

    def test_path_escape_is_rejected(self) -> None:
        temporary, root, manifest = self._fixture()
        self.addCleanup(temporary.cleanup)
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["sources"][0]["files"][0]["path"] = "upstream/../outside.txt"
        manifest.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(InputVerificationError, "not an allowed repository-relative path"):
            verify_inputs(manifest, root)

    def test_symbolic_link_input_is_rejected(self) -> None:
        temporary, root, manifest = self._fixture()
        self.addCleanup(temporary.cleanup)
        source = root / "upstream" / "example" / "1" / "input.txt"
        link = source.with_name("linked-input.txt")
        link.symlink_to(source)
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["sources"][0]["files"][0]["path"] = "upstream/example/1/linked-input.txt"
        manifest.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(InputVerificationError, "must not traverse a symbolic link"):
            verify_inputs(manifest, root)

    def test_duplicate_json_key_is_rejected(self) -> None:
        temporary, root, manifest = self._fixture()
        self.addCleanup(temporary.cleanup)
        manifest.write_text(
            '{"schemaVersion":"raskovnik-language-registry-sources-v1",'
            '"schemaVersion":"duplicate","sources":[]}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(InputVerificationError, "duplicate JSON key"):
            verify_inputs(manifest, root)


class PackagingContractTest(unittest.TestCase):
    def test_xar_installs_only_registry_distribution_and_acl_hook(self) -> None:
        package_namespace = {"p": "http://expath.org/ns/pkg"}
        package = ET.parse(REPOSITORY_ROOT / "xar-assembly.xml").getroot()
        self.assertEqual("${package-target}", package.findtext("p:target", namespaces=package_namespace))
        self.assertEqual("post-install.xq", package.findtext("p:finish", namespaces=package_namespace))
        dependencies = {
            node.get("package"): node.get("semver-min")
            for node in package.findall("p:dependency", package_namespace)
            if node.get("package")
        }
        self.assertEqual(
            {"http://raskovnik.org/raskovnik-data-core": "${requires.core.version}"},
            dependencies,
        )
        file_sets = {
            node.findtext("p:directory", namespaces=package_namespace): {
                include.text for include in node.findall("p:includes/p:include", package_namespace)
            }
            for node in package.findall("p:fileSets/p:fileSet", package_namespace)
        }
        self.assertEqual(
            {
                "${basedir}/dist": {"manifest.xml", "registry.xml"},
                "${basedir}/src/main/xar-resources": {"post-install.xq"},
            },
            file_sets,
        )

    def test_pom_pins_target_and_data_core_minimum(self) -> None:
        maven_namespace = {"m": "http://maven.apache.org/POM/4.0.0"}
        project = ET.parse(REPOSITORY_ROOT / "pom.xml").getroot()
        properties = project.find("m:properties", maven_namespace)
        assert properties is not None
        self.assertEqual(
            "raskovnik-data/metadata/languages",
            properties.findtext("m:package-target", namespaces=maven_namespace),
        )
        self.assertEqual(
            "2026.6.6-1",
            properties.findtext("m:requires.core.version", namespaces=maven_namespace),
        )


if __name__ == "__main__":
    unittest.main()
