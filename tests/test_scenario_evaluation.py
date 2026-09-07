import json
import ast
from pathlib import Path

from app.evidence_tools.spark import SparkFixtureEvidenceProvider
from app.investigation.spark_performance_workflow import SparkPerformanceInvestigationOrchestrator
from app.evaluation import ScenarioEvaluator
from app.models import HypothesisStatus

SCENARIO_DIR = Path(__file__).resolve().parents[1] / "scenarios" / "spark_performance"
EVALUATION_PATH = SCENARIO_DIR / "evaluation" / "expected_diagnosis.json"
INCIDENT_RUN_ID = "run-customer-aggregation-2026-08-28"


def load_contract() -> dict:
    with EVALUATION_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def test_scenario_1_investigation_passes_evaluation():
    # Setup the actual workflow
    provider = SparkFixtureEvidenceProvider(SCENARIO_DIR)
    orchestrator = SparkPerformanceInvestigationOrchestrator(provider)
    
    # Run the investigation
    report = orchestrator.investigate(INCIDENT_RUN_ID)
    
    # Evaluate
    contract = load_contract()
    result = ScenarioEvaluator.evaluate(report, contract)
    
    assert result.passed is True
    assert result.root_cause_correct is True
    assert result.evidence_coverage == 1.0
    assert not result.failure_reasons


def test_incorrect_leading_hypothesis_fails_evaluation():
    provider = SparkFixtureEvidenceProvider(SCENARIO_DIR)
    orchestrator = SparkPerformanceInvestigationOrchestrator(provider)
    report = orchestrator.investigate(INCIDENT_RUN_ID)
    
    # Mutate the report to have a wrong leading hypothesis
    report.leading_hypothesis_id = "INPUT_VOLUME_INCREASE"
    
    contract = load_contract()
    result = ScenarioEvaluator.evaluate(report, contract)
    
    assert result.passed is False
    assert result.root_cause_correct is False
    assert "Expected leading hypothesis 'DATA_SKEW'" in result.failure_reasons[0]


def test_missing_required_evidence_fails_evaluation():
    provider = SparkFixtureEvidenceProvider(SCENARIO_DIR)
    orchestrator = SparkPerformanceInvestigationOrchestrator(provider)
    report = orchestrator.investigate(INCIDENT_RUN_ID)
    
    # Mutate report to remove the skew evidence
    report.evidence = [ev for ev in report.evidence if ev.derived_metric_name != "skew_ratio"]
    
    contract = load_contract()
    result = ScenarioEvaluator.evaluate(report, contract)
    
    assert result.passed is False
    assert result.evidence_coverage < 1.0
    assert "Missing expected metric: incident_skew_ratio" in result.failure_reasons


def test_incorrect_metric_value_fails_evaluation():
    provider = SparkFixtureEvidenceProvider(SCENARIO_DIR)
    orchestrator = SparkPerformanceInvestigationOrchestrator(provider)
    report = orchestrator.investigate(INCIDENT_RUN_ID)
    
    # Mutate a metric value to be outside the expected range
    for ev in report.evidence:
        if ev.derived_metric_name == "runtime_regression_ratio":
            ev.derived_metric_value = 1.0  # Should be between 3.5 and 4.5
    
    contract = load_contract()
    result = ScenarioEvaluator.evaluate(report, contract)
    
    assert result.passed is False
    assert result.metrics_checks.get("runtime_regression_ratio") is False
    assert any("outside expected range" in reason for reason in result.failure_reasons)


def test_incorrect_hypothesis_status_fails_evaluation():
    provider = SparkFixtureEvidenceProvider(SCENARIO_DIR)
    orchestrator = SparkPerformanceInvestigationOrchestrator(provider)
    report = orchestrator.investigate(INCIDENT_RUN_ID)
    
    # Mutate a hypothesis status
    for h in report.hypotheses:
        if h.name == "Input volume increase":
            # the contract expects REJECTED
            h.status = HypothesisStatus.SUPPORTED
    
    contract = load_contract()
    result = ScenarioEvaluator.evaluate(report, contract)
    
    assert result.passed is False
    assert result.hypothesis_checks.get("Input volume increase") is False
    assert any("expected 'REJECTED'" in reason for reason in result.failure_reasons)


def test_evaluation_contract_not_imported_by_runtime_code():
    """Ensure the evaluation contract and logic is strictly separated from runtime execution."""
    src_dir = Path(__file__).resolve().parents[1] / "app"
    forbidden_strings = ["expected_diagnosis.json", "app.evaluation", "app/evaluation"]
    
    # Check all files in investigation and evidence_tools
    target_dirs = [src_dir / "investigation", src_dir / "evidence_tools"]
    
    for d in target_dirs:
        for py_file in d.rglob("*.py"):
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()
                for forbidden in forbidden_strings:
                    assert forbidden not in content, f"Forbidden string '{forbidden}' found in {py_file}"
                    
            # Parse AST to ensure no tricky imports
            with open(py_file, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(py_file))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            assert "evaluation" not in alias.name
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            assert "evaluation" not in node.module
