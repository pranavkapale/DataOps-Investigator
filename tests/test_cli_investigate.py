import json
import subprocess
import sys
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent

import io
from unittest.mock import patch
from app.cli import main

class MockResult:
    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

def run_cli(*args):
    """Helper to run the CLI in-process and return a MockResult."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    returncode = 0
    with patch("sys.argv", ["cli.py"] + list(args)):
        import contextlib
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                main()
            except SystemExit as e:
                returncode = e.code if e.code is not None else 0
            except Exception as e:
                import traceback
                traceback.print_exc(file=stderr)
                returncode = 1
    return MockResult(returncode, stdout.getvalue(), stderr.getvalue())

def test_cli_human_readable_success():
    res = run_cli("investigate", "spark_performance", "run-customer-aggregation-2026-08-28")
    assert res.returncode == 0
    assert "Incident: Spark performance regression" in res.stdout
    assert "Run ID: run-customer-aggregation-2026-08-28" in res.stdout
    assert "Status: COMPLETED" in res.stdout
    assert "Leading Root Cause: Data skew" in res.stdout
    assert "ACTUAL EVIDENCE:" in res.stdout
    assert "skew_ratio" in res.stdout
    assert "runtime_regression_ratio" in res.stdout
    assert "Recommendations:" in res.stdout
    assert "Audit Events:" in res.stdout

def test_cli_json_success():
    res = run_cli("investigate", "spark_performance", "run-customer-aggregation-2026-08-28", "--json")
    assert res.returncode == 0
    
    # Parse output as JSON
    try:
        report = json.loads(res.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(f"Output is not valid JSON: {e}\nOutput: {res.stdout}")
    
    # Check that it represents an InvestigationReport
    assert "incident" in report
    assert "plan" in report
    assert "hypotheses" in report
    assert "evidence" in report
    assert report["incident"]["investigation_type"] == "SPARK_PERFORMANCE"
    assert report["leading_hypothesis_id"] == "DATA_SKEW"

def test_cli_unknown_run_id():
    res = run_cli("investigate", "spark_performance", "nonexistent-run-id")
    assert res.returncode != 0
    assert "Investigation Error:" in res.stderr
    assert "was not found" in res.stderr

def test_cli_unknown_investigation_type():
    res = run_cli("investigate", "unknown_type", "some-run-id")
    assert res.returncode != 0
    assert "Error: Unknown investigation type 'unknown_type'" in res.stderr

def test_existing_cli_intact():
    res = run_cli("-h")
    assert res.returncode == 0
    assert "ask" in res.stdout
    assert "serve" in res.stdout
    assert "build-index" in res.stdout
    assert "investigate" in res.stdout

def test_cli_agentic_human_readable_success(monkeypatch):
    from app.investigation.deterministic_planner import DeterministicMockPlanner
    # Mock the planner instantiation in app.cli
    monkeypatch.setattr("app.cli.InvestigationPlanner", lambda *args, **kwargs: DeterministicMockPlanner())
    
    res = run_cli("investigate", "spark_performance", "run-customer-aggregation-2026-08-28", "--agentic")
    assert res.returncode == 0, f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "Investigation Mode: Agentic (via LLM & MCP)" in res.stdout
    assert "PLANNED TOOLS:" in res.stdout
    assert "- spark_get_job:" in res.stdout
    assert "ACTUAL EVIDENCE:" in res.stdout
    assert "Status: COMPLETED" in res.stdout
    assert "Leading Root Cause: Data skew" in res.stdout

def test_cli_agentic_json_success(monkeypatch):
    from app.investigation.deterministic_planner import DeterministicMockPlanner
    monkeypatch.setattr("app.cli.InvestigationPlanner", lambda *args, **kwargs: DeterministicMockPlanner())
    
    res = run_cli("investigate", "spark_performance", "run-customer-aggregation-2026-08-28", "--agentic", "--json")
    assert res.returncode == 0
    try:
        report = json.loads(res.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(f"Output is not valid JSON: {e}\nOutput: {res.stdout}")
    
    assert report["incident"]["investigation_type"] == "SPARK_PERFORMANCE"
    assert report["leading_hypothesis_id"] == "DATA_SKEW"
    # Ensure plan is populated
    assert len(report["plan"]["steps"]) == 5

def test_cli_agentic_planner_failure(monkeypatch):
    from app.investigation.planner import InvestigationPlannerError
    
    class FailingPlanner:
        def plan_investigation(self, *args, **kwargs):
            raise InvestigationPlannerError("Mock LLM failure")
            
    monkeypatch.setattr("app.cli.InvestigationPlanner", lambda *args, **kwargs: FailingPlanner())
    
    res = run_cli("investigate", "spark_performance", "run-customer-aggregation-2026-08-28", "--agentic")
    assert res.returncode != 0
    assert "Status: FAILED" in res.stdout
    assert "Mock LLM failure" in res.stdout

