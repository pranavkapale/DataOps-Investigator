from pathlib import Path
from app.evidence_tools.sql_regression import SQLFixtureEvidenceProvider
from app.investigation.sql_regression_analysis import analyze_sql_regression
from app.models import HypothesisStatus

SCENARIO_DIR = Path(__file__).resolve().parent.parent / "scenarios" / "sql_regression"

def test_analyze_sql_regression():
    provider = SQLFixtureEvidenceProvider(SCENARIO_DIR)
    incident_run = provider.get_query("sql-run-2026-09-20")
    baseline_run = provider.get_baseline_query()
    
    hypotheses, evidence = analyze_sql_regression(incident_run, baseline_run)
    
    assert len(hypotheses) == 1
    
    # We expect JOIN cardinality explosion -> SUPPORTED
    explosion_hypothesis = next((h for h in hypotheses if h.hypothesis_id == "JOIN_CARDINALITY_EXPLOSION"), None)
    assert explosion_hypothesis is not None
    assert explosion_hypothesis.status == HypothesisStatus.SUPPORTED
    
    # Evidence validation
    assert len(evidence) == 1
    assert evidence[0].evidence_id == "ev-sql-01"
