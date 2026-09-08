import json
import subprocess
import sys
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent

def run_cli(*args):
    """Helper to run the CLI and return the CompletedProcess."""
    cmd = [sys.executable, "-m", "app.cli"] + list(args)
    return subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)

def test_cli_human_readable_success():
    res = run_cli("investigate", "spark_performance", "run-customer-aggregation-2026-08-28")
    assert res.returncode == 0
    assert "Incident: Spark performance regression" in res.stdout
    assert "Run ID: run-customer-aggregation-2026-08-28" in res.stdout
    assert "Status: COMPLETED" in res.stdout
    assert "Leading Root Cause: Data skew" in res.stdout
    assert "Key Evidence (Derived Metrics):" in res.stdout
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
