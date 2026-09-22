import pytest
from pathlib import Path
from app.evidence_tools.sql_regression import SQLFixtureEvidenceProvider
from app.evidence_tools.sql_regression_mcp import SQLMCPEvidenceProvider

SCENARIO_DIR = Path(__file__).resolve().parent.parent / "scenarios" / "sql_regression"

def test_mcp_sql_provider_equivalence():
    fixture_provider = SQLFixtureEvidenceProvider(SCENARIO_DIR)
    
    with SQLMCPEvidenceProvider() as mcp_provider:
        fixture_query = fixture_provider.get_query("sql-run-2026-09-20")
        mcp_query = mcp_provider.get_query("sql-run-2026-09-20")
        
        assert fixture_query == mcp_query
        
        fixture_baseline = fixture_provider.get_baseline_query()
        mcp_baseline = mcp_provider.get_baseline_query()
        
        assert fixture_baseline == mcp_baseline
