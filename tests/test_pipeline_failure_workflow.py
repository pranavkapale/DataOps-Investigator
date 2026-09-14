import pytest

from app.evidence_tools.pipeline import (
    PipelineFixtureEvidenceProvider,
    PipelineEvidenceProviderError,
    UnknownPipelineRunError
)
from app.investigation.pipeline_failure_workflow import (
    PipelineFailureInvestigationOrchestrator,
    PipelineInvestigationError
)
from app.models import (
    AuditEventType,
    HypothesisStatus,
    InvestigationStatus,
    InvestigationType
)

def test_pipeline_workflow_happy_path():
    # 1. Happy-path fixture produces SCHEMA_DRIFT.
    provider = PipelineFixtureEvidenceProvider()
    orchestrator = PipelineFailureInvestigationOrchestrator(provider)
    
    report = orchestrator.investigate("run-customer-daily-2026-09-12")
    
    # Check overall investigation metadata
    assert report.incident.investigation_type == InvestigationType.PIPELINE_FAILURE
    assert report.status == InvestigationStatus.COMPLETED
    assert report.leading_hypothesis_id == "SCHEMA_DRIFT"
    
    # 2. Report contains the expected evidence.
    assert len(report.evidence) == 2
    evidence_ids = {ev.evidence_id for ev in report.evidence}
    assert "ev-schema-diff" in evidence_ids
    assert "ev-log-mismatch" in evidence_ids
    
    # 3. Hypothesis evidence references resolve correctly.
    schema_drift_hyp = next(h for h in report.hypotheses if h.hypothesis_id == "SCHEMA_DRIFT")
    assert schema_drift_hyp.status == HypothesisStatus.SUPPORTED
    for ev_id in schema_drift_hyp.supporting_evidence_ids:
        assert ev_id in evidence_ids
        
    # 4. Plan is bounded and deterministic.
    assert report.plan is not None
    assert len(report.plan.steps) == 6
    assert report.plan.steps[0].description == "Retrieve pipeline run metadata."
    
    # 5. Audit trail exists and follows sensible lifecycle ordering.
    audit_events = [record.event_type for record in report.audit_records]
    expected_order = [
        AuditEventType.INVESTIGATION_STARTED,
        AuditEventType.PLAN_CREATED,
        AuditEventType.EVIDENCE_COLLECTED,
        AuditEventType.EVIDENCE_COLLECTED,
        AuditEventType.ANALYSIS_COMPLETED,
        AuditEventType.HYPOTHESIS_EVALUATED,
        AuditEventType.REPORT_COMPLETED,
        AuditEventType.INVESTIGATION_COMPLETED,
    ]
    assert audit_events == expected_order
    
    # 9. Workflow does not read the evaluation contract.
    # The fixture provider does not read the evaluation directory, and the orchestrator doesn't either.
    assert not hasattr(report, "expected_root_cause")
    assert not hasattr(report.incident, "root_cause")
    
    # Verify recommendations exist
    assert len(report.recommendations) == 1
    assert report.recommendations[0].recommendation_id == "rec-validate-schema-contract"


def test_workflow_unknown_run():
    # 6. Unknown run is handled cleanly.
    provider = PipelineFixtureEvidenceProvider()
    orchestrator = PipelineFailureInvestigationOrchestrator(provider)
    
    with pytest.raises(PipelineInvestigationError, match="Unable to complete Pipeline investigation"):
        orchestrator.investigate("unknown-run-id")


def test_workflow_missing_schema(tmp_path):
    # 7. Missing baseline/current schema is handled safely.
    (tmp_path / "incident").mkdir(parents=True)
    with open(tmp_path / "incident" / "run.json", "w") as f:
        f.write('{"run_id": "run-customer-daily-2026-09-12", "pipeline_name": "test", "status": "FAILED", "timestamp": "2026-09-12T00:00:00Z"}')
    # Intentionally omitted schemas and logs
    
    provider = PipelineFixtureEvidenceProvider(scenario_dir=tmp_path)
    orchestrator = PipelineFailureInvestigationOrchestrator(provider)
    
    report = orchestrator.investigate("run-customer-daily-2026-09-12")
    
    # The orchestrator swallows insufficient evidence and returns FAILED investigation status
    assert report.status == InvestigationStatus.FAILED
    assert len(report.hypotheses) == 1
    assert report.hypotheses[0].hypothesis_id == "INSUFFICIENT_EVIDENCE"


def test_workflow_unrelated_failure(tmp_path):
    # 8. Unrelated failure does not produce SCHEMA_DRIFT.
    (tmp_path / "incident").mkdir(parents=True)
    (tmp_path / "baseline").mkdir(parents=True)
    
    with open(tmp_path / "incident" / "run.json", "w") as f:
        f.write('{"run_id": "run-customer-daily-2026-09-12", "pipeline_name": "test", "status": "FAILED", "timestamp": "2026-09-12T00:00:00Z"}')
        
    with open(tmp_path / "incident" / "logs.txt", "w") as f:
        f.write('OOM Killed: executor ran out of memory.')
        
    with open(tmp_path / "incident" / "current_schema.json", "w") as f:
        f.write('{"dataset_id": "test", "table_id": "test", "fields": [{"name": "id", "type": "STRING"}]}')
        
    with open(tmp_path / "baseline" / "baseline_schema.json", "w") as f:
        f.write('{"dataset_id": "test", "table_id": "test", "fields": [{"name": "id", "type": "STRING"}]}')
        
    provider = PipelineFixtureEvidenceProvider(scenario_dir=tmp_path)
    orchestrator = PipelineFailureInvestigationOrchestrator(provider)
    
    report = orchestrator.investigate("run-customer-daily-2026-09-12")
    
    assert report.status == InvestigationStatus.COMPLETED
    assert report.leading_hypothesis_id is None
    
    schema_drift_hyp = next(h for h in report.hypotheses if h.hypothesis_id == "SCHEMA_DRIFT")
    assert schema_drift_hyp.status == HypothesisStatus.REJECTED
