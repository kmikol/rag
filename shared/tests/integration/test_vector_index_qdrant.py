import os
from uuid import uuid4

from shared.vector_index import ChunkVector, QdrantVectorIndex


def test_qdrant_vector_index_round_trip() -> None:
    collection_name = f"test_chunks_{uuid4().hex}"
    index = QdrantVectorIndex(
        url=os.environ["QDRANT_URL"],
        collection_name=collection_name,
    )
    document_id = str(uuid4())
    first_version_id = str(uuid4())
    second_version_id = str(uuid4())
    first_chunk_id = str(uuid4())
    second_chunk_id = str(uuid4())

    index.ensure_collection(3)
    index.upsert_chunks(
        [
            ChunkVector(
                chunk_id=first_chunk_id,
                document_id=document_id,
                document_version_id=first_version_id,
                vector=[1.0, 0.0, 0.0],
            ),
            ChunkVector(
                chunk_id=second_chunk_id,
                document_id=document_id,
                document_version_id=second_version_id,
                vector=[0.0, 1.0, 0.0],
            ),
        ]
    )

    results = index.search([1.0, 0.0, 0.0], limit=2)

    assert results[0].chunk_id == first_chunk_id
    assert results[0].document_id == document_id
    assert results[0].document_version_id == first_version_id

    index.delete_by_document_version_id(first_version_id)
    remaining_chunk_ids = {result.chunk_id for result in index.search([1.0, 0.0, 0.0], limit=2)}
    assert first_chunk_id not in remaining_chunk_ids
    assert second_chunk_id in remaining_chunk_ids

    index.delete_by_document_id(document_id)
    assert index.search([1.0, 0.0, 0.0], limit=2) == []
