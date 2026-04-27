from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader


@dataclass(frozen=True)
class DocumentSection:
    """Normalized text section emitted by a format-specific parser."""

    text: str
    source_path: str
    filename: str
    heading_path: tuple[str, ...] = field(default_factory=tuple)
    page_number: int | None = None
    section_title: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None


@dataclass(frozen=True)
class ParsedDocument:
    """Normalized parser result consumed by structure-aware chunking."""

    source_path: str
    filename: str
    content_type: str
    sections: tuple[DocumentSection, ...]


class EmptyScannedPdfError(ValueError):
    """Raised when a PDF has no extractable text layer."""

    def __init__(self, path: Path, page_count: int):
        super().__init__(f"PDF has no extractable text: {path}")
        self.path = path
        self.page_count = page_count


class BaseDocumentParser(ABC):
    """Parser contract for converting source files into normalized sections."""

    content_type: str

    @abstractmethod
    def parse(self, path: Path) -> ParsedDocument:
        """Parse a source file into normalized document sections."""


class MarkdownDocumentParser(BaseDocumentParser):
    """Parse Markdown into sections while preserving heading hierarchy."""

    content_type = "text/markdown"
    _heading_pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

    def parse(self, path: Path) -> ParsedDocument:
        text = path.read_text(encoding="utf-8")
        source_path = str(path)
        filename = path.name
        sections: list[DocumentSection] = []
        headings: list[str] = []
        body_lines: list[str] = []
        body_start_offset = 0
        current_title: str | None = None
        current_offset = 0

        def flush(end_offset: int) -> None:
            body = "\n".join(body_lines).strip()
            if not body:
                return
            sections.append(
                DocumentSection(
                    text=body,
                    source_path=source_path,
                    filename=filename,
                    heading_path=tuple(headings),
                    section_title=current_title,
                    start_offset=body_start_offset,
                    end_offset=end_offset,
                )
            )

        for line in text.splitlines(keepends=True):
            raw_line = line.rstrip("\r\n")
            heading_match = self._heading_pattern.match(raw_line)
            if heading_match:
                flush(current_offset)
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                headings = headings[: level - 1]
                headings.append(title)
                current_title = title
                body_lines = []
                body_start_offset = current_offset + len(line)
            else:
                if not body_lines:
                    body_start_offset = current_offset
                body_lines.append(raw_line)
            current_offset += len(line)

        flush(len(text))
        return ParsedDocument(
            source_path=source_path,
            filename=filename,
            content_type=self.content_type,
            sections=tuple(sections),
        )


class PdfDocumentParser(BaseDocumentParser):
    """Parse PDF text layers into page-aware paragraph sections."""

    content_type = "application/pdf"
    _paragraph_pattern = re.compile(r"\S(?:.*?(?:\n\s*\n|$))", re.DOTALL)

    def parse(self, path: Path) -> ParsedDocument:
        source_path = str(path)
        filename = path.name
        reader = PdfReader(str(path))
        sections: list[DocumentSection] = []

        for page_index, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            for match in self._paragraph_pattern.finditer(page_text):
                paragraph = match.group(0).strip()
                if not paragraph:
                    continue
                sections.append(
                    DocumentSection(
                        text=paragraph,
                        source_path=source_path,
                        filename=filename,
                        page_number=page_index,
                        start_offset=match.start(),
                        end_offset=match.end(),
                    )
                )

        if not sections:
            raise EmptyScannedPdfError(path, len(reader.pages))

        return ParsedDocument(
            source_path=source_path,
            filename=filename,
            content_type=self.content_type,
            sections=tuple(sections),
        )


class ParserRegistry:
    """Extension-based registry for supported document parsers."""

    def __init__(self) -> None:
        self._parsers: dict[str, BaseDocumentParser] = {}

    def register(self, extension: str, parser: BaseDocumentParser) -> None:
        """Register a parser for a file extension."""
        normalized = extension if extension.startswith(".") else f".{extension}"
        self._parsers[normalized.lower()] = parser

    def get_parser(self, path: Path) -> BaseDocumentParser | None:
        """Return a parser for the path, or None for unsupported formats."""
        return self._parsers.get(path.suffix.lower())

    def parse(self, path: Path) -> ParsedDocument | None:
        """Parse supported files and skip unsupported formats gracefully."""
        parser = self.get_parser(path)
        if parser is None:
            return None
        return parser.parse(path)


def default_parser_registry() -> ParserRegistry:
    """Build the default parser registry for initial ingestion formats."""
    registry = ParserRegistry()
    markdown_parser = MarkdownDocumentParser()
    registry.register(".md", markdown_parser)
    registry.register(".markdown", markdown_parser)
    registry.register(".pdf", PdfDocumentParser())
    return registry
