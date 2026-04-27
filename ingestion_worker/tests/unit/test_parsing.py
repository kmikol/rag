from pathlib import Path

import pytest

from ingestion_worker.parsing import (
    EmptyScannedPdfError,
    MarkdownDocumentParser,
    PdfDocumentParser,
    default_parser_registry,
)


def test_markdown_parser_preserves_heading_paths_and_offsets(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    path.write_text(
        "# Project\n\nIntro text.\n\n## Detail\n\nDetail text.\n",
        encoding="utf-8",
    )

    document = MarkdownDocumentParser().parse(path)

    assert document.source_path == str(path)
    assert document.filename == "notes.md"
    assert document.content_type == "text/markdown"
    assert len(document.sections) == 2
    assert document.sections[0].heading_path == ("Project",)
    assert document.sections[0].section_title == "Project"
    assert document.sections[0].text == "Intro text."
    assert (
        path.read_text(encoding="utf-8")[
            document.sections[0].start_offset : document.sections[0].end_offset
        ].strip()
        == "Intro text."
    )
    assert document.sections[1].heading_path == ("Project", "Detail")
    assert document.sections[1].section_title == "Detail"
    assert document.sections[1].text == "Detail text."


def test_registry_skips_unsupported_formats(tmp_path: Path) -> None:
    path = tmp_path / "image.png"
    path.write_bytes(b"not a supported document")

    assert default_parser_registry().parse(path) is None


def test_pdf_parser_preserves_page_numbers_and_offsets(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "paper.pdf"
    path.write_bytes(b"%PDF test placeholder")

    class FakePage:
        def __init__(self, text: str):
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, file_path: str):
            assert file_path == str(path)
            self.pages = [
                FakePage("First paragraph.\n\nSecond paragraph."),
                FakePage("Third page text."),
            ]

    monkeypatch.setattr("ingestion_worker.parsing.PdfReader", FakeReader)

    document = PdfDocumentParser().parse(path)

    assert document.content_type == "application/pdf"
    assert [section.page_number for section in document.sections] == [1, 1, 2]
    assert [section.text for section in document.sections] == [
        "First paragraph.",
        "Second paragraph.",
        "Third page text.",
    ]
    assert document.sections[1].start_offset == 18
    assert document.sections[1].end_offset == 35


def test_pdf_parser_detects_empty_or_scanned_pdf(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF test placeholder")

    class FakePage:
        def extract_text(self) -> str:
            return ""

    class FakeReader:
        def __init__(self, file_path: str):
            assert file_path == str(path)
            self.pages = [FakePage(), FakePage()]

    monkeypatch.setattr("ingestion_worker.parsing.PdfReader", FakeReader)

    with pytest.raises(EmptyScannedPdfError) as exc_info:
        PdfDocumentParser().parse(path)

    assert exc_info.value.page_count == 2
