import ast
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from app.investigation.planner import (
    InvestigationPlanner,
    InvestigationPlannerError,
    InvestigationPlanProposal,
    PlannedStep,
)
from app.llm_client import LLMClient

@pytest.fixture
def mock_llm_client():
    return Mock(spec=LLMClient)

@pytest.fixture
def planner(mock_llm_client):
    return InvestigationPlanner(llm_client=mock_llm_client)

def test_valid_spark_performance_plan(planner, mock_llm_client):
    expected_proposal = InvestigationPlanProposal(
        investigation_type="SPARK_PERFORMANCE",
        steps=[
            PlannedStep(tool="spark_get_job", reason="Check metadata"),
            PlannedStep(tool="spark_get_stages", reason="Check stages")
        ]
    )
    mock_llm_client.generate_structured.return_value = expected_proposal
    
    proposal = planner.plan_investigation("Job failed")
    
    assert proposal.investigation_type == "SPARK_PERFORMANCE"
    assert len(proposal.steps) == 2
    assert proposal.steps[0].tool == "spark_get_job"
    assert proposal.steps[1].tool == "spark_get_stages"

def test_invalid_tool_name_rejected(planner, mock_llm_client):
    proposal = InvestigationPlanProposal(
        investigation_type="SPARK_PERFORMANCE",
        steps=[
            PlannedStep(tool="spark_get_job", reason="Check metadata"),
            PlannedStep(tool="spark_get_unknown_thing", reason="Invalid")
        ]
    )
    mock_llm_client.generate_structured.return_value = proposal
    
    with pytest.raises(InvestigationPlannerError, match="unauthorized tool"):
        planner.plan_investigation("Job failed")

def test_duplicate_tools_rejected(planner, mock_llm_client):
    proposal = InvestigationPlanProposal(
        investigation_type="SPARK_PERFORMANCE",
        steps=[
            PlannedStep(tool="spark_get_job", reason="Check metadata"),
            PlannedStep(tool="spark_get_job", reason="Check metadata again")
        ]
    )
    mock_llm_client.generate_structured.return_value = proposal
    
    with pytest.raises(InvestigationPlannerError, match="duplicate tool"):
        planner.plan_investigation("Job failed")

def test_more_than_5_steps_rejected(planner, mock_llm_client):
    # This should fail pydantic validation at the LLMClient layer in a real app,
    # but let's test our manual override just in case.
    proposal = InvestigationPlanProposal(
        investigation_type="SPARK_PERFORMANCE",
        steps=[
            PlannedStep(tool="spark_get_job", reason="1"),
            PlannedStep(tool="spark_get_stages", reason="2"),
            PlannedStep(tool="spark_get_partition_statistics", reason="3"),
            PlannedStep(tool="spark_get_configuration", reason="4"),
            PlannedStep(tool="spark_get_baseline", reason="5"),
        ]
    )
    # forcefully break pydantic boundary for testing
    proposal.steps.append(PlannedStep(tool="spark_get_job", reason="6"))
    
    mock_llm_client.generate_structured.return_value = proposal
    
    with pytest.raises(InvestigationPlannerError, match="maximum limit of 5 steps"):
        planner.plan_investigation("Job failed")

def test_unsupported_investigation_type_rejected():
    with pytest.raises(ValidationError):
        InvestigationPlanProposal(
            investigation_type="UNKNOWN", # type: ignore
            steps=[]
        )

def test_malformed_model_output_rejected_safely(planner, mock_llm_client):
    mock_llm_client.generate_structured.side_effect = Exception("API Error")
    
    with pytest.raises(InvestigationPlannerError, match="Failed to generate plan"):
        planner.plan_investigation("Job failed")

def test_evaluation_contract_never_loaded():
    """Ensure the planner never imports expected_diagnosis.json logic."""
    planner_file = Path(__file__).resolve().parent.parent / "app" / "investigation" / "planner.py"
    with open(planner_file, "r") as f:
        tree = ast.parse(f.read())
        
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                assert "evaluation" not in name.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert "evaluation" not in node.module
                
    content = planner_file.read_text()
    assert "expected_diagnosis.json" not in content
