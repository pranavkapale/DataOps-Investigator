import pytest
from app.models import InvestigationType

def test_investigation_type_enum():
    assert InvestigationType.SPARK_PERFORMANCE == "SPARK_PERFORMANCE"
    assert InvestigationType.PIPELINE_FAILURE == "PIPELINE_FAILURE"
    assert len(InvestigationType) == 2

import json
from pathlib import Path
from app.evidence_tools.pipeline import (
    PipelineFixtureEvidenceProvider,
    UnknownPipelineRunError,
    PipelineEvidenceProviderError,
    PipelineRunTelemetry,
    PipelineLogTelemetry,
    SchemaTelemetry
)

def test_pipeline_fixtures_exist():
    provider = PipelineFixtureEvidenceProvider()
    assert (provider.scenario_dir / "incident" / "run.json").exists()
    assert (provider.scenario_dir / "incident" / "logs.txt").exists()
    assert (provider.scenario_dir / "incident" / "current_schema.json").exists()
    assert (provider.scenario_dir / "baseline" / "baseline_schema.json").exists()
    assert (provider.scenario_dir / "evaluation" / "expected_diagnosis.json").exists()

def test_schema_fixtures_are_different():
    provider = PipelineFixtureEvidenceProvider()
    with open(provider.scenario_dir / "incident" / "current_schema.json") as f:
        current = json.load(f)
    with open(provider.scenario_dir / "baseline" / "baseline_schema.json") as f:
        baseline = json.load(f)
    assert current != baseline
    assert current["fields"][0]["type"] == "STRING"
    assert baseline["fields"][0]["type"] == "BIGINT"

def test_pipeline_get_run():
    provider = PipelineFixtureEvidenceProvider()
    run = provider.get_run("run-customer-daily-2026-09-12")
    assert isinstance(run, PipelineRunTelemetry)
    assert run.run_id == "run-customer-daily-2026-09-12"
    assert run.status == "FAILED"

def test_pipeline_get_logs():
    provider = PipelineFixtureEvidenceProvider()
    logs = provider.get_logs("run-customer-daily-2026-09-12", "transform_customer_data")
    assert isinstance(logs, PipelineLogTelemetry)
    assert "Type mismatch" in logs.log_content

def test_pipeline_get_schemas():
    provider = PipelineFixtureEvidenceProvider()
    current = provider.get_current_schema("production_dataset", "customer_data")
    assert isinstance(current, SchemaTelemetry)
    assert current.fields[0].type == "STRING"
    
    baseline = provider.get_baseline_schema("production_dataset", "customer_data")
    assert isinstance(baseline, SchemaTelemetry)
    assert baseline.fields[0].type == "BIGINT"

def test_unknown_run_id():
    provider = PipelineFixtureEvidenceProvider()
    with pytest.raises(UnknownPipelineRunError):
        provider.get_run("invalid-run-id")

def test_malformed_fixture(tmp_path):
    # Create a temporary broken provider
    (tmp_path / "incident").mkdir()
    with open(tmp_path / "incident" / "run.json", "w") as f:
        f.write("{ invalid json")
    
    provider = PipelineFixtureEvidenceProvider(scenario_dir=tmp_path)
    with pytest.raises(PipelineEvidenceProviderError, match="Failed to load run telemetry"):
        provider.get_run("run-customer-daily-2026-09-12")

def test_evaluation_boundary():
    # Runtime provider must NOT read the evaluation contract
    provider = PipelineFixtureEvidenceProvider()
    
    # We ensure none of the returned models have a root_cause field
    run = provider.get_run("run-customer-daily-2026-09-12")
    assert not hasattr(run, "expected_root_cause")
    assert not hasattr(run, "root_cause")

