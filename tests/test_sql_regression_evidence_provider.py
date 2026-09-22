from pathlib import Path
import pytest
from app.evidence_tools.sql_regression import SQLFixtureEvidenceProvider, UnknownSQLQueryError

SCENARIO_DIR = Path(__file__).resolve().parent.parent / "scenarios" / "sql_regression"

def test_sql_fixture_provider_loads_incident():
    provider = SQLFixtureEvidenceProvider(SCENARIO_DIR)
    query = provider.get_query("sql-run-2026-09-20")
    
    assert query.query_id == "sql-run-2026-09-20"
    assert len(query.nodes) > 0
    join_node = next((n for n in query.nodes if n.type == "JOIN"), None)
    assert join_node is not None
    assert join_node.output_rows == 50000000000

def test_sql_fixture_provider_loads_baseline():
    provider = SQLFixtureEvidenceProvider(SCENARIO_DIR)
    query = provider.get_baseline_query()
    
    assert query.query_id == "sql-run-2026-09-19"
    join_node = next((n for n in query.nodes if n.type == "JOIN"), None)
    assert join_node is not None
    assert join_node.output_rows == 10000000

def test_sql_fixture_provider_unknown_query():
    provider = SQLFixtureEvidenceProvider(SCENARIO_DIR)
    with pytest.raises(UnknownSQLQueryError):
        provider.get_query("unknown")
