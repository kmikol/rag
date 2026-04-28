from __future__ import annotations

from ingestion_worker import worker
from ingestion_worker.pipeline import IngestionRunResult


def test_worker_fail_on_error_returns_one_for_failed_claimed_job(monkeypatch) -> None:
    monkeypatch.setattr(
        "ingestion_worker.worker.run_pending_job_once",
        lambda worker_id=None: IngestionRunResult(
            claimed=True,
            status="failed",
            job_id="job-1",
            error_message="parse failed",
        ),
    )
    monkeypatch.setattr("sys.argv", ["worker", "--fail-on-error"])

    assert worker.main() == 1


def test_worker_fail_on_error_returns_zero_when_no_job(monkeypatch) -> None:
    monkeypatch.setattr(
        "ingestion_worker.worker.run_pending_job_once",
        lambda worker_id=None: IngestionRunResult(claimed=False, status="idle"),
    )
    monkeypatch.setattr("sys.argv", ["worker", "--fail-on-error"])

    assert worker.main() == 0


def test_worker_default_returns_zero_for_failed_job(monkeypatch) -> None:
    monkeypatch.setattr(
        "ingestion_worker.worker.run_pending_job_once",
        lambda worker_id=None: IngestionRunResult(claimed=True, status="failed"),
    )
    monkeypatch.setattr("sys.argv", ["worker"])

    assert worker.main() == 0
