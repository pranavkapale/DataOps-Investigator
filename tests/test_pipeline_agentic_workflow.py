import pytest
from pydantic import ValidationError

from app.evidence_tools.pipeline_mcp import PipelineMCPEvidenceProvider
from app.evidence_tools.pipeline import PipelineFixtureEvidenceProvider
from app.investigation.deterministic_planner import DeterministicMockPlanner
from app.investigation.pipeline_agentic_workflow import PipelineAgenticInvestigationOrchestrator, PipelineInvestigationError
from app.investigation.pipeline_failure_workflow import PipelineFailureInvestigationOrchestrator
from app.models import InvestigationStatus

RUN_ID = "run-customer-daily-2026-09-12"

def test_pipeline_agentic_offline_e2e_mcp():
    """Test full agentic pipeline failure investigation using mock planner and real local MCP provider."""
    planner = DeterministicMockPlanner()
    
    provider = PipelineMCPEvidenceProvider()
    orchestrator = PipelineAgenticInvestigationOrchestrator(
        provider=provider,
        planner=planner
    )
    report = orchestrator.investigate(RUN_ID)
    
    assert report.status == InvestigationStatus.COMPLETED
    assert report.leading_hypothesis_id == "SCHEMA_DRIFT"
    assert len(report.plan.steps) == 4
    
    tool_names = [s.description.split(":")[0] for s in report.plan.steps]
    assert "pipeline_get_run" in tool_names
    assert "pipeline_get_logs" in tool_names
    assert "pipeline_get_current_schema" in tool_names
    assert "pipeline_get_baseline_schema" in tool_names
    
    assert provider.session._loop is None

def test_pipeline_agentic_invalid_tool_rejection():
    """Test that unauthorized tools fail the investigation before execution."""
    class BadPlanner(DeterministicMockPlanner):
        def plan_investigation(self, description: str, inv_type: str):
            from app.investigation.planner import InvestigationPlanProposal, PlannedStep
            from app.models import InvestigationType
            return InvestigationPlanProposal(
                investigation_type=InvestigationType.PIPELINE_FAILURE,
                steps=[PlannedStep(tool="invalid_tool", reason="test")]
            )

    planner = BadPlanner()
    provider = PipelineFixtureEvidenceProvider()
    orchestrator = PipelineAgenticInvestigationOrchestrator(provider, planner)
    
    with pytest.raises(PipelineInvestigationError, match="Unknown or unauthorized tool 'invalid_tool'"):
        orchestrator.investigate(RUN_ID)

def test_pipeline_agentic_vs_deterministic_equivalence():
    """Ensure both orchestrators produce the exact same analytical findings."""
    provider = PipelineFixtureEvidenceProvider()
    
    # Deterministic
    det_orchestrator = PipelineFailureInvestigationOrchestrator(provider)
    det_report = det_orchestrator.investigate(RUN_ID)
    
    # Agentic
    agentic_orchestrator = PipelineAgenticInvestigationOrchestrator(provider, DeterministicMockPlanner())
    agent_report = agentic_orchestrator.investigate(RUN_ID)
    
    assert det_report.status == agent_report.status
    assert det_report.leading_hypothesis_id == agent_report.leading_hypothesis_id
    
    # Compare hypotheses mapping
    det_hyp = {h.hypothesis_id: h.status for h in det_report.hypotheses}
    ag_hyp = {h.hypothesis_id: h.status for h in agent_report.hypotheses}
    assert det_hyp == ag_hyp
    
    # Compare evidence
    det_ev = {e.evidence_id: e.observation for e in det_report.evidence}
    ag_ev = {e.evidence_id: e.observation for e in agent_report.evidence}
    assert det_ev == ag_ev

    # Compare recommendations
    det_rec = {r.recommendation_id: r.description for r in det_report.recommendations}
    ag_rec = {r.recommendation_id: r.description for r in agent_report.recommendations}
    assert det_rec == ag_rec
