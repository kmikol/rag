import os
from pathlib import Path

from ingestion_worker.filesystem import (
    compute_sha256,
    copy_to_managed_store,
    parse_watch_roots,
    scan_watch_roots,
)


def test_parse_watch_roots_uses_os_pathsep_and_ignores_empty_segments() -> None:
    roots = parse_watch_roots(f" /watch/one {os.pathsep}{os.pathsep}/watch/two{os.pathsep}   ")

    assert roots == (Path("/watch/one"), Path("/watch/two"))


def test_scan_watch_roots_returns_supported_files_recursively(tmp_path: Path) -> None:
    watch_root = tmp_path / "watch"
    nested = watch_root / "nested"
    nested.mkdir(parents=True)
    markdown = watch_root / "notes.md"
    markdown.write_text("notes", encoding="utf-8")
    pdf = nested / "paper.pdf"
    pdf.write_bytes(b"%PDF placeholder")
    unsupported = nested / "image.png"
    unsupported.write_bytes(b"not a document")

    result = scan_watch_roots((watch_root,))

    assert result.unhealthy_roots == ()
    assert [file.relative_path for file in result.files] == [
        Path("nested/paper.pdf"),
        Path("notes.md"),
    ]
    assert [file.suffix for file in result.files] == [".pdf", ".md"]


def test_scan_watch_roots_skips_hidden_paths_by_default(tmp_path: Path) -> None:
    watch_root = tmp_path / "watch"
    hidden_dir = watch_root / ".hidden"
    hidden_dir.mkdir(parents=True)
    hidden_file = watch_root / ".secret.md"
    hidden_file.write_text("secret", encoding="utf-8")
    hidden_dir_file = hidden_dir / "nested.md"
    hidden_dir_file.write_text("secret", encoding="utf-8")
    visible = watch_root / "visible.md"
    visible.write_text("visible", encoding="utf-8")

    result = scan_watch_roots((watch_root,))

    assert [file.relative_path for file in result.files] == [Path("visible.md")]


def test_scan_watch_roots_can_include_hidden_paths(tmp_path: Path) -> None:
    watch_root = tmp_path / "watch"
    hidden_dir = watch_root / ".hidden"
    hidden_dir.mkdir(parents=True)
    (hidden_dir / "nested.md").write_text("secret", encoding="utf-8")
    (watch_root / ".secret.md").write_text("secret", encoding="utf-8")
    (watch_root / "visible.md").write_text("visible", encoding="utf-8")

    result = scan_watch_roots((watch_root,), include_hidden=True)

    assert [file.relative_path for file in result.files] == [
        Path(".hidden/nested.md"),
        Path(".secret.md"),
        Path("visible.md"),
    ]


def test_scan_watch_roots_reports_unhealthy_roots_and_scans_healthy_roots(
    tmp_path: Path,
) -> None:
    healthy_root = tmp_path / "watch"
    healthy_root.mkdir()
    (healthy_root / "notes.md").write_text("notes", encoding="utf-8")
    missing_root = tmp_path / "missing"
    file_root = tmp_path / "not-a-directory"
    file_root.write_text("plain file", encoding="utf-8")

    result = scan_watch_roots((missing_root, file_root, healthy_root))

    assert [file.relative_path for file in result.files] == [Path("notes.md")]
    assert [(root.root_path, root.reason) for root in result.unhealthy_roots] == [
        (missing_root, "missing"),
        (file_root, "not_directory"),
    ]


def test_scan_watch_roots_follows_symlinks_without_duplicates_or_cycles(
    tmp_path: Path,
) -> None:
    watch_root = tmp_path / "watch"
    real_dir = watch_root / "real"
    real_dir.mkdir(parents=True)
    (real_dir / "notes.md").write_text("notes", encoding="utf-8")
    (watch_root / "linked-real").symlink_to(real_dir, target_is_directory=True)
    (real_dir / "cycle").symlink_to(watch_root, target_is_directory=True)
    (watch_root / "linked-notes.md").symlink_to(real_dir / "notes.md")

    result = scan_watch_roots((watch_root,))

    assert [file.relative_path for file in result.files] == [Path("linked-notes.md")]


def test_compute_sha256_uses_raw_bytes(tmp_path: Path) -> None:
    source = tmp_path / "document.md"
    source.write_bytes(b"hello\nworld")

    assert compute_sha256(source) == (
        "26c60a61d01db5836ca70fefd44a6a016620413c8ef5f259a6c5612d4f79d3b8"
    )


def test_copy_to_managed_store_uses_hash_path_and_preserves_bytes(tmp_path: Path) -> None:
    source = tmp_path / "source" / "Notes.MD"
    source.parent.mkdir()
    source.write_bytes(b"managed content")
    content_hash = compute_sha256(source)
    document_store = tmp_path / "documents"

    managed_copy = copy_to_managed_store(source, content_hash, document_store)

    expected_path = document_store / content_hash[:2] / f"{content_hash}.md"
    assert managed_copy.source_path == source
    assert managed_copy.managed_path == expected_path
    assert managed_copy.content_hash == content_hash
    assert managed_copy.byte_size == len(b"managed content")
    assert expected_path.read_bytes() == b"managed content"


def test_copy_to_managed_store_is_idempotent_for_identical_content(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_bytes(b"managed content")
    content_hash = compute_sha256(source)
    document_store = tmp_path / "documents"

    first_copy = copy_to_managed_store(source, content_hash, document_store)
    second_copy = copy_to_managed_store(source, content_hash, document_store)

    assert second_copy == first_copy


def test_copy_to_managed_store_normalizes_uppercase_hash(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_bytes(b"managed content")
    content_hash = compute_sha256(source)
    document_store = tmp_path / "documents"

    managed_copy = copy_to_managed_store(source, content_hash.upper(), document_store)

    assert managed_copy.content_hash == content_hash
    assert managed_copy.managed_path == document_store / content_hash[:2] / f"{content_hash}.md"


def test_copy_to_managed_store_rejects_invalid_hash(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_bytes(b"managed content")

    try:
        copy_to_managed_store(source, "../not-a-sha", tmp_path / "documents")
    except ValueError as exc:
        assert str(exc) == "content_hash must be a 64-character SHA-256 hex digest"
    else:
        raise AssertionError("expected invalid content hash to raise")


def test_copy_to_managed_store_rejects_existing_mismatched_copy(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_bytes(b"managed content")
    content_hash = compute_sha256(source)
    document_store = tmp_path / "documents"
    managed_path = document_store / content_hash[:2] / f"{content_hash}.md"
    managed_path.parent.mkdir(parents=True)
    managed_path.write_bytes(b"different content")

    try:
        copy_to_managed_store(source, content_hash, document_store)
    except ValueError as exc:
        assert str(exc) == f"Managed copy hash mismatch: {managed_path}"
    else:
        raise AssertionError("expected mismatched managed copy to raise")


def test_copy_to_managed_store_rejects_source_hash_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_bytes(b"managed content")
    wrong_hash = compute_sha256(tmp_path / "source.md")
    source.write_bytes(b"changed content")

    try:
        copy_to_managed_store(source, wrong_hash, tmp_path / "documents")
    except ValueError as exc:
        assert str(exc) == f"Source content hash mismatch: {source}"
    else:
        raise AssertionError("expected source hash mismatch to raise")

    assert list((tmp_path / "documents" / wrong_hash[:2]).iterdir()) == []
