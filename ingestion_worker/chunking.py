from __future__ import annotations

import re
from dataclasses import dataclass

from ingestion_worker.parsing import DocumentSection, ParsedDocument


@dataclass(frozen=True)
class DocumentChunk:
    """Chunk of source text with citation metadata preserved."""

    text: str
    source_path: str
    filename: str
    heading_path: tuple[str, ...]
    page_number: int | None
    section_title: str | None
    start_offset: int | None
    end_offset: int | None
    token_count: int


class StructureAwareChunker:
    """Split normalized sections into deterministic citation-ready chunks."""

    _token_pattern = re.compile(r"\w+|[^\w\s]", re.UNICODE)

    def __init__(self, target_tokens: int = 500, overlap_tokens: int = 75) -> None:
        if target_tokens <= 0:
            raise ValueError("target_tokens must be positive")
        if overlap_tokens < 0:
            raise ValueError("overlap_tokens must not be negative")
        if overlap_tokens >= target_tokens:
            raise ValueError("overlap_tokens must be smaller than target_tokens")
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens

    def chunk(self, document: ParsedDocument) -> tuple[DocumentChunk, ...]:
        """Chunk a parsed document without crossing parser section boundaries."""
        chunks: list[DocumentChunk] = []
        for section in document.sections:
            chunks.extend(self._chunk_section(section))
        return tuple(chunks)

    def count_tokens(self, text: str) -> int:
        """Approximate token count deterministically using words and punctuation."""
        return len(self._token_pattern.findall(text))

    def _chunk_section(self, section: DocumentSection) -> list[DocumentChunk]:
        token_matches = list(self._token_pattern.finditer(section.text))
        if not token_matches:
            return []

        chunks: list[DocumentChunk] = []
        start_token = 0
        while start_token < len(token_matches):
            end_token = min(start_token + self.target_tokens, len(token_matches))
            start_char = token_matches[start_token].start()
            end_char = token_matches[end_token - 1].end()
            text = section.text[start_char:end_char].strip()
            start_offset = self._absolute_offset(section.start_offset, start_char)
            end_offset = self._absolute_offset(section.start_offset, end_char)
            chunks.append(self._build_chunk(section, text, start_offset, end_offset))

            if end_token == len(token_matches):
                break
            start_token = end_token - self.overlap_tokens

        return chunks

    def _build_chunk(
        self,
        section: DocumentSection,
        text: str,
        start_offset: int | None,
        end_offset: int | None,
    ) -> DocumentChunk:
        return DocumentChunk(
            text=text,
            source_path=section.source_path,
            filename=section.filename,
            heading_path=section.heading_path,
            page_number=section.page_number,
            section_title=section.section_title,
            start_offset=start_offset,
            end_offset=end_offset,
            token_count=self.count_tokens(text),
        )

    @staticmethod
    def _absolute_offset(base_offset: int | None, relative_offset: int) -> int | None:
        if base_offset is None:
            return None
        return base_offset + relative_offset
