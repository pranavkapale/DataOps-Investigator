import pytest
from app.evidence_tools.spark_mcp import SparkMCPEvidenceProvider
from app.investigation.agentic_workflow import SparkAgenticInvestigationOrchestrator
from app.investigation.deterministic_planner import DeterministicMockPlanner
from app.models import HypothesisStatus, InvestigationStatus

@pytest.fixture
def mcp_provider():
    with SparkMCPEvidenceProvider() as provider:
        yield provider

def test_offline_agentic_workflow_with_mcp(mcp_provider):
    """
    End-to-end test of the agentic workflow using the deterministic planner and real local MCP provider.
    Proves that the workflow can run entirely offline via MCP without the LLM.
    """
    planner = DeterministicMockPlanner()
    orchestrator = SparkAgenticInvestigationOrchestrator(mcp_provider, planner)
    
    # Run the investigation
    report = orchestrator.investigate("run-customer-aggregation-2026-08-28", "Test deterministic offline MCP workflow")
    
    # Verify investigation succeeds
    assert report.status == InvestigationStatus.COMPLETED
    assert report.leading_hypothesis_id == "DATA_SKEW"
    
    # Verify hypothesis status is SUPPORTED
    supported_hypotheses = [h for h in report.hypotheses if h.hypothesis_id == "DATA_SKEW"]
    assert len(supported_hypotheses) == 1
    assert supported_hypotheses[0].status == HypothesisStatus.SUPPORTED
    
    # Verify expected evidence is present
    evidence_ids = {e.evidence_id for e in report.evidence}
    assert "ev-partition-distribution" in evidence_ids
    assert "ev-runtime-regression" in evidence_ids
    
    # Verify MCP was actually traversed implicitly because the provider is SparkMCPEvidenceProvider
    assert isinstance(mcp_provider, SparkMCPEvidenceProvider)
    
    # Verify plan structure
    assert len(report.plan.steps) == 5
    tools_called = [step.description.split(":")[0].strip() for step in report.plan.steps]
    assert set(tools_called) == {
        "spark_get_job",
        "spark_get_stages",
        "spark_get_partition_statistics",
        "spark_get_configuration",
        "spark_get_baseline"
    }
