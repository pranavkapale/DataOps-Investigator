import json
from pathlib import Path

import pytest

from app.evidence_tools.spark import (
    MalformedSparkFixtureError,
    SparkFixtureEvidenceProvider,
    UnknownSparkJobError,
    UnknownSparkRunError,
)


SCENARIO_DIR = Path(__file__).resolve().parents[1] / "scenarios" / "spark_performance"
BASELINE_RUN_ID = "run-customer-aggregation-2026-08-21"
INCIDENT_RUN_ID = "run-customer-aggregation-2026-08-28"
JOB_ID = "customer_aggregation"


@pytest.fixture
def provider() -> SparkFixtureEvidenceProvider:
    return SparkFixtureEvidenceProvider(SCENARIO_DIR)


def test_provider_loads_baseline_and_incident_runs(provider: SparkFixtureEvidenceProvider) -> None:
    baseline = provider.get_job(BASELINE_RUN_ID)
    incident = provider.get_job(INCIDENT_RUN_ID)

    assert baseline.duration_seconds == 1500
    assert incident.duration_seconds == 6000
    assert baseline.job_id == incident.job_id == JOB_ID


def test_get_job_returns_factual_metadata(provider: SparkFixtureEvidenceProvider) -> None:
    job = provider.get_job(INCIDENT_RUN_ID)

    assert job.model_dump() == {
        "run_id": INCIDENT_RUN_ID,
        "job_id": JOB_ID,
        "job_name": "customer_aggregation",
        "timestamp": "2026-08-28T02:00:00Z",
        "status": "SUCCEEDED",
        "duration_seconds": 6000,
        "input_size_bytes": 579820584960,
        "output_size_bytes": 98784247808,
    }
    assert "root_cause" not in job.model_dump()


def test_get_stages_returns_stage_and_executor_telemetry(
    provider: SparkFixtureEvidenceProvider,
) -> None:
    telemetry = provider.get_stages(INCIDENT_RUN_ID)

    assert [stage.duration_seconds for stage in telemetry.stages] == [510, 5490]
    assert telemetry.stages[1].shuffle_read_bytes == 451186491392
    assert telemetry.executor_metrics.memory_spill_bytes == 12884901888
    assert telemetry.executor_metrics.gc_time_seconds == 331


def test_get_partition_statistics_returns_raw_distribution(
    provider: SparkFixtureEvidenceProvider,
) -> None:
    statistics = provider.get_partition_statistics(INCIDENT_RUN_ID)

    assert statistics.median == 4187593113
    assert statistics.largest == 46170898432
    assert "root_cause" not in statistics.model_dump()


def test_get_configuration_returns_spark_configuration(
    provider: SparkFixtureEvidenceProvider,
) -> None:
    configuration = provider.get_configuration(INCIDENT_RUN_ID)

    assert configuration["spark.sql.shuffle.partitions"] == "200"
    assert configuration["spark.executor.memory"] == "16g"


def test_get_baseline_returns_matching_job_run(provider: SparkFixtureEvidenceProvider) -> None:
    baseline = provider.get_baseline(JOB_ID, INCIDENT_RUN_ID)

    assert baseline.run_id == BASELINE_RUN_ID
    assert baseline.job_id == JOB_ID
    assert baseline.partition_count == 200


def test_provider_handles_unknown_run_and_job(provider: SparkFixtureEvidenceProvider) -> None:
    with pytest.raises(UnknownSparkRunError, match="was not found"):
        provider.get_job("run-does-not-exist")

    with pytest.raises(UnknownSparkJobError, match="does not belong"):
        provider.get_baseline("unknown_job", INCIDENT_RUN_ID)


def test_provider_does_not_read_evaluation_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    evaluation_path = SCENARIO_DIR / "evaluation" / "expected_diagnosis.json"
    original_open = Path.open

    def forbid_evaluation_read(path: Path, *args: object, **kwargs: object):
        if path == evaluation_path:
            raise AssertionError("Evidence provider must not read the evaluation contract.")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", forbid_evaluation_read)

    provider = SparkFixtureEvidenceProvider(SCENARIO_DIR)

    assert provider.get_job(INCIDENT_RUN_ID).run_id == INCIDENT_RUN_ID


def test_malformed_fixture_raises_application_error(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline"
    incident_dir = tmp_path / "incident"
    baseline_dir.mkdir()
    incident_dir.mkdir()
    (baseline_dir / "invalid.json").write_text("{not valid json", encoding="utf-8")
    (incident_dir / "placeholder.json").write_text(
        json.dumps(
            {
                "run_id": INCIDENT_RUN_ID,
                "job_id": JOB_ID,
                "job_name": JOB_ID,
                "timestamp": "2026-08-28T02:00:00Z",
                "status": "SUCCEEDED",
                "duration_seconds": 1,
                "input_size_bytes": 1,
                "output_size_bytes": 1,
                "partition_count": 1,
                "partition_size_stats_bytes": {
                    "smallest": 1,
                    "median": 1,
                    "p95": 1,
                    "largest": 1
                },
                "shuffle_bytes": {"read": 0, "write": 0},
                "executor_metrics": {
                    "peak_executor_memory_bytes": 1,
                    "memory_spill_bytes": 0,
                    "disk_spill_bytes": 0,
                    "gc_time_seconds": 0,
                    "failed_task_count": 0
                },
                "stage_metrics": [],
                "spark_configuration": {}
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(MalformedSparkFixtureError, match="malformed"):
        SparkFixtureEvidenceProvider(tmp_path)
