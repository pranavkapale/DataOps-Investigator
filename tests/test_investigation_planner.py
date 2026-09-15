import ast
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.investigation.planner import (
    InvestigationPlanner,
    InvestigationPlannerError,
    InvestigationPlanProposal,
    PlannedStep,
)
from app.investigation.deterministic_planner import DeterministicMockPlanner
from app.investigation.scenario_config import SCENARIO_CONFIGS
from app.llm_client import LLMClient
from app.models import InvestigationType


@pytest.fixture
def mock_llm_client():
    return Mock(spec=LLMClient)


@pytest.fixture
def planner(mock_llm_client):
    return InvestigationPlanner(llm_client=mock_llm_client)


def test_scenario_configs_exist():
    assert InvestigationType.SPARK_PERFORMANCE in SCENARIO_CONFIGS
    assert InvestigationType.PIPELINE_FAILURE in SCENARIO_CONFIGS
    
    spark_config = SCENARIO_CONFIGS[InvestigationType.SPARK_PERFORMANCE]
    assert len(spark_config.allowed_tools) == 5
    assert len(spark_config.required_tools) == 5
    assert "spark_get_job" in spark_config.allowed_tools

    pipeline_config = SCENARIO_CONFIGS[InvestigationType.PIPELINE_FAILURE]
    assert len(pipeline_config.allowed_tools) == 4
    assert len(pipeline_config.required_tools) == 4
    assert "pipeline_get_run" in pipeline_config.allowed_tools


def test_valid_spark_performance_plan(planner, mock_llm_client):
    expected_proposal = InvestigationPlanProposal(
        investigation_type=InvestigationType.SPARK_PERFORMANCE,
        steps=[
            PlannedStep(tool="spark_get_job", reason="Check metadata"),
            PlannedStep(tool="spark_get_stages", reason="Check stages"),
            PlannedStep(tool="spark_get_partition_statistics", reason="Check partitions"),
            PlannedStep(tool="spark_get_configuration", reason="Check config"),
            PlannedStep(tool="spark_get_baseline", reason="Check baseline")
        ]
    )
    mock_llm_client.generate_structured.return_value = expected_proposal

    proposal = planner.plan_investigation("Job failed", InvestigationType.SPARK_PERFORMANCE)

    assert proposal.investigation_type == InvestigationType.SPARK_PERFORMANCE
    assert len(proposal.steps) == 5
    assert proposal.steps[0].tool == "spark_get_job"


def test_valid_pipeline_failure_plan(planner, mock_llm_client):
    expected_proposal = InvestigationPlanProposal(
        investigation_type=InvestigationType.PIPELINE_FAILURE,
        steps=[
            PlannedStep(tool="pipeline_get_run", reason="Check run"),
            PlannedStep(tool="pipeline_get_logs", reason="Check logs"),
            PlannedStep(tool="pipeline_get_current_schema", reason="Check current schema"),
            PlannedStep(tool="pipeline_get_baseline_schema", reason="Check baseline schema")
        ]
    )
    mock_llm_client.generate_structured.return_value = expected_proposal

    proposal = planner.plan_investigation("Pipeline failed", InvestigationType.PIPELINE_FAILURE)

    assert proposal.investigation_type == InvestigationType.PIPELINE_FAILURE
    assert len(proposal.steps) == 4
    assert proposal.steps[0].tool == "pipeline_get_run"


def test_invalid_tool_name_rejected_spark(planner, mock_llm_client):
    proposal = InvestigationPlanProposal(
        investigation_type=InvestigationType.SPARK_PERFORMANCE,
        steps=[
            PlannedStep(tool="spark_get_job", reason="Check metadata"),
            PlannedStep(tool="spark_get_unknown_thing", reason="Invalid")
        ]
    )
    mock_llm_client.generate_structured.return_value = proposal

    with pytest.raises(InvestigationPlannerError, match="unauthorized tool"):
        planner.plan_investigation("Job failed", InvestigationType.SPARK_PERFORMANCE)


def test_invalid_tool_name_rejected_pipeline(planner, mock_llm_client):
    proposal = InvestigationPlanProposal(
        investigation_type=InvestigationType.PIPELINE_FAILURE,
        steps=[
            PlannedStep(tool="pipeline_get_run", reason="Check run"),
            PlannedStep(tool="pipeline_get_unknown_thing", reason="Invalid")
        ]
    )
    mock_llm_client.generate_structured.return_value = proposal

    with pytest.raises(InvestigationPlannerError, match="unauthorized tool"):
        planner.plan_investigation("Job failed", InvestigationType.PIPELINE_FAILURE)


def test_duplicate_tools_rejected(planner, mock_llm_client):
    proposal = InvestigationPlanProposal(
        investigation_type=InvestigationType.SPARK_PERFORMANCE,
        steps=[
            PlannedStep(tool="spark_get_job", reason="Check metadata"),
            PlannedStep(tool="spark_get_job", reason="Check metadata again")
        ]
    )
    mock_llm_client.generate_structured.return_value = proposal

    with pytest.raises(InvestigationPlannerError, match="duplicate tool"):
        planner.plan_investigation("Job failed", InvestigationType.SPARK_PERFORMANCE)


def test_missing_required_tools_rejected_spark(planner, mock_llm_client):
    proposal = InvestigationPlanProposal(
        investigation_type=InvestigationType.SPARK_PERFORMANCE,
        steps=[
            PlannedStep(tool="spark_get_job", reason="Check metadata"),
            PlannedStep(tool="spark_get_stages", reason="Check stages"),
            PlannedStep(tool="spark_get_partition_statistics", reason="Check partitions"),
            PlannedStep(tool="spark_get_configuration", reason="Check config")
            # Missing spark_get_baseline
        ]
    )
    mock_llm_client.generate_structured.return_value = proposal

    with pytest.raises(InvestigationPlannerError, match="missing required tools: spark_get_baseline"):
        planner.plan_investigation("Job failed", InvestigationType.SPARK_PERFORMANCE)


def test_missing_required_tools_rejected_pipeline(planner, mock_llm_client):
    proposal = InvestigationPlanProposal(
        investigation_type=InvestigationType.PIPELINE_FAILURE,
        steps=[
            PlannedStep(tool="pipeline_get_run", reason="Check run"),
            PlannedStep(tool="pipeline_get_logs", reason="Check logs"),
            PlannedStep(tool="pipeline_get_current_schema", reason="Check current schema")
            # Missing pipeline_get_baseline_schema
        ]
    )
    mock_llm_client.generate_structured.return_value = proposal

    with pytest.raises(InvestigationPlannerError, match="missing required tools: pipeline_get_baseline_schema"):
        planner.plan_investigation("Job failed", InvestigationType.PIPELINE_FAILURE)


def test_more_than_5_steps_rejected(planner, mock_llm_client):
    proposal = InvestigationPlanProposal(
        investigation_type=InvestigationType.SPARK_PERFORMANCE,
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
        planner.plan_investigation("Job failed", InvestigationType.SPARK_PERFORMANCE)


def test_unsupported_investigation_type_rejected():
    with pytest.raises(ValidationError):
        InvestigationPlanProposal(
            investigation_type="UNKNOWN", # type: ignore
            steps=[]
        )


def test_malformed_model_output_rejected_safely(planner, mock_llm_client):
    mock_llm_client.generate_structured.side_effect = Exception("API Error")

    with pytest.raises(InvestigationPlannerError, match="Failed to generate plan"):
        planner.plan_investigation("Job failed", InvestigationType.SPARK_PERFORMANCE)


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


def test_planners_implement_protocol():
    """Ensure both planners structurally implement InvestigationPlannerProtocol."""
    assert hasattr(InvestigationPlanner, "plan_investigation")
    assert hasattr(DeterministicMockPlanner, "plan_investigation")
