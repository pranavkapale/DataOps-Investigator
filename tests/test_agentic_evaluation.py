import ast
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.agentic_evaluation import AgenticScenarioEvaluator
from app.evaluation_corpus import SCENARIO_1_CORPUS
from app.evidence_tools.spark import SparkFixtureEvidenceProvider
from app.investigation.agentic_workflow import SparkAgenticInvestigationOrchestrator
from app.investigation.planner import (
    InvestigationPlanner,
    InvestigationPlannerError,
    InvestigationPlanProposal,
    PlannedStep,
)

SCENARIO_DIR = Path(__file__).resolve().parents[1] / "scenarios" / "spark_performance"
EVALUATION_PATH = SCENARIO_DIR / "evaluation" / "expected_diagnosis.json"
INCIDENT_RUN_ID = "run-customer-aggregation-2026-08-28"

@pytest.fixture
def mock_planner():
    return Mock(spec=InvestigationPlanner)

@pytest.fixture
def provider():
    return SparkFixtureEvidenceProvider(SCENARIO_DIR)

@pytest.fixture
def orchestrator(provider, mock_planner):
    return SparkAgenticInvestigationOrchestrator(provider=provider, planner=mock_planner)

def test_agentic_evaluator_valid_plans(orchestrator, mock_planner):
    # Setup mock to always return a valid plan
    valid_proposal = InvestigationPlanProposal(
        investigation_type="SPARK_PERFORMANCE",
        steps=[
            PlannedStep(tool="spark_get_job", reason="Check metadata"),
            PlannedStep(tool="spark_get_stages", reason="Check stages"),
            PlannedStep(tool="spark_get_partition_statistics", reason="Check partitions"),
            PlannedStep(tool="spark_get_configuration", reason="Check config"),
            PlannedStep(tool="spark_get_baseline", reason="Check baseline")
        ]
    )
    mock_planner.plan_investigation.return_value = valid_proposal

    evaluator = AgenticScenarioEvaluator(orchestrator, EVALUATION_PATH)
    metrics = evaluator.evaluate_corpus(INCIDENT_RUN_ID, SCENARIO_1_CORPUS)

    assert metrics.total_cases == 5
    assert metrics.valid_plan_count == 5
    assert metrics.invalid_plan_count == 0
    assert metrics.required_tool_coverage == 1.0
    assert metrics.unsafe_tool_count == 0
    assert metrics.duplicate_tool_count == 0
    assert metrics.successful_investigations == 5
    assert metrics.correct_root_cause_count == 5
    assert metrics.root_cause_accuracy == 1.0
    assert metrics.evidence_coverage == 1.0

def test_agentic_evaluator_invalid_plans(orchestrator, mock_planner):
    # Setup mock to simulate various failures
    def side_effect(description):
        if "longer" in description:
            raise InvestigationPlannerError("Plan includes unauthorized tool: 'spark_mutate_job'")
        elif "slower" in description:
            raise InvestigationPlannerError("Plan includes duplicate tool: 'spark_get_job'")
        elif "increased" in description:
            raise InvestigationPlannerError("Plan is missing required tools: spark_get_baseline")
        else:
            # Fallback valid
            return InvestigationPlanProposal(
                investigation_type="SPARK_PERFORMANCE",
                steps=[
                    PlannedStep(tool="spark_get_job", reason="Check metadata"),
                    PlannedStep(tool="spark_get_stages", reason="Check stages"),
                    PlannedStep(tool="spark_get_partition_statistics", reason="Check partitions"),
                    PlannedStep(tool="spark_get_configuration", reason="Check config"),
                    PlannedStep(tool="spark_get_baseline", reason="Check baseline")
                ]
            )

    mock_planner.plan_investigation.side_effect = side_effect

    evaluator = AgenticScenarioEvaluator(orchestrator, EVALUATION_PATH)
    metrics = evaluator.evaluate_corpus(INCIDENT_RUN_ID, SCENARIO_1_CORPUS)

    assert metrics.total_cases == 5
    assert metrics.valid_plan_count == 2
    assert metrics.invalid_plan_count == 3
    assert metrics.required_tool_coverage == 2.0 / 5.0
    assert metrics.unsafe_tool_count == 1
    assert metrics.duplicate_tool_count == 1
    assert metrics.successful_investigations == 2
    assert metrics.root_cause_accuracy == 1.0
    assert metrics.evidence_coverage == 1.0

def test_evaluation_contract_not_imported_by_agentic_workflow():
    src_dir = Path(__file__).resolve().parents[1] / "app"
    forbidden_strings = ["expected_diagnosis.json", "app.evaluation", "app/evaluation"]
    
    target_dirs = [src_dir / "investigation", src_dir / "evidence_tools"]
    
    for d in target_dirs:
        for py_file in d.rglob("*.py"):
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()
                for forbidden in forbidden_strings:
                    assert forbidden not in content, f"Forbidden string '{forbidden}' found in {py_file}"
                    
            with open(py_file, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(py_file))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            assert "evaluation" not in alias.name
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            assert "evaluation" not in node.module
