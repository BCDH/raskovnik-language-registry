#!/usr/bin/env python3
"""Validate generated registry and manifest artifacts through every build gate."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from registry_build import (
    RegistryBuildError,
    load_json,
    load_sources,
    validate_generated_manifest,
    validate_generated_registry,
)


ROOT = Path(__file__).resolve().parents[1]


def run_validator(command: list[str], label: str) -> None:
    executable = shutil.which(command[0])
    if executable is None:
        raise RegistryBuildError(f"required {label} executable is unavailable: {command[0]}")
    result = subprocess.run([executable, *command[1:]], text=True, capture_output=True)
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        raise RegistryBuildError(f"{label} failed: {details}")


def validate_paths(registry_path: Path, manifest_path: Path, plan_path: Path) -> None:
    registry = registry_path.read_bytes()
    manifest = manifest_path.read_bytes()
    plan = load_json(plan_path)
    source_lock = load_json(ROOT / "upstream/sources.json")
    publication = load_json(ROOT / "registry/source-publication-metadata.json")
    sources = load_sources(source_lock, publication, ROOT)
    run_validator(
        ["jing", str(ROOT / "registry/schema/lex-0-f6d51f29.rng"), str(registry_path)],
        "pinned Lex-0 RNG validation",
    )
    run_validator(
        [
            "xmllint",
            "--noout",
            "--schematron",
            str(ROOT / "registry/schema/language-registry.sch"),
            str(registry_path),
        ],
        "Raskovnik Schematron validation",
    )
    run_validator(
        ["jing", str(ROOT / "registry/schema/registry-manifest.rng"), str(manifest_path)],
        "registry-manifest RNG validation",
    )
    validate_generated_registry(registry, plan)
    validate_generated_manifest(manifest, registry, plan, sources)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=ROOT / "dist/registry.xml")
    parser.add_argument("--manifest", type=Path, default=ROOT / "dist/manifest.xml")
    parser.add_argument("--plan", type=Path, default=ROOT / "dist/effective-registry-plan.json")
    args = parser.parse_args()
    try:
        validate_paths(args.registry, args.manifest, args.plan)
    except (OSError, RegistryBuildError) as exc:
        print(f"registry validation failed: {exc}", file=sys.stderr)
        return 1
    print(
        "registry validation passed: "
        f"registry={args.registry} manifest={args.manifest} plan={args.plan}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
