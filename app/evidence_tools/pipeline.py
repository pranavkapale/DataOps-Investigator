from typing import Protocol, List, Optional
from pydantic import BaseModel

class PipelineEvidenceProviderError(Exception):
    """Base exception for pipeline evidence provider errors."""
    pass

class UnknownPipelineRunError(PipelineEvidenceProviderError):
    """Raised when a requested pipeline run is not found."""
    pass

class PipelineRunTelemetry(BaseModel):
    run_id: str
    pipeline_name: str
    status: str
    timestamp: str
    failed_task: Optional[str] = None
    error_message: Optional[str] = None

class PipelineLogTelemetry(BaseModel):
    run_id: str
    task_id: str
    log_content: str

class SchemaField(BaseModel):
    name: str
    type: str

class SchemaTelemetry(BaseModel):
    dataset_id: str
    table_id: str
    fields: List[SchemaField]

class PipelineEvidenceProvider(Protocol):
    def get_run(self, run_id: str) -> PipelineRunTelemetry:
        """Retrieve metadata for a specific pipeline run."""
        ...
        
    def get_logs(self, run_id: str, task_id: str) -> PipelineLogTelemetry:
        """Retrieve logs for a specific task in a pipeline run."""
        ...
        
    def get_current_schema(self, dataset_id: str, table_id: str) -> SchemaTelemetry:
        """Retrieve the current schema for a given table."""
        ...
        
    def get_baseline_schema(self, dataset_id: str, table_id: str) -> SchemaTelemetry:
        """Retrieve the historical/expected schema for a given table."""
        ...

import json
from pathlib import Path

DEFAULT_PIPELINE_SCENARIO_DIR = Path(__file__).resolve().parents[2] / "scenarios" / "pipeline_failure"

class PipelineFixtureEvidenceProvider:
    def __init__(self, scenario_dir: Path | None = None) -> None:
        self.scenario_dir = scenario_dir or DEFAULT_PIPELINE_SCENARIO_DIR
        
    def _get_incident_file(self, run_id: str, filename: str) -> Path:
        """Helper to safely construct and check path."""
        # For this MVP foundation, we assume all failed runs use the single incident fixture,
        # but we do a basic check to make sure it's the expected one, or we just load what's there.
        # In a real multiple-fixture setup, this might be `self.scenario_dir / run_id / ...`.
        # Here we follow the simple structure.
        if run_id != "run-customer-daily-2026-09-12":
            raise UnknownPipelineRunError(f"Unknown run ID: {run_id}")
            
        file_path = self.scenario_dir / "incident" / filename
        if not file_path.exists():
            raise PipelineEvidenceProviderError(f"Fixture file missing: {filename}")
        return file_path

    def get_run(self, run_id: str) -> PipelineRunTelemetry:
        path = self._get_incident_file(run_id, "run.json")
        try:
            with open(path) as f:
                data = json.load(f)
            return PipelineRunTelemetry(**data)
        except Exception as e:
            raise PipelineEvidenceProviderError(f"Failed to load run telemetry: {e}") from e

    def get_logs(self, run_id: str, task_id: str) -> PipelineLogTelemetry:
        # We only have one logs file for the MVP, regardless of task_id
        path = self._get_incident_file(run_id, "logs.txt")
        try:
            with open(path) as f:
                content = f.read()
            return PipelineLogTelemetry(run_id=run_id, task_id=task_id, log_content=content)
        except Exception as e:
            raise PipelineEvidenceProviderError(f"Failed to load logs: {e}") from e

    def get_current_schema(self, dataset_id: str, table_id: str) -> SchemaTelemetry:
        # For MVP, we ignore dataset_id and table_id and just load current_schema.json
        # The run_id isn't passed here, so we assume the fixture is static
        path = self.scenario_dir / "incident" / "current_schema.json"
        if not path.exists():
            raise PipelineEvidenceProviderError("Current schema fixture missing")
        try:
            with open(path) as f:
                data = json.load(f)
            return SchemaTelemetry(**data)
        except Exception as e:
            raise PipelineEvidenceProviderError(f"Failed to load current schema: {e}") from e

    def get_baseline_schema(self, dataset_id: str, table_id: str) -> SchemaTelemetry:
        path = self.scenario_dir / "baseline" / "baseline_schema.json"
        if not path.exists():
            raise PipelineEvidenceProviderError("Baseline schema fixture missing")
        try:
            with open(path) as f:
                data = json.load(f)
            return SchemaTelemetry(**data)
        except Exception as e:
            raise PipelineEvidenceProviderError(f"Failed to load baseline schema: {e}") from e
