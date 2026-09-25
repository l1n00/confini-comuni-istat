from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .config import SOURCE_COMPONENTS
from .errors import SourceValidationError


@dataclass(frozen=True)
class SourceFile:
    relative_path: str
    byte_length: int
    sha256: str


@dataclass(frozen=True)
class SourceManifest:
    files: tuple[SourceFile, ...]
    sha256: str


def hash_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical_manifest_bytes(files: tuple[SourceFile, ...]) -> bytes:
    return "".join(
        f"{f.relative_path}\t{f.byte_length}\t{f.sha256}\n"
        for f in sorted(files, key=lambda f: f.relative_path.encode("utf-8"))
    ).encode("utf-8")


def build_source_manifest(source_root: Path) -> SourceManifest:
    entries = []
    for relative in SOURCE_COMPONENTS:
        path = source_root / relative
        if not path.is_file():
            raise SourceValidationError(f"missing source component: {relative}")
        entries.append(SourceFile(relative, path.stat().st_size, hash_file(path)))
    files = tuple(entries)
    return SourceManifest(files, hashlib.sha256(canonical_manifest_bytes(files)).hexdigest())


def write_utf8_json(path: Path, value: object) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        stream.write("\n")


def write_source_manifest(path: Path, manifest: SourceManifest) -> None:
    write_utf8_json(path, {
        "schemaVersion": 1, "sha256": manifest.sha256,
        "files": [{"path": f.relative_path, "bytes": f.byte_length, "sha256": f.sha256}
                  for f in manifest.files],
    })
