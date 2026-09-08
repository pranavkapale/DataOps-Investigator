import ast
import json
from pathlib import Path
from app.mcp_server import (
    spark_get_job,
    spark_get_stages,
    spark_get_partition_statistics,
    spark_get_configuration,
    spark_get_baseline
)

RUN_ID = "run-customer-aggregation-2026-08-28"
JOB_ID = "customer_aggregation"

def test_spark_get_job_success():
    res = spark_get_job(RUN_ID)
    data = json.loads(res)
    assert "error" not in data
    assert data["run_id"] == RUN_ID
    assert data["job_id"] == JOB_ID

def test_spark_get_stages_success():
    res = spark_get_stages(RUN_ID)
    data = json.loads(res)
    assert "error" not in data
    assert "stages" in data
    assert "executor_metrics" in data

def test_spark_get_partition_statistics_success():
    res = spark_get_partition_statistics(RUN_ID)
    data = json.loads(res)
    assert "error" not in data
    assert "median" in data
    assert "largest" in data

def test_spark_get_configuration_success():
    res = spark_get_configuration(RUN_ID)
    data = json.loads(res)
    assert "error" not in data
    assert "spark.sql.shuffle.partitions" in data

def test_spark_get_baseline_success():
    res = spark_get_baseline(JOB_ID, RUN_ID)
    data = json.loads(res)
    assert "error" not in data
    assert data["job_id"] == JOB_ID
    assert data["run_id"] != RUN_ID  # Baseline has a different run ID

def test_unknown_run_returns_error():
    res = spark_get_job("non-existent-run")
    data = json.loads(res)
    assert "error" in data
    assert "was not found" in data["error"]

def test_mcp_server_boundary_safety():
    """Ensure MCP server doesn't cheat by importing evaluation code."""
    mcp_file = Path(__file__).resolve().parent.parent / "app" / "mcp_server.py"
    with open(mcp_file, "r") as f:
        tree = ast.parse(f.read())
        
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                assert "evaluation" not in name.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert "evaluation" not in node.module

    # Also check string literals to ensure expected_diagnosis.json is not mentioned
    content = mcp_file.read_text()
    assert "expected_diagnosis.json" not in content
