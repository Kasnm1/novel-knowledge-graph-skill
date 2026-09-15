from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_cache_key(
    *,
    input_files: Mapping[str, Path | None],
    parameters: Mapping[str, Any],
    implementation_files: Iterable[Path],
) -> tuple[str, dict[str, Any]]:
    """Fingerprint every input and implementation dependency used by a build."""
    inputs = {name: sha256_file(path) if path is not None else None for name, path in sorted(input_files.items())}
    implementation = {
        str(path): sha256_file(path)
        for path in sorted({path.resolve() for path in implementation_files if path.is_file()}, key=str)
    }
    material = {
        "inputs": inputs,
        "parameters": json.loads(json.dumps(parameters, ensure_ascii=False, sort_keys=True, default=str)),
        "implementation": implementation,
    }
    raw = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest(), material


def verify_artifact_manifest(manifest: Mapping[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if manifest.get("status") != "complete":
        errors.append("manifest is not complete")
    for artifact in manifest.get("artifacts", []) if isinstance(manifest.get("artifacts"), list) else []:
        if not isinstance(artifact, Mapping):
            errors.append("malformed artifact entry")
            continue
        path = Path(str(artifact.get("path") or ""))
        expected = artifact.get("sha256")
        if not path.is_file():
            errors.append(f"missing artifact: {path}")
            continue
        actual = sha256_file(path)
        if expected != actual:
            errors.append(f"artifact fingerprint mismatch: {path}")
    return not errors, errors
