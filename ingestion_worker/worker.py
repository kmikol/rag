from __future__ import annotations

import argparse
import sys

from ingestion_worker.pipeline import run_pending_job_once


def main() -> int:
    """Run the ingestion worker once and exit."""
    parser = argparse.ArgumentParser(description="Process one pending ingestion job.")
    parser.add_argument("--worker-id", default=None)
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Return a non-zero exit code when a claimed job ends in failed.",
    )
    args = parser.parse_args()

    result = run_pending_job_once(worker_id=args.worker_id)
    if args.fail_on_error and result.status == "failed":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
