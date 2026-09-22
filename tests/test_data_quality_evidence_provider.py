from pathlib import Path
import pytest
from app.evidence_tools.data_quality import DataQualityFixtureEvidenceProvider, UnknownDataQualityRunError

SCENARIO_DIR = Path(__file__).resolve().parent.parent / "scenarios" / "data_quality"

def test_dq_fixture_provider_loads_incident():
    provider = DataQualityFixtureEvidenceProvider(SCENARIO_DIR)
    run = provider.get_run("dq-run-2026-09-20")
    
    assert run.run_id == "dq-run-2026-09-20"
    assert run.dataset == "finance"
    assert run.table == "daily_revenue"
    assert run.metrics.observed_partition_count == 15
    assert run.metrics.expected_partition_count == 24

def test_dq_fixture_provider_loads_baseline():
    provider = DataQualityFixtureEvidenceProvider(SCENARIO_DIR)
    run = provider.get_baseline("sales", "daily_revenue")
    
    assert run.dataset == "finance"
    assert run.table == "daily_revenue"
    assert run.metrics.observed_partition_count == 24
    assert run.metrics.expected_partition_count == 24

def test_dq_fixture_provider_unknown_run():
    provider = DataQualityFixtureEvidenceProvider(SCENARIO_DIR)
    with pytest.raises(UnknownDataQualityRunError):
        provider.get_run("unknown")
