from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ingestion_worker.parsing import ParserRegistry, default_parser_registry


@dataclass(frozen=True)
class DiscoveredFile:
    """Supported source file found under a configured watch root."""

    source_path: Path
    root_path: Path
    relative_path: Path
    suffix: str


@dataclass(frozen=True)
class UnhealthyWatchRoot:
    """Watch root that could not be safely scanned."""

    root_path: Path
    reason: str


@dataclass(frozen=True)
class WatchScanResult:
    """Result of scanning watch roots without applying deletion behavior."""

    files: tuple[DiscoveredFile, ...]
    unhealthy_roots: tuple[UnhealthyWatchRoot, ...]


@dataclass(frozen=True)
class ManagedCopy:
    """Managed document-store copy of a source file."""

    source_path: Path
    managed_path: Path
    content_hash: str
    byte_size: int


def parse_watch_roots(value: str) -> tuple[Path, ...]:
    """Parse the WATCH_ROOTS environment value as an OS path list."""
    return tuple(
        Path(part.strip()).expanduser() for part in value.split(os.pathsep) if part.strip()
    )


def compute_sha256(path: Path) -> str:
    """Compute a SHA-256 digest from raw file bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_to_managed_store(
    source_path: Path,
    content_hash: str,
    document_store_path: Path,
) -> ManagedCopy:
    """Copy a source file into the managed store using a hash-derived path."""
    source = Path(source_path)
    destination = (
        Path(document_store_path).expanduser()
        / content_hash[:2]
        / f"{content_hash}{source.suffix.lower()}"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        if compute_sha256(destination) != content_hash:
            raise ValueError(f"Managed copy hash mismatch: {destination}")
    else:
        shutil.copyfile(source, destination)

    return ManagedCopy(
        source_path=source,
        managed_path=destination,
        content_hash=content_hash,
        byte_size=destination.stat().st_size,
    )


def scan_watch_roots(
    roots: Iterable[Path],
    parser_registry: ParserRegistry | None = None,
    include_hidden: bool = False,
) -> WatchScanResult:
    """Discover supported files under healthy watch roots.

    Missing or unreadable roots are reported separately so future deletion
    reconciliation can avoid treating those roots as empty.
    """
    registry = parser_registry or default_parser_registry()
    files: list[DiscoveredFile] = []
    unhealthy_roots: list[UnhealthyWatchRoot] = []

    for root in roots:
        root_path = Path(root).expanduser()
        if not root_path.exists():
            unhealthy_roots.append(UnhealthyWatchRoot(root_path=root_path, reason="missing"))
            continue
        if not root_path.is_dir():
            unhealthy_roots.append(UnhealthyWatchRoot(root_path=root_path, reason="not_directory"))
            continue

        try:
            discovered = _scan_root(root_path, registry, include_hidden)
        except OSError as exc:
            unhealthy_roots.append(
                UnhealthyWatchRoot(root_path=root_path, reason=f"unreadable: {exc}")
            )
            continue
        files.extend(discovered)

    return WatchScanResult(files=tuple(files), unhealthy_roots=tuple(unhealthy_roots))


def _scan_root(
    root_path: Path,
    parser_registry: ParserRegistry,
    include_hidden: bool,
) -> list[DiscoveredFile]:
    files: list[DiscoveredFile] = []
    seen_dirs: set[Path] = set()
    seen_files: set[Path] = set()

    def visit(directory: Path) -> None:
        resolved_directory = directory.resolve(strict=True)
        if resolved_directory in seen_dirs:
            return
        seen_dirs.add(resolved_directory)

        for child in sorted(directory.iterdir(), key=lambda path: path.name):
            if not include_hidden and _has_hidden_part(child, root_path):
                continue

            if child.is_dir():
                visit(child)
                continue

            if not child.is_file() or parser_registry.get_parser(child) is None:
                continue

            resolved_file = child.resolve(strict=True)
            if resolved_file in seen_files:
                continue
            seen_files.add(resolved_file)

            files.append(
                DiscoveredFile(
                    source_path=child,
                    root_path=root_path,
                    relative_path=child.relative_to(root_path),
                    suffix=child.suffix.lower(),
                )
            )

    visit(root_path)
    return files


def _has_hidden_part(path: Path, root_path: Path) -> bool:
    relative_path = path.relative_to(root_path)
    return any(part.startswith(".") for part in relative_path.parts)
