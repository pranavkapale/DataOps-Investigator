import pytest
from app.evidence_tools.pipeline import (
    PipelineFixtureEvidenceProvider,
    PipelineRunTelemetry,
    PipelineLogTelemetry,
    SchemaTelemetry,
    SchemaField,
    PipelineEvidenceProviderError,
)
from app.investigation.pipeline_failure import PipelineFailureAnalyzer
from app.models import HypothesisStatus, InvestigationStatus

class MockPipelineEvidenceProvider:
    def __init__(self, run: PipelineRunTelemetry, logs: PipelineLogTelemetry, current: SchemaTelemetry, baseline: SchemaTelemetry):
        self._run = run
        self._logs = logs
        self._current = current
        self._baseline = baseline

    def get_run(self, run_id: str) -> PipelineRunTelemetry:
        if self._run is None:
            raise PipelineEvidenceProviderError("Mock error")
        return self._run

    def get_logs(self, run_id: str, task_id: str) -> PipelineLogTelemetry:
        if self._logs is None:
            raise PipelineEvidenceProviderError("Mock error")
        return self._logs

    def get_current_schema(self, dataset: str, table: str) -> SchemaTelemetry:
        if self._current is None:
            raise PipelineEvidenceProviderError("Mock error")
        return self._current

    def get_baseline_schema(self, dataset: str, table: str) -> SchemaTelemetry:
        if self._baseline is None:
            raise PipelineEvidenceProviderError("Mock error")
        return self._baseline


def _create_mock_provider(
    log_content="Type mismatch in field 'customer_id'",
    current_type="STRING",
    baseline_type="BIGINT",
    missing_baseline=False,
    missing_current=False,
    missing_logs=False,
    missing_run=False
):
    run = PipelineRunTelemetry(
        run_id="run-1", pipeline_name="test", status="FAILED", timestamp="2026-09-12T00:00:00Z", failed_task="task1"
    ) if not missing_run else None
    
    logs = PipelineLogTelemetry(
        run_id="run-1", task_id="task1", log_content=log_content
    ) if not missing_logs else None
    
    current = SchemaTelemetry(
        dataset_id="test", table_id="test", fields=[SchemaField(name="customer_id", type=current_type)]
    ) if not missing_current else None
    
    baseline = SchemaTelemetry(
        dataset_id="test", table_id="test", fields=[SchemaField(name="customer_id", type=baseline_type)]
    ) if not missing_baseline else None
    
    return MockPipelineEvidenceProvider(run, logs, current, baseline)


def test_fixture_identifies_schema_drift():
    # 1. Current fixture correctly identifies schema drift
    # 10. No hardcoded expected root-cause value is read from the evaluation directory.
    provider = PipelineFixtureEvidenceProvider()
    analyzer = PipelineFailureAnalyzer()
    findings = analyzer.analyze(provider, "run-customer-daily-2026-09-12")
    
    assert findings.status == InvestigationStatus.COMPLETED
    assert findings.leading_hypothesis_id == "SCHEMA_DRIFT"
    
    schema_drift_hyp = next(h for h in findings.hypotheses if h.hypothesis_id == "SCHEMA_DRIFT")
    assert schema_drift_hyp.status == HypothesisStatus.SUPPORTED
    
def test_changed_field_identified():
    # 2. Changed field and old/new types are identified
    provider = _create_mock_provider(current_type="STRING", baseline_type="BIGINT")
    analyzer = PipelineFailureAnalyzer()
    findings = analyzer.analyze(provider, "run-1")
    
    assert findings.metrics.schema_changed is True
    assert "customer_id" in findings.metrics.changed_fields
    assert findings.metrics.changed_fields["customer_id"].baseline_type == "BIGINT"
    assert findings.metrics.changed_fields["customer_id"].current_type == "STRING"

def test_matching_log_strengthens_conclusion():
    # 3. Matching log mismatch strengthens the schema-drift conclusion
    provider = _create_mock_provider(
        log_content="Type mismatch in field 'customer_id'. Expected BIGINT, got STRING."
    )
    analyzer = PipelineFailureAnalyzer()
    findings = analyzer.analyze(provider, "run-1")
    assert findings.metrics.log_mismatch_corresponds_to_schema_diff is True
    schema_drift = next(h for h in findings.hypotheses if h.hypothesis_id == "SCHEMA_DRIFT")
    assert schema_drift.status == HypothesisStatus.SUPPORTED

def test_schema_changed_but_unrelated_log():
    # 4. Schema changed but log provides unrelated failure → schema drift should not automatically be supported
    provider = _create_mock_provider(
        log_content="Timeout Error: Connection refused to database."
    )
    analyzer = PipelineFailureAnalyzer()
    findings = analyzer.analyze(provider, "run-1")
    
    assert findings.metrics.schema_changed is True
    assert findings.metrics.log_indicates_schema_mismatch is False
    assert findings.metrics.log_mismatch_corresponds_to_schema_diff is False
    
    schema_drift = next(h for h in findings.hypotheses if h.hypothesis_id == "SCHEMA_DRIFT")
    assert schema_drift.status == HypothesisStatus.REJECTED

def test_log_mismatch_but_schemas_match():
    # 5. Log reports type mismatch but schemas do not confirm it → inconclusive/insufficient evidence
    provider = _create_mock_provider(
        log_content="Type mismatch in field 'customer_id'",
        current_type="BIGINT",
        baseline_type="BIGINT"  # Schemas match
    )
    analyzer = PipelineFailureAnalyzer()
    findings = analyzer.analyze(provider, "run-1")
    
    assert findings.metrics.schema_changed is False
    assert findings.metrics.log_indicates_schema_mismatch is True
    assert findings.metrics.log_mismatch_corresponds_to_schema_diff is False
    
    schema_drift = next(h for h in findings.hypotheses if h.hypothesis_id == "SCHEMA_DRIFT")
    assert schema_drift.status == HypothesisStatus.REJECTED

def test_missing_baseline_schema():
    # 6. Missing baseline schema
    provider = _create_mock_provider(missing_baseline=True)
    analyzer = PipelineFailureAnalyzer()
    findings = analyzer.analyze(provider, "run-1")
    
    assert findings.status == InvestigationStatus.FAILED
    assert findings.hypotheses[0].hypothesis_id == "INSUFFICIENT_EVIDENCE"

def test_missing_current_schema():
    # 7. Missing current schema
    provider = _create_mock_provider(missing_current=True)
    analyzer = PipelineFailureAnalyzer()
    findings = analyzer.analyze(provider, "run-1")
    
    assert findings.status == InvestigationStatus.FAILED
    assert findings.hypotheses[0].hypothesis_id == "INSUFFICIENT_EVIDENCE"

def test_malformed_telemetry():
    # 8. Malformed telemetry (Missing run)
    provider = _create_mock_provider(missing_run=True)
    analyzer = PipelineFailureAnalyzer()
    findings = analyzer.analyze(provider, "run-1")
    
    assert findings.status == InvestigationStatus.FAILED
    assert findings.hypotheses[0].hypothesis_id == "INSUFFICIENT_EVIDENCE"

def test_no_schema_differences():
    # 9. No schema differences
    provider = _create_mock_provider(
        log_content="Everything looks fine",
        current_type="BIGINT",
        baseline_type="BIGINT"
    )
    analyzer = PipelineFailureAnalyzer()
    findings = analyzer.analyze(provider, "run-1")
    
    assert findings.metrics.schema_changed is False
    schema_drift = next(h for h in findings.hypotheses if h.hypothesis_id == "SCHEMA_DRIFT")
    assert schema_drift.status == HypothesisStatus.REJECTED
