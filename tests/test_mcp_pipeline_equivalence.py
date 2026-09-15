import ast
import pytest
from pathlib import Path

from app.evidence_tools.pipeline import (
    PipelineFixtureEvidenceProvider,
    UnknownPipelineRunError,
)
from app.evidence_tools.pipeline_mcp import PipelineMCPEvidenceProvider

RUN_ID = "run-customer-daily-2026-09-12"
TASK_ID = "transform_customer_data"
DATASET_ID = "core"
TABLE_ID = "customer"

def test_mcp_pipeline_equivalence_run():
    fixture_provider = PipelineFixtureEvidenceProvider()
    with PipelineMCPEvidenceProvider() as mcp_provider:
        expected = fixture_provider.get_run(RUN_ID)
        actual = mcp_provider.get_run(RUN_ID)
        assert expected == actual

def test_mcp_pipeline_equivalence_logs():
    fixture_provider = PipelineFixtureEvidenceProvider()
    with PipelineMCPEvidenceProvider() as mcp_provider:
        expected = fixture_provider.get_logs(RUN_ID, TASK_ID)
        actual = mcp_provider.get_logs(RUN_ID, TASK_ID)
        assert expected == actual

def test_mcp_pipeline_equivalence_current_schema():
    fixture_provider = PipelineFixtureEvidenceProvider()
    with PipelineMCPEvidenceProvider() as mcp_provider:
        expected = fixture_provider.get_current_schema(DATASET_ID, TABLE_ID)
        actual = mcp_provider.get_current_schema(DATASET_ID, TABLE_ID)
        assert expected == actual

def test_mcp_pipeline_equivalence_baseline_schema():
    fixture_provider = PipelineFixtureEvidenceProvider()
    with PipelineMCPEvidenceProvider() as mcp_provider:
        expected = fixture_provider.get_baseline_schema(DATASET_ID, TABLE_ID)
        actual = mcp_provider.get_baseline_schema(DATASET_ID, TABLE_ID)
        assert expected == actual

def test_mcp_pipeline_provider_reuse_connection():
    """Test that a single provider instance reuses the connection across multiple calls."""
    with PipelineMCPEvidenceProvider() as mcp_provider:
        loop_before = mcp_provider._loop
        mcp_provider.get_run(RUN_ID)
        mcp_provider.get_logs(RUN_ID, TASK_ID)
        mcp_provider.get_current_schema(DATASET_ID, TABLE_ID)
        mcp_provider.get_baseline_schema(DATASET_ID, TABLE_ID)
        loop_after = mcp_provider._loop

        # Ensure the same event loop was used for all calls
        assert loop_before is loop_after
        assert loop_before.is_running()

def test_mcp_pipeline_unknown_run():
    """Test that unknown runs are properly mapped to UnknownPipelineRunError."""
    with PipelineMCPEvidenceProvider() as mcp_provider:
        with pytest.raises(UnknownPipelineRunError):
            mcp_provider.get_run("invalid-run-id")

def test_mcp_pipeline_boundary_safety():
    """Ensure the MCP provider never imports evaluation logic."""
    mcp_file = Path(__file__).resolve().parent.parent / "app" / "evidence_tools" / "pipeline_mcp.py"
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

def test_mcp_server_boundary_safety():
    """Ensure the MCP server never imports evaluation logic."""
    mcp_server_file = Path(__file__).resolve().parent.parent / "app" / "mcp_server.py"
    with open(mcp_server_file, "r") as f:
        tree = ast.parse(f.read())

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                assert "evaluation" not in name.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert "evaluation" not in node.module

    content = mcp_server_file.read_text()
    assert "expected_diagnosis.json" not in content
