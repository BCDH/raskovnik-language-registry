#!/usr/bin/env python3
"""Maven lifecycle contracts for fail-closed registry XAR assembly."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackageLifecycleTest(unittest.TestCase):
    def prepare_project(self, directory: Path, build_script: str) -> Path:
        for name in ("pom.xml", "xar-assembly.xml"):
            shutil.copy2(ROOT / name, directory / name)
        resources = directory / "src/main/xar-resources"
        resources.mkdir(parents=True)
        shutil.copy2(ROOT / "src/main/xar-resources/post-install.xq", resources)
        scripts = directory / "scripts"
        scripts.mkdir()
        (scripts / "build-registry.py").write_text(
            textwrap.dedent(build_script).lstrip(), encoding="utf-8"
        )
        return directory

    def package(self, project: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["mvn", "-o", "package", *arguments],
            cwd=project,
            text=True,
            capture_output=True,
        )

    def test_maven_package_rejects_missing_registry_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="registry-maven-missing-") as directory:
            project = self.prepare_project(Path(directory), "raise SystemExit(0)\n")
            result = self.package(project)
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn(
            "validated dist/registry.xml is required before XAR assembly",
            result.stderr + result.stdout,
        )

    def test_maven_property_cannot_bypass_compiler_with_preexisting_artifacts(self) -> None:
        for property_override in (
            "-Dpython.executable=true",
            "-Dmaven.antrun.skip=true",
        ):
            with self.subTest(property_override), tempfile.TemporaryDirectory(
                prefix="registry-maven-property-bypass-"
            ) as directory:
                project = self.prepare_project(Path(directory), "raise SystemExit(23)\n")
                distribution = project / "dist"
                distribution.mkdir()
                (distribution / "registry.xml").write_text(
                    "<stale-registry/>\n", encoding="utf-8"
                )
                (distribution / "manifest.xml").write_text(
                    "<stale-manifest/>\n", encoding="utf-8"
                )
                result = self.package(project, property_override)
                archives = list((project / "target").glob("*.xar"))
            self.assertNotEqual(0, result.returncode, result.stdout)
            self.assertEqual([], archives)

    def test_maven_package_contains_only_the_approved_xar_inventory(self) -> None:
        build_script = """
            from pathlib import Path

            root = Path(__file__).resolve().parents[1]
            distribution = root / "dist"
            distribution.mkdir()
            (distribution / "registry.xml").write_text("<registry/>\\n", encoding="utf-8")
            (distribution / "manifest.xml").write_text("<manifest/>\\n", encoding="utf-8")
        """
        with tempfile.TemporaryDirectory(prefix="registry-maven-inventory-") as directory:
            project = self.prepare_project(Path(directory), build_script)
            result = self.package(project)
            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
            archives = list((project / "target").glob("*.xar"))
            self.assertEqual(1, len(archives), archives)
            with zipfile.ZipFile(archives[0]) as archive:
                inventory = set(archive.namelist())
        self.assertEqual(
            {
                "registry.xml",
                "manifest.xml",
                "post-install.xq",
                "expath-pkg.xml",
                "exist.xml",
                "cxan.xml",
                "repo.xml",
            },
            inventory,
        )


if __name__ == "__main__":
    unittest.main()
