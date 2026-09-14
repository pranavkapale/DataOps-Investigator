import json
import pytest
from pathlib import Path

from app.models import (
    Evidence,
    EvidenceKind,
    Hypothesis,
    HypothesisStatus,
    Incident,
    InvestigationPlan,
    InvestigationReport,
    InvestigationStatus,
    InvestigationType,
    SourceReference
)
from app.pipeline_evaluation import PipelineFailureEvaluator, PipelineEvaluationResult
from app.evidence_tools.pipeline import PipelineFixtureEvidenceProvider
from app.investigation.pipeline_failure_workflow import PipelineFailureInvestigationOrchestrator


def _mock_report(
    root_cause: str | None = "SCHEMA_DRIFT",
    evidence_ids: list[str] = None,
    observation: str = "Schema drifted fields: customer_id (BIGINT->STRING)",
    status: InvestigationStatus = InvestigationStatus.COMPLETED
) -> InvestigationReport:
    if evidence_ids is None:
        evidence_ids = ["ev-schema-diff", "ev-log-mismatch"]
        
    incident = Incident(
        incident_id="test",
        investigation_type=InvestigationType.PIPELINE_FAILURE,
        title="test",
        description="test",
        created_at="2026-09-12T00:00:00Z",
        source_reference=SourceReference(source="test")
    )
    
    evidence = []
    if "ev-schema-diff" in evidence_ids:
        evidence.append(Evidence(
            evidence_id="ev-schema-diff",
            source="test",
            kind=EvidenceKind.OBSERVED,
            observation=observation,
            timestamp="2026-09-12T00:00:00Z"
        ))
    if "ev-log-mismatch" in evidence_ids:
        evidence.append(Evidence(
            evidence_id="ev-log-mismatch",
            source="test",
            kind=EvidenceKind.OBSERVED,
            observation="test",
            timestamp="2026-09-12T00:00:00Z"
        ))
        
    hypotheses = []
    if root_cause is not None:
        hypotheses.append(Hypothesis(
            hypothesis_id=root_cause,
            name=root_cause,
            description="test",
            rationale="test",
            status=HypothesisStatus.SUPPORTED,
            supporting_evidence_ids=evidence_ids
        ))
        
    return InvestigationReport(
        incident=incident,
        status=status,
        plan=InvestigationPlan(plan_id="test", max_steps=1, steps=[]),
        hypotheses=hypotheses,
        evidence=evidence,
        leading_hypothesis_id=root_cause,
        rejected_hypothesis_ids=[],
        inconclusive_hypothesis_ids=[],
        recommendations=[],
        audit_records=[],
        sources=[]
    )


def test_happy_path_evaluation():
    contract = {
        "root_cause": "SCHEMA_DRIFT",
        "changed_field": "customer_id",
        "old_type": "BIGINT",
        "new_type": "STRING",
        "required_evidence": ["ev-schema-diff", "ev-log-mismatch"]
    }
    report = _mock_report()
    result = PipelineFailureEvaluator.evaluate(report, contract)
    
    assert result.passed is True
    assert result.root_cause_correct is True
    assert result.evidence_coverage == 1.0
    assert result.changed_field_correct is True
    assert result.old_type_correct is True
    assert result.new_type_correct is True
    assert not result.failure_reasons


def test_incorrect_root_cause():
    contract = {"root_cause": "SCHEMA_DRIFT"}
    report = _mock_report(root_cause="UNKNOWN_PIPELINE_FAILURE")
    result = PipelineFailureEvaluator.evaluate(report, contract)
    
    assert result.passed is False
    assert result.root_cause_correct is False
    assert any("Expected leading hypothesis" in r for r in result.failure_reasons)


def test_missing_evidence():
    contract = {"required_evidence": ["ev-schema-diff", "ev-log-mismatch", "ev-missing"]}
    report = _mock_report()
    result = PipelineFailureEvaluator.evaluate(report, contract)
    
    assert result.passed is False
    assert result.evidence_coverage < 1.0
    assert any("Missing required evidence IDs" in r for r in result.failure_reasons)


def test_changed_field_mismatch():
    contract = {"changed_field": "wrong_field"}
    report = _mock_report()
    result = PipelineFailureEvaluator.evaluate(report, contract)
    
    assert result.passed is False
    assert result.changed_field_correct is False
    assert any("Expected changed field" in r for r in result.failure_reasons)


def test_type_mismatch():
    contract = {"changed_field": "customer_id", "old_type": "INT", "new_type": "FLOAT"}
    report = _mock_report()
    result = PipelineFailureEvaluator.evaluate(report, contract)
    
    assert result.passed is False
    assert result.old_type_correct is False
    assert result.new_type_correct is False
    assert any("Expected type transition" in r for r in result.failure_reasons)


def test_insufficient_evidence_semantics():
    contract = {"root_cause": "SCHEMA_DRIFT"}
    report = _mock_report(root_cause=None, status=InvestigationStatus.FAILED)
    result = PipelineFailureEvaluator.evaluate(report, contract)
    
    # An investigation that fails gracefully due to missing evidence 
    # should NOT pass the evaluation if the contract expects a root cause.
    assert result.passed is False
    assert result.root_cause_correct is False


def test_malformed_evaluation_contract(tmp_path):
    (tmp_path / "evaluation").mkdir(parents=True)
    with open(tmp_path / "evaluation" / "expected_diagnosis.json", "w") as f:
        f.write("{malformed json")
        
    with pytest.raises(ValueError, match="Malformed evaluation contract"):
        PipelineFailureEvaluator.load_contract(tmp_path)
        
    with open(tmp_path / "evaluation" / "expected_diagnosis.json", "w") as f:
        pass # empty file, not valid json
        
    with pytest.raises(ValueError, match="Malformed evaluation contract"):
        PipelineFailureEvaluator.load_contract(tmp_path)


def test_missing_evaluation_contract(tmp_path):
    (tmp_path / "evaluation").mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="Evaluation contract not found"):
        PipelineFailureEvaluator.load_contract(tmp_path)


def test_e2e_evaluation_boundary_and_execution():
    # End-to-end evaluation using the real fixture, real orchestrator, and real evaluator.
    # Proves that the runtime doesn't depend on the evaluation contract,
    # but the evaluation contract successfully validates the runtime output.
    
    scenario_dir = Path("scenarios/pipeline_failure")
    contract = PipelineFailureEvaluator.load_contract(scenario_dir)
    
    provider = PipelineFixtureEvidenceProvider(scenario_dir)
    orchestrator = PipelineFailureInvestigationOrchestrator(provider)
    report = orchestrator.investigate("run-customer-daily-2026-09-12")
    
    result = PipelineFailureEvaluator.evaluate(report, contract)
    
    assert result.passed is True
    assert result.root_cause_correct is True
    assert result.changed_field_correct is True
    assert result.old_type_correct is True
    assert result.new_type_correct is True
    assert result.evidence_coverage == 1.0
