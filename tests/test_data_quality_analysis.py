from pathlib import Path
from app.evidence_tools.data_quality import DataQualityFixtureEvidenceProvider
from app.investigation.data_quality_analysis import analyze_data_quality
from app.models import HypothesisStatus

SCENARIO_DIR = Path(__file__).resolve().parent.parent / "scenarios" / "data_quality"

def test_analyze_data_quality():
    provider = DataQualityFixtureEvidenceProvider(SCENARIO_DIR)
    incident_run = provider.get_run("dq-run-2026-09-20")
    baseline_run = provider.get_baseline("finance", "daily_revenue")
    
    hypotheses, evidence = analyze_data_quality(incident_run, baseline_run)
    
    assert len(hypotheses) == 2
    
    # We expect missing partitions (9 out of 24) -> INCOMPLETE_UPSTREAM_DATA SUPPORTED
    incomplete_hypothesis = next((h for h in hypotheses if h.hypothesis_id == "INCOMPLETE_UPSTREAM_DATA"), None)
    assert incomplete_hypothesis is not None
    assert incomplete_hypothesis.status == HypothesisStatus.SUPPORTED
    
    # Genuine business drop should be REJECTED because there is missing data
    business_drop = next((h for h in hypotheses if h.hypothesis_id == "GENUINE_BUSINESS_DROP"), None)
    assert business_drop is not None
    assert business_drop.status == HypothesisStatus.REJECTED
    
    # Evidence validation
    assert len(evidence) == 2
    assert any(e.evidence_id == "ev-dq-01" for e in evidence)
    assert any(e.evidence_id == "ev-dq-02" for e in evidence)
