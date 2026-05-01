from __future__ import annotations

from pathlib import Path


def validate_path_under_roots(path: str | Path, roots: tuple[Path, ...]) -> Path:
    """Return a resolved path after verifying it is under one configured root."""
    if not roots:
        raise ValueError("WATCH_ROOTS must contain at least one path for document deletion.")
    for root in roots:
        try:
            return validate_path_under_root(path, root)
        except ValueError:
            continue
    raise ValueError(f"Path is outside configured watch roots: {path}")


def validate_path_under_root(path: str | Path, root: Path) -> Path:
    """Return a resolved path after verifying it is under one configured root."""
    resolved_path = resolve_path(Path(path))
    resolved_root = resolve_path(root)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError(f"Path is outside configured root: {path}") from error
    return resolved_path


def is_path_under_roots(path: str | Path, roots: tuple[Path, ...]) -> bool:
    """Return whether a path resolves under any configured root."""
    return any(is_path_under_root(path, root) for root in roots)


def is_path_under_root(path: str | Path, root: Path) -> bool:
    """Return whether a path resolves under one configured root."""
    try:
        validate_path_under_root(path, root)
    except ValueError:
        return False
    return True


def resolve_path(path: Path) -> Path:
    """Resolve a path for safety checks without requiring it to exist."""
    return path.expanduser().resolve(strict=False)


def validate_file_cleanup_targets(paths: list[Path]) -> None:
    """Reject cleanup targets that exist but are not regular files."""
    for path in paths:
        if path.exists() and not path.is_file():
            raise ValueError(f"Deletion target is not a file: {path}")


def delete_file_if_present(path: Path) -> bool:
    """Delete one file if present and return whether it was removed."""
    if not path.exists():
        return False
    path.unlink()
    return True


def delete_unique_files(paths: list[Path]) -> list[str]:
    """Delete each unique file path at most once and return deleted paths."""
    deleted: list[str] = []
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        if delete_file_if_present(path):
            deleted.append(str(path))
    return deleted
