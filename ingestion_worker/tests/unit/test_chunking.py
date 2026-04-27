from ingestion_worker.chunking import StructureAwareChunker
from ingestion_worker.parsing import DocumentSection, ParsedDocument


def test_chunker_preserves_markdown_citation_metadata() -> None:
    document = ParsedDocument(
        source_path="/watch/notes.md",
        filename="notes.md",
        content_type="text/markdown",
        sections=(
            DocumentSection(
                text="Alpha beta gamma delta epsilon zeta.",
                source_path="/watch/notes.md",
                filename="notes.md",
                heading_path=("Project", "Detail"),
                section_title="Detail",
                start_offset=10,
                end_offset=46,
            ),
        ),
    )

    chunks = StructureAwareChunker(target_tokens=3, overlap_tokens=1).chunk(document)

    assert [chunk.text for chunk in chunks] == [
        "Alpha beta gamma",
        "gamma delta epsilon",
        "epsilon zeta.",
    ]
    assert chunks[0].source_path == "/watch/notes.md"
    assert chunks[0].filename == "notes.md"
    assert chunks[0].heading_path == ("Project", "Detail")
    assert chunks[0].section_title == "Detail"
    assert chunks[0].page_number is None
    assert chunks[0].start_offset == 10
    assert chunks[0].end_offset == 26
    assert chunks[0].token_count == 3


def test_chunker_preserves_pdf_page_metadata() -> None:
    document = ParsedDocument(
        source_path="/watch/paper.pdf",
        filename="paper.pdf",
        content_type="application/pdf",
        sections=(
            DocumentSection(
                text="One two three four.",
                source_path="/watch/paper.pdf",
                filename="paper.pdf",
                page_number=7,
                start_offset=100,
                end_offset=119,
            ),
        ),
    )

    chunks = StructureAwareChunker(target_tokens=10, overlap_tokens=2).chunk(document)

    assert len(chunks) == 1
    assert chunks[0].page_number == 7
    assert chunks[0].heading_path == ()
    assert chunks[0].start_offset == 100
    assert chunks[0].end_offset == 119


def test_chunker_rejects_invalid_overlap() -> None:
    try:
        StructureAwareChunker(target_tokens=10, overlap_tokens=10)
    except ValueError as exc:
        assert str(exc) == "overlap_tokens must be smaller than target_tokens"
    else:
        raise AssertionError("expected invalid overlap to raise")
