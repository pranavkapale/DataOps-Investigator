from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from pydantic import BaseModel, ValidationError


DEFAULT_SCENARIO_DIR = (
    Path(__file__).resolve().parents[2] / "scenarios" / "spark_performance"
)


class SparkEvidenceProviderError(RuntimeError):
    """Base error for local Spark evidence retrieval failures."""


class UnknownSparkRunError(SparkEvidenceProviderError):
    """Raised when a requested run ID is not present in the fixture."""


class UnknownSparkJobError(SparkEvidenceProviderError):
    """Raised when a run does not belong to the requested job."""


class MalformedSparkFixtureError(SparkEvidenceProviderError):
    """Raised when a telemetry fixture cannot be read or validated."""


class SparkPartitionStatistics(BaseModel):
    smallest: int
    median: int
    p95: int
    largest: int


class SparkExecutorMetrics(BaseModel):
    peak_executor_memory_bytes: int
    memory_spill_bytes: int
    disk_spill_bytes: int
    gc_time_seconds: int
    failed_task_count: int


class SparkStagePartitionStatistics(BaseModel):
    median: int
    largest: int


class SparkStageTelemetry(BaseModel):
    stage_id: int
    name: str
    duration_seconds: int
    task_count: int
    partition_size_stats_bytes: SparkStagePartitionStatistics
    shuffle_read_bytes: int
    shuffle_write_bytes: int


class SparkRunTelemetry(BaseModel):
    run_id: str
    job_id: str
    job_name: str
    timestamp: str
    status: str
    duration_seconds: int
    input_size_bytes: int
    output_size_bytes: int
    partition_count: int
    partition_size_stats_bytes: SparkPartitionStatistics
    shuffle_bytes: Dict[str, int]
    executor_metrics: SparkExecutorMetrics
    stage_metrics: List[SparkStageTelemetry]
    spark_configuration: Dict[str, str]


class SparkJobTelemetry(BaseModel):
    run_id: str
    job_id: str
    job_name: str
    timestamp: str
    status: str
    duration_seconds: int
    input_size_bytes: int
    output_size_bytes: int


class SparkStagesTelemetry(BaseModel):
    run_id: str
    stages: List[SparkStageTelemetry]
    executor_metrics: SparkExecutorMetrics


@dataclass(frozen=True)
class _FixtureRun:
    role: str
    telemetry: SparkRunTelemetry


class SparkFixtureEvidenceProvider:
    """Read-only access to the local Spark performance scenario telemetry."""

    def __init__(self, scenario_dir: Path | None = None) -> None:
        self.scenario_dir = scenario_dir or DEFAULT_SCENARIO_DIR
        self._runs = self._load_runs()

    def get_job(self, run_id: str) -> SparkJobTelemetry:
        run = self._get_run(run_id)
        telemetry = run.telemetry
        return SparkJobTelemetry(
            run_id=telemetry.run_id,
            job_id=telemetry.job_id,
            job_name=telemetry.job_name,
            timestamp=telemetry.timestamp,
            status=telemetry.status,
            duration_seconds=telemetry.duration_seconds,
            input_size_bytes=telemetry.input_size_bytes,
            output_size_bytes=telemetry.output_size_bytes,
        )

    def get_run(self, run_id: str) -> SparkRunTelemetry:
        """Return the complete raw telemetry fixture for a known run."""
        return self._get_run(run_id).telemetry

    def get_stages(self, run_id: str) -> SparkStagesTelemetry:
        telemetry = self._get_run(run_id).telemetry
        return SparkStagesTelemetry(
            run_id=telemetry.run_id,
            stages=telemetry.stage_metrics,
            executor_metrics=telemetry.executor_metrics,
        )

    def get_partition_statistics(self, run_id: str) -> SparkPartitionStatistics:
        return self._get_run(run_id).telemetry.partition_size_stats_bytes

    def get_configuration(self, run_id: str) -> Dict[str, str]:
        return dict(self._get_run(run_id).telemetry.spark_configuration)

    def get_baseline(self, job_id: str, run_id: str) -> SparkRunTelemetry:
        requested_run = self._get_run(run_id).telemetry
        if requested_run.job_id != job_id:
            raise UnknownSparkJobError(
                f"Run '{run_id}' does not belong to Spark job '{job_id}'."
            )

        for fixture_run in self._runs.values():
            if fixture_run.role == "baseline" and fixture_run.telemetry.job_id == job_id:
                return fixture_run.telemetry

        raise UnknownSparkJobError(
            f"No baseline Spark run is available for job '{job_id}'."
        )

    def _get_run(self, run_id: str) -> _FixtureRun:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise UnknownSparkRunError(
                f"Spark run '{run_id}' was not found in the local scenario fixtures."
            ) from exc

    def _load_runs(self) -> Dict[str, _FixtureRun]:
        runs: Dict[str, _FixtureRun] = {}
        for role in ("baseline", "incident"):
            fixture_paths = sorted((self.scenario_dir / role).glob("*.json"))
            if not fixture_paths:
                raise MalformedSparkFixtureError(
                    f"No {role} Spark telemetry fixture found in '{self.scenario_dir}'."
                )
            for fixture_path in fixture_paths:
                telemetry = self._load_telemetry(fixture_path)
                if telemetry.run_id in runs:
                    raise MalformedSparkFixtureError(
                        f"Duplicate Spark run ID '{telemetry.run_id}' in scenario fixtures."
                    )
                runs[telemetry.run_id] = _FixtureRun(role=role, telemetry=telemetry)
        return runs

    @staticmethod
    def _load_telemetry(fixture_path: Path) -> SparkRunTelemetry:
        try:
            with fixture_path.open(encoding="utf-8") as fixture_file:
                payload = json.load(fixture_file)
            return SparkRunTelemetry.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise MalformedSparkFixtureError(
                f"Spark telemetry fixture '{fixture_path}' is malformed."
            ) from exc
