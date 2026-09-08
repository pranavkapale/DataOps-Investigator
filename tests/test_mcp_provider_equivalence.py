import ast
from pathlib import Path

from app.evidence_tools.spark import SparkFixtureEvidenceProvider
from app.evidence_tools.spark_mcp import SparkMCPEvidenceProvider
from app.investigation.spark_performance_workflow import SparkPerformanceInvestigationOrchestrator

RUN_ID = "run-customer-aggregation-2026-08-28"
JOB_ID = "customer_aggregation"

def test_mcp_provider_equivalence_job():
    fixture_provider = SparkFixtureEvidenceProvider()
    mcp_provider = SparkMCPEvidenceProvider()
    
    expected = fixture_provider.get_job(RUN_ID)
    actual = mcp_provider.get_job(RUN_ID)
    assert expected == actual

def test_mcp_provider_equivalence_stages():
    fixture_provider = SparkFixtureEvidenceProvider()
    mcp_provider = SparkMCPEvidenceProvider()
    
    expected = fixture_provider.get_stages(RUN_ID)
    actual = mcp_provider.get_stages(RUN_ID)
    assert expected == actual

def test_mcp_provider_equivalence_partition_statistics():
    fixture_provider = SparkFixtureEvidenceProvider()
    mcp_provider = SparkMCPEvidenceProvider()
    
    expected = fixture_provider.get_partition_statistics(RUN_ID)
    actual = mcp_provider.get_partition_statistics(RUN_ID)
    assert expected == actual

def test_mcp_provider_equivalence_configuration():
    fixture_provider = SparkFixtureEvidenceProvider()
    mcp_provider = SparkMCPEvidenceProvider()
    
    expected = fixture_provider.get_configuration(RUN_ID)
    actual = mcp_provider.get_configuration(RUN_ID)
    assert expected == actual

def test_mcp_provider_equivalence_baseline():
    fixture_provider = SparkFixtureEvidenceProvider()
    mcp_provider = SparkMCPEvidenceProvider()
    
    expected = fixture_provider.get_baseline(JOB_ID, RUN_ID)
    actual = mcp_provider.get_baseline(JOB_ID, RUN_ID)
    assert expected == actual

def test_mcp_end_to_end_investigation_equivalence():
    fixture_provider = SparkFixtureEvidenceProvider()
    mcp_provider = SparkMCPEvidenceProvider()
    
    fixture_orchestrator = SparkPerformanceInvestigationOrchestrator(fixture_provider)
    mcp_orchestrator = SparkPerformanceInvestigationOrchestrator(mcp_provider)
    
    expected_report = fixture_orchestrator.investigate(RUN_ID)
    actual_report = mcp_orchestrator.investigate(RUN_ID)
    
    assert actual_report.status == expected_report.status
    assert actual_report.leading_hypothesis_id == expected_report.leading_hypothesis_id
    assert [h.status for h in actual_report.hypotheses] == [h.status for h in expected_report.hypotheses]
    
    # Check derived metrics are equal
    for exp_ev, act_ev in zip(expected_report.evidence, actual_report.evidence):
        assert exp_ev.derived_metric_name == act_ev.derived_metric_name
        assert exp_ev.derived_metric_value == act_ev.derived_metric_value
        
    assert len(actual_report.recommendations) == len(expected_report.recommendations)
    for exp_rec, act_rec in zip(expected_report.recommendations, actual_report.recommendations):
        assert exp_rec.description == act_rec.description
        assert exp_rec.risk_level == act_rec.risk_level

def test_mcp_provider_boundary_safety():
    """Ensure the MCP provider never imports evaluation logic."""
    mcp_file = Path(__file__).resolve().parent.parent / "app" / "evidence_tools" / "spark_mcp.py"
    with open(mcp_file, "r") as f:
        tree = ast.parse(f.read())
        
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                assert "evaluation" not in name.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert "evaluation" not in node.module
                
    content = mcp_file.read_text()
    assert "expected_diagnosis.json" not in content
