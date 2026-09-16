import ast
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.pipeline_agentic_evaluation import PipelineAgenticScenarioEvaluator
from app.evaluation_corpus import SCENARIO_2_CORPUS
from app.evidence_tools.pipeline_mcp import PipelineMCPEvidenceProvider
from app.evidence_tools.pipeline import PipelineFixtureEvidenceProvider
from app.investigation.pipeline_agentic_workflow import PipelineAgenticInvestigationOrchestrator, PipelineInvestigationError
from app.models import InvestigationType, SourceReference, InvestigationStatus
from app.investigation.planner import (
    InvestigationPlanner,
    InvestigationPlannerError,
    InvestigationPlanProposal,
    PlannedStep,
)
from app.investigation.pipeline_failure import PipelineFailureAnalyzer

SCENARIO_DIR = Path(__file__).resolve().parents[1] / "scenarios" / "pipeline_failure"
EVALUATION_PATH = SCENARIO_DIR / "evaluation" / "expected_diagnosis.json"
INCIDENT_RUN_ID = "run-customer-daily-2026-09-12"

@pytest.fixture
def mock_planner():
    return Mock(spec=InvestigationPlanner)

@pytest.fixture
def provider():
    return PipelineFixtureEvidenceProvider(SCENARIO_DIR)

@pytest.fixture
def orchestrator(provider, mock_planner):
    return PipelineAgenticInvestigationOrchestrator(provider=provider, planner=mock_planner)

def test_pipeline_agentic_evaluator_valid_plans(orchestrator, mock_planner):
    valid_proposal = InvestigationPlanProposal(
        investigation_type=InvestigationType.PIPELINE_FAILURE,
        steps=[
            PlannedStep(tool="pipeline_get_run", reason="Check metadata"),
            PlannedStep(tool="pipeline_get_logs", reason="Check logs"),
            PlannedStep(tool="pipeline_get_current_schema", reason="Check current schema"),
            PlannedStep(tool="pipeline_get_baseline_schema", reason="Check baseline schema")
        ]
    )
    mock_planner.plan_investigation.return_value = valid_proposal

    evaluator = PipelineAgenticScenarioEvaluator(orchestrator, EVALUATION_PATH)
    metrics = evaluator.evaluate_corpus(INCIDENT_RUN_ID, SCENARIO_2_CORPUS)

    assert metrics.total_cases == 5
    assert metrics.valid_plan_count == 5
    assert metrics.invalid_plan_count == 0
    assert metrics.planner_request_error_count == 0
    assert metrics.plan_validation_error_count == 0
    assert metrics.provider_error_count == 0
    assert metrics.investigation_error_count == 0
    assert metrics.required_tool_coverage == 1.0
    assert metrics.unsafe_tool_count == 0
    assert metrics.duplicate_tool_count == 0
    assert metrics.successful_investigations == 5
    assert metrics.correct_root_cause_count == 5
    assert metrics.root_cause_accuracy == 1.0
    assert metrics.evidence_coverage == 1.0

def test_pipeline_agentic_evaluator_invalid_plans(orchestrator, mock_planner):
    def side_effect(description, investigation_type):
        if "during transformation" in description:
            raise InvestigationPlannerError("Plan includes unauthorized tool: 'spark_get_job'")
        elif "could not be processed" in description:
            raise InvestigationPlannerError("Plan includes duplicate tool: 'pipeline_get_run'")
        elif "failed around" in description:
            raise InvestigationPlannerError("Plan is missing required tool: 'pipeline_get_baseline_schema'")
        elif "type mismatch" in description:
            raise InvestigationPlannerError("Planner failed: 503 Service Unavailable")
        elif "unexpectedly" in description:
            raise InvestigationPlannerError("Plan includes unknown tool: 'pipeline_restart'")
        else:
            return InvestigationPlanProposal(
                investigation_type=InvestigationType.PIPELINE_FAILURE,
                steps=[
                    PlannedStep(tool="pipeline_get_run", reason="Check metadata"),
                    PlannedStep(tool="pipeline_get_logs", reason="Check logs"),
                    PlannedStep(tool="pipeline_get_current_schema", reason="Check current schema"),
                    PlannedStep(tool="pipeline_get_baseline_schema", reason="Check baseline schema")
                ]
            )

    mock_planner.plan_investigation.side_effect = side_effect

    evaluator = PipelineAgenticScenarioEvaluator(orchestrator, EVALUATION_PATH)
    metrics = evaluator.evaluate_corpus(INCIDENT_RUN_ID, SCENARIO_2_CORPUS)

    assert metrics.total_cases == 5
    assert metrics.valid_plan_count == 0
    assert metrics.invalid_plan_count == 5
    
    assert metrics.planner_request_error_count == 1  # the 503 error
    assert metrics.plan_validation_error_count == 4  # unauthorized, duplicate, missing, unknown
    assert metrics.unsafe_tool_count == 1 # unauthorized tool: spark_get_job
    assert metrics.duplicate_tool_count == 1 # duplicate tool

def test_pipeline_agentic_evaluator_provider_error(mock_planner):
    valid_proposal = InvestigationPlanProposal(
        investigation_type=InvestigationType.PIPELINE_FAILURE,
        steps=[
            PlannedStep(tool="pipeline_get_run", reason="Check metadata"),
            PlannedStep(tool="pipeline_get_logs", reason="Check logs"),
            PlannedStep(tool="pipeline_get_current_schema", reason="Check current schema"),
            PlannedStep(tool="pipeline_get_baseline_schema", reason="Check baseline schema")
        ]
    )
    mock_planner.plan_investigation.return_value = valid_proposal

    # Mock provider to raise PipelineInvestigationError during tool call
    provider = Mock(spec=PipelineFixtureEvidenceProvider)
    provider.get_run.side_effect = PipelineInvestigationError("Provider connection failed")
    
    orchestrator = PipelineAgenticInvestigationOrchestrator(provider, mock_planner)

    evaluator = PipelineAgenticScenarioEvaluator(orchestrator, EVALUATION_PATH)
    # Just run 1 case
    metrics = evaluator.evaluate_corpus(INCIDENT_RUN_ID, SCENARIO_2_CORPUS[:1])

    assert metrics.total_cases == 1
    assert metrics.provider_error_count == 1
    assert metrics.valid_plan_count == 0

def test_pipeline_evaluation_contract_not_imported_by_agentic_workflow():
    src_dir = Path(__file__).resolve().parents[1] / "app"
    forbidden_strings = ["expected_diagnosis.json", "app.evaluation", "app/evaluation", "app.pipeline_evaluation"]
    
    target_dirs = [src_dir / "investigation", src_dir / "evidence_tools"]
    
    for d in target_dirs:
        for py_file in d.rglob("*.py"):
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()
                for forbidden in forbidden_strings:
                    # Ignore the evaluator itself because it's allowed to import the contract/evaluator
                    if "agentic_evaluation" in py_file.name:
                        continue
                    assert forbidden not in content, f"Forbidden string '{forbidden}' found in {py_file}"
                    
            with open(py_file, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(py_file))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if "agentic_evaluation" not in py_file.name:
                                assert "evaluation" not in alias.name
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            if "agentic_evaluation" not in py_file.name:
                                assert "evaluation" not in node.module
