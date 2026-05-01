from pathlib import Path

from shared.file_cleanup import (
    delete_file_if_present,
    delete_unique_files,
    is_path_under_roots,
    validate_file_cleanup_targets,
    validate_path_under_root,
    validate_path_under_roots,
)


def test_validate_path_under_roots_accepts_configured_root(tmp_path: Path) -> None:
    root = tmp_path / "watch"
    source = root / "notes.md"

    assert validate_path_under_roots(source, (root,)) == source.resolve(strict=False)


def test_validate_path_under_roots_rejects_outside_path(tmp_path: Path) -> None:
    root = tmp_path / "watch"
    outside = tmp_path / "outside.md"

    try:
        validate_path_under_roots(outside, (root,))
    except ValueError as error:
        assert str(error) == f"Path is outside configured watch roots: {outside}"
    else:
        raise AssertionError("expected outside path to be rejected")


def test_validate_path_under_root_rejects_outside_path(tmp_path: Path) -> None:
    root = tmp_path / "watch"
    outside = tmp_path / "outside.md"

    try:
        validate_path_under_root(outside, root)
    except ValueError as error:
        assert str(error) == f"Path is outside configured root: {outside}"
    else:
        raise AssertionError("expected outside path to be rejected")


def test_is_path_under_roots_returns_false_for_outside_path(tmp_path: Path) -> None:
    assert is_path_under_roots(tmp_path / "outside.md", (tmp_path / "watch",)) is False


def test_validate_file_cleanup_targets_rejects_directory(tmp_path: Path) -> None:
    directory = tmp_path / "directory"
    directory.mkdir()

    try:
        validate_file_cleanup_targets([directory])
    except ValueError as error:
        assert str(error) == f"Deletion target is not a file: {directory}"
    else:
        raise AssertionError("expected directory cleanup target to be rejected")


def test_delete_file_if_present_returns_whether_file_was_removed(tmp_path: Path) -> None:
    target = tmp_path / "target.md"
    target.write_text("content", encoding="utf-8")

    assert delete_file_if_present(target) is True
    assert delete_file_if_present(target) is False


def test_delete_unique_files_deletes_each_path_once(tmp_path: Path) -> None:
    target = tmp_path / "target.md"
    target.write_text("content", encoding="utf-8")

    assert delete_unique_files([target, target]) == [str(target)]
    assert not target.exists()
