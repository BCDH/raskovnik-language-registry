#!/usr/bin/env python3
"""Build deterministic effective registry artifacts after the editorial gate."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from registry_build import (
    RegistryBuildError,
    build_artifacts,
    load_json,
    validate_production_plan_provenance,
)


ROOT = Path(__file__).resolve().parents[1]


def assert_editorial_gate() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check-editorial-gate.py")],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RegistryBuildError(detail or "editorial release gate failed")


def validate_temp(registry_path: Path, manifest_path: Path, plan_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/validate-registry.py"),
            "--registry",
            str(registry_path),
            "--manifest",
            str(manifest_path),
            "--plan",
            str(plan_path),
        ],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RegistryBuildError(detail or "generated registry validation failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=ROOT / "dist/effective-registry-plan.json")
    parser.add_argument("--registry", type=Path, default=ROOT / "dist/registry.xml")
    parser.add_argument("--manifest", type=Path, default=ROOT / "dist/manifest.xml")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        # This gate deliberately runs before even checking whether a production plan exists.
        assert_editorial_gate()
        plan = load_json(args.plan)
        validate_production_plan_provenance(plan, ROOT)
        source_lock = load_json(ROOT / "upstream/sources.json")
        publication = load_json(ROOT / "registry/source-publication-metadata.json")
        registry, manifest = build_artifacts(plan, source_lock, publication, ROOT)
        with tempfile.TemporaryDirectory(prefix="raskovnik-effective-registry-") as directory:
            temporary = Path(directory)
            registry_candidate = temporary / "registry.xml"
            manifest_candidate = temporary / "manifest.xml"
            registry_candidate.write_bytes(registry)
            manifest_candidate.write_bytes(manifest)
            validate_temp(registry_candidate, manifest_candidate, args.plan)
        if args.check:
            stale = [
                path
                for path, expected in ((args.registry, registry), (args.manifest, manifest))
                if not path.is_file() or path.read_bytes() != expected
            ]
            if stale:
                raise RegistryBuildError(
                    "generated effective-registry artifacts are stale: "
                    + ", ".join(str(path) for path in stale)
                )
        else:
            args.registry.parent.mkdir(parents=True, exist_ok=True)
            args.manifest.parent.mkdir(parents=True, exist_ok=True)
            args.registry.write_bytes(registry)
            args.manifest.write_bytes(manifest)
    except (OSError, RegistryBuildError) as exc:
        print(f"effective registry build failed: {exc}", file=sys.stderr)
        return 1
    print(
        "effective registry build passed: "
        f"registry={args.registry} manifest={args.manifest} check={args.check}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
