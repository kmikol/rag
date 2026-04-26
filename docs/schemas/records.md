# Event and Record Schemas

Record schemas are not implemented yet.

The first implementation should define records for:

- `document`
- `document_version`
- `source_path`
- `chunk`
- `ingestion_job`
- `ingestion_error`

Each chunk record must preserve enough provenance for citations:

- `document_id`
- `document_version_id`
- `chunk_id`
- source path
- original filename
- page number or heading path where available
- offsets where practical
