#!/usr/bin/env python3
"""Verify every pinned registry input without using the network."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


SCHEMA_VERSION = "raskovnik-language-registry-sources-v1"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
TOP_LEVEL_KEYS = {"schemaVersion", "sources"}
SOURCE_REQUIRED_KEYS = {"id", "title", "version", "revision", "url", "files"}
SOURCE_OPTIONAL_KEYS = {"artifactRevision"}
FILE_KEYS = {"path", "bytes", "sha256"}
ALLOWED_INPUT_PREFIXES = ("upstream/", "registry/schema/")


class InputVerificationError(RuntimeError):
    """A pinned input or its manifest is malformed or has drifted."""


@dataclass(frozen=True)
class VerificationResult:
    source_count: int
    file_count: int
    total_bytes: int


def _reject_duplicate_keys(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputVerificationError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _load_manifest(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise InputVerificationError(f"manifest must not be a symbolic link: {path}")
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise InputVerificationError(f"cannot read input manifest {path}: {exc}") from exc
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except InputVerificationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputVerificationError(f"invalid input manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise InputVerificationError("input manifest root must be an object")
    return value


def _require_exact_keys(value: dict[str, Any], expected: set[str], context: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise InputVerificationError(
            f"{context} keys differ: missing={missing!r} unexpected={unexpected!r}"
        )


def _require_nonempty_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise InputVerificationError(f"{context} must be a nonempty trimmed string")
    return value


def _safe_repo_path(root: Path, raw_path: Any, context: str) -> tuple[str, Path]:
    path_text = _require_nonempty_string(raw_path, context)
    posix_path = PurePosixPath(path_text)
    if (
        posix_path.is_absolute()
        or ".." in posix_path.parts
        or "." in posix_path.parts
        or str(posix_path) != path_text
        or not path_text.startswith(ALLOWED_INPUT_PREFIXES)
    ):
        raise InputVerificationError(f"{context} is not an allowed repository-relative path: {path_text!r}")
    candidate = root / Path(*posix_path.parts)
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise InputVerificationError(f"{context} escapes repository root: {path_text!r}") from exc
    current = candidate
    while current != root:
        if current.is_symlink():
            raise InputVerificationError(f"{context} must not traverse a symbolic link: {path_text!r}")
        current = current.parent
    return path_text, candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_inputs(manifest_path: Path, root: Path | None = None) -> VerificationResult:
    manifest_path = manifest_path.absolute()
    repository_root = (root.resolve() if root is not None else manifest_path.parent.parent.resolve())
    manifest = _load_manifest(manifest_path)
    manifest_real_path = manifest_path.resolve()
    _require_exact_keys(manifest, TOP_LEVEL_KEYS, "manifest")
    if manifest["schemaVersion"] != SCHEMA_VERSION:
        raise InputVerificationError(
            f"unsupported manifest schema {manifest['schemaVersion']!r}; expected {SCHEMA_VERSION!r}"
        )
    sources = manifest["sources"]
    if not isinstance(sources, list) or not sources:
        raise InputVerificationError("manifest sources must be a nonempty array")

    source_ids: list[str] = []
    declared_paths: list[str] = []
    total_bytes = 0
    for source_index, source in enumerate(sources):
        context = f"sources[{source_index}]"
        if not isinstance(source, dict):
            raise InputVerificationError(f"{context} must be an object")
        expected_keys = SOURCE_REQUIRED_KEYS | ({"artifactRevision"} if "artifactRevision" in source else set())
        _require_exact_keys(source, expected_keys, context)
        for field in ("id", "title", "version", "revision", "url"):
            _require_nonempty_string(source[field], f"{context}.{field}")
        if "artifactRevision" in source:
            _require_nonempty_string(source["artifactRevision"], f"{context}.artifactRevision")
        source_ids.append(source["id"])
        files = source["files"]
        if not isinstance(files, list) or not files:
            raise InputVerificationError(f"{context}.files must be a nonempty array")
        source_paths: list[str] = []
        for file_index, file_record in enumerate(files):
            file_context = f"{context}.files[{file_index}]"
            if not isinstance(file_record, dict):
                raise InputVerificationError(f"{file_context} must be an object")
            _require_exact_keys(file_record, FILE_KEYS, file_context)
            path_text, path = _safe_repo_path(repository_root, file_record["path"], f"{file_context}.path")
            source_paths.append(path_text)
            declared_paths.append(path_text)
            expected_bytes = file_record["bytes"]
            if isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int) or expected_bytes < 0:
                raise InputVerificationError(f"{file_context}.bytes must be a nonnegative integer")
            expected_hash = file_record["sha256"]
            if not isinstance(expected_hash, str) or SHA256_RE.fullmatch(expected_hash) is None:
                raise InputVerificationError(f"{file_context}.sha256 must be a lowercase SHA-256 digest")
            if path.is_symlink() or not path.is_file():
                raise InputVerificationError(f"pinned input is missing, not a file, or a symbolic link: {path_text}")
            actual_bytes = path.stat().st_size
            if actual_bytes != expected_bytes:
                raise InputVerificationError(
                    f"pinned input size drift for {path_text}: expected {expected_bytes}, got {actual_bytes}"
                )
            actual_hash = _sha256(path)
            if actual_hash != expected_hash:
                raise InputVerificationError(
                    f"pinned input hash drift for {path_text}: expected {expected_hash}, got {actual_hash}"
                )
            total_bytes += actual_bytes
        if source_paths != sorted(source_paths):
            raise InputVerificationError(f"{context}.files must be sorted lexically by path")

    if len(source_ids) != len(set(source_ids)):
        raise InputVerificationError("manifest source IDs must be unique")
    if source_ids != sorted(source_ids):
        raise InputVerificationError("manifest sources must be sorted lexically by ID")
    if len(declared_paths) != len(set(declared_paths)):
        raise InputVerificationError("each pinned input path must be declared exactly once")

    upstream_root = repository_root / "upstream"
    actual_upstream_paths = {
        path.relative_to(repository_root).as_posix()
        for path in upstream_root.rglob("*")
        if path.is_file() and path.resolve() != manifest_real_path
    }
    declared_upstream_paths = {path for path in declared_paths if path.startswith("upstream/")}
    undeclared = sorted(actual_upstream_paths - declared_upstream_paths)
    missing = sorted(declared_upstream_paths - actual_upstream_paths)
    if undeclared or missing:
        raise InputVerificationError(
            f"upstream inventory differs: undeclared={undeclared!r} missing={missing!r}"
        )

    return VerificationResult(len(sources), len(declared_paths), total_bytes)


def main(argv: list[str] | None = None) -> int:
    repository_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=repository_root / "upstream" / "sources.json",
        help="input-lock manifest (default: upstream/sources.json)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=repository_root,
        help="repository root used to resolve manifest paths",
    )
    args = parser.parse_args(argv)
    try:
        result = verify_inputs(args.manifest, args.root)
    except InputVerificationError as exc:
        print(f"input verification failed: {exc}", file=sys.stderr)
        return 1
    print(
        "pinned inputs verified: "
        f"sources={result.source_count} files={result.file_count} bytes={result.total_bytes}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
