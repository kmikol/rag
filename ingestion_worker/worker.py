from __future__ import annotations

import argparse
import sys

from ingestion_worker.pipeline import process_pending_jobs_once


def main() -> int:
    """Run the ingestion worker once and exit."""
    parser = argparse.ArgumentParser(description="Process one pending ingestion job.")
    parser.add_argument("--worker-id", default=None)
    args = parser.parse_args()

    process_pending_jobs_once(worker_id=args.worker_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
