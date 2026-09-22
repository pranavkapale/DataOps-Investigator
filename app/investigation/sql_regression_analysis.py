from app.evidence_tools.sql_regression import SQLQueryRun
from app.models import (
    Evidence,
    EvidenceKind,
    Hypothesis,
    HypothesisStatus,
)

def analyze_sql_regression(incident: SQLQueryRun, baseline: SQLQueryRun) -> tuple[list[Hypothesis], list[Evidence]]:
    hypotheses = []
    evidence = []
    
    incident_join = next((n for n in incident.nodes if n.type == "JOIN"), None)
    baseline_join = next((n for n in baseline.nodes if n.type == "JOIN"), None)
    
    if incident_join and baseline_join:
        # Check for Join Cardinality Explosion
        incident_ratio = incident_join.output_rows / max(1, incident_join.input_rows_left + incident_join.input_rows_right)
        baseline_ratio = baseline_join.output_rows / max(1, baseline_join.input_rows_left + baseline_join.input_rows_right)
        
        cardinality_evidence = Evidence(
            evidence_id="ev-sql-01",
            source="sql_query_plan",
            observation=f"Join output expanded to {incident_join.output_rows} rows from {incident_join.input_rows_left + incident_join.input_rows_right} input rows. Baseline was {baseline_join.output_rows} from {baseline_join.input_rows_left + baseline_join.input_rows_right} input rows.",
            kind=EvidenceKind.DERIVED,
            derived_metric_name="join_expansion_ratio",
            derived_metric_value=incident_ratio / max(1, baseline_ratio)
        )
        evidence.append(cardinality_evidence)
        
        if incident_ratio > baseline_ratio * 10:  # 10x explosion threshold
            hypotheses.append(Hypothesis(
                hypothesis_id="JOIN_CARDINALITY_EXPLOSION",
                name="Join Cardinality Explosion",
                description="A JOIN operation produced significantly more rows than its inputs.",
                status=HypothesisStatus.SUPPORTED,
                heuristic_confidence=0.98,
                rationale="Output rows exceeded input rows by >10x compared to baseline.",
                supporting_evidence_ids=[cardinality_evidence.evidence_id],
                contradicting_evidence_ids=[]
            ))
        else:
            hypotheses.append(Hypothesis(
                hypothesis_id="JOIN_CARDINALITY_EXPLOSION",
                name="Join Cardinality Explosion",
                description="A JOIN operation produced significantly more rows than its inputs.",
                status=HypothesisStatus.REJECTED,
                heuristic_confidence=0.9,
                rationale="Join expansion ratio is within expected limits.",
                supporting_evidence_ids=[],
                contradicting_evidence_ids=[cardinality_evidence.evidence_id]
            ))
            
    return hypotheses, evidence
