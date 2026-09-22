import pytest
from pathlib import Path
from app.evidence_tools.data_quality import DataQualityFixtureEvidenceProvider
from app.evidence_tools.data_quality_mcp import DataQualityMCPEvidenceProvider

SCENARIO_DIR = Path(__file__).resolve().parent.parent / "scenarios" / "data_quality"

def test_mcp_dq_provider_equivalence():
    fixture_provider = DataQualityFixtureEvidenceProvider(SCENARIO_DIR)
    
    with DataQualityMCPEvidenceProvider() as mcp_provider:
        fixture_run = fixture_provider.get_run("dq-run-2026-09-20")
        mcp_run = mcp_provider.get_run("dq-run-2026-09-20")
        
        assert fixture_run == mcp_run
        
        fixture_baseline = fixture_provider.get_baseline("finance", "daily_revenue")
        mcp_baseline = mcp_provider.get_baseline("finance", "daily_revenue")
        
        assert fixture_baseline == mcp_baseline
