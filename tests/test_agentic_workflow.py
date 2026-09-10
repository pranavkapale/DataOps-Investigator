import ast
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.evidence_tools.spark import SparkFixtureEvidenceProvider
from app.investigation.agentic_workflow import SparkAgenticInvestigationOrchestrator
from app.investigation.planner import (
    InvestigationPlanner,
    InvestigationPlannerError,
    InvestigationPlanProposal,
    PlannedStep,
)
from app.investigation.spark_performance_workflow import SparkPerformanceInvestigationOrchestrator
from app.models import HypothesisStatus, InvestigationStatus

RUN_ID = "run-customer-aggregation-2026-08-28"

@pytest.fixture
def mock_planner():
    return Mock(spec=InvestigationPlanner)

@pytest.fixture
def provider():
    return SparkFixtureEvidenceProvider()

@pytest.fixture
def orchestrator(provider, mock_planner):
    return SparkAgenticInvestigationOrchestrator(provider=provider, planner=mock_planner)

def test_agentic_produces_identical_diagnosis(orchestrator, provider, mock_planner):
    mock_planner.plan_investigation.return_value = InvestigationPlanProposal(
        investigation_type="SPARK_PERFORMANCE",
        steps=[
            PlannedStep(tool="spark_get_job", reason="Check metadata"),
            PlannedStep(tool="spark_get_stages", reason="Check stages"),
            PlannedStep(tool="spark_get_partition_statistics", reason="Check partitions"),
            PlannedStep(tool="spark_get_configuration", reason="Check configuration"),
            PlannedStep(tool="spark_get_baseline", reason="Check baseline"),
        ]
    )

    agentic_report = orchestrator.investigate(RUN_ID)

    deterministic_orchestrator = SparkPerformanceInvestigationOrchestrator(provider=provider)
    deterministic_report = deterministic_orchestrator.investigate(RUN_ID)

    # Equivalence assertions
    assert agentic_report.status == deterministic_report.status == InvestigationStatus.COMPLETED
    assert agentic_report.leading_hypothesis_id == deterministic_report.leading_hypothesis_id == "DATA_SKEW"
    
    agentic_statuses = {h.hypothesis_id: h.status for h in agentic_report.hypotheses}
    deterministic_statuses = {h.hypothesis_id: h.status for h in deterministic_report.hypotheses}
    assert agentic_statuses == deterministic_statuses

    agentic_metrics = {ev.derived_metric_name: ev.derived_metric_value for ev in agentic_report.evidence}
    deterministic_metrics = {ev.derived_metric_name: ev.derived_metric_value for ev in deterministic_report.evidence}
    assert agentic_metrics == deterministic_metrics

    assert len(agentic_report.recommendations) == len(deterministic_report.recommendations)

    # Agentic plan should have 5 steps based on the mock
    assert len(agentic_report.plan.steps) == 5

def test_agentic_handles_planner_error_safely(orchestrator, mock_planner):
    mock_planner.plan_investigation.side_effect = InvestigationPlannerError("Exceeded max steps")

    report = orchestrator.investigate(RUN_ID)
    
    assert report.status == InvestigationStatus.FAILED
    assert report.leading_hypothesis_id is None
    assert len(report.hypotheses) == 0
    assert len(report.evidence) == 0
    
    # Audit log should record the failure
    assert any("Planner failed: Exceeded max steps" in r.details for r in report.audit_records)

def test_unknown_tool_fails_safely(orchestrator, mock_planner):
    # This bypasses the pydantic validation in Planner, but tests the orchestrator's safety boundary
    proposal = InvestigationPlanProposal(
        investigation_type="SPARK_PERFORMANCE",
        steps=[]
    )
    # forcefully add unknown tool
    proposal.steps.append(PlannedStep(tool="spark_mutate_job", reason="Hack"))
    mock_planner.plan_investigation.return_value = proposal

    with pytest.raises(Exception, match="Unable to complete agentic Spark investigation"):
        orchestrator.investigate(RUN_ID)

def test_evaluation_contract_never_loaded_by_agentic():
    """Ensure the agentic workflow never imports expected_diagnosis.json logic."""
    workflow_file = Path(__file__).resolve().parent.parent / "app" / "investigation" / "agentic_workflow.py"
    with open(workflow_file, "r") as f:
        tree = ast.parse(f.read())
        
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                assert "evaluation" not in name.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert "evaluation" not in node.module
                
    content = workflow_file.read_text()
    assert "expected_diagnosis.json" not in content
