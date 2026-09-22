from app.evidence_tools.data_quality import DataQualityRun
from app.models import (
    Evidence,
    EvidenceKind,
    Hypothesis,
    HypothesisStatus,
)

def analyze_data_quality(incident_run: DataQualityRun, baseline_run: DataQualityRun) -> tuple[list[Hypothesis], list[Evidence]]:
    hypotheses = []
    evidence = []
    
    # Check for incomplete upstream data (missing partitions)
    missing_partition_evidence = Evidence(
        evidence_id="ev-dq-01",
        source="data_quality_metrics",
        observation=f"Observed {incident_run.metrics.observed_partition_count} partitions, expected {incident_run.metrics.expected_partition_count}. Missing: {len(incident_run.metrics.missing_partitions)}",
        kind=EvidenceKind.DERIVED,
        derived_metric_name="missing_partition_count",
        derived_metric_value=len(incident_run.metrics.missing_partitions)
    )
    evidence.append(missing_partition_evidence)
    
    if len(incident_run.metrics.missing_partitions) > 0:
        hypotheses.append(Hypothesis(
            hypothesis_id="INCOMPLETE_UPSTREAM_DATA",
            name="Incomplete Upstream Data",
            description="Upstream data pipeline failed to generate all partitions.",
            status=HypothesisStatus.SUPPORTED,
            heuristic_confidence=0.95,
            rationale="Missing partitions observed.",
            supporting_evidence_ids=[missing_partition_evidence.evidence_id],
            contradicting_evidence_ids=[]
        ))
    else:
        hypotheses.append(Hypothesis(
            hypothesis_id="INCOMPLETE_UPSTREAM_DATA",
            name="Incomplete Upstream Data",
            description="Upstream data pipeline failed to generate all partitions.",
            status=HypothesisStatus.REJECTED,
            heuristic_confidence=0.9,
            rationale="All expected partitions are present.",
            supporting_evidence_ids=[],
            contradicting_evidence_ids=[missing_partition_evidence.evidence_id]
        ))
        
    # Check for genuine business drop
    revenue_evidence = Evidence(
        evidence_id="ev-dq-02",
        source="data_quality_metrics",
        observation=f"Revenue changed from {baseline_run.metrics.revenue} to {incident_run.metrics.revenue}",
        kind=EvidenceKind.DERIVED,
        derived_metric_name="revenue_ratio",
        derived_metric_value=incident_run.metrics.revenue / baseline_run.metrics.revenue if baseline_run.metrics.revenue > 0 else 0
    )
    evidence.append(revenue_evidence)
    
    # If revenue dropped but data is complete, it might be a genuine business drop
    if incident_run.metrics.revenue < baseline_run.metrics.revenue * 0.8:
        if len(incident_run.metrics.missing_partitions) == 0:
            hypotheses.append(Hypothesis(
                hypothesis_id="GENUINE_BUSINESS_DROP",
                name="Genuine Business Drop",
                description="Revenue decreased due to genuine business factors.",
                status=HypothesisStatus.SUPPORTED,
                heuristic_confidence=0.8,
                rationale="Revenue dropped significantly despite complete data.",
                supporting_evidence_ids=[revenue_evidence.evidence_id],
                contradicting_evidence_ids=[]
            ))
        else:
            hypotheses.append(Hypothesis(
                hypothesis_id="GENUINE_BUSINESS_DROP",
                name="Genuine Business Drop",
                description="Revenue decreased due to genuine business factors.",
                status=HypothesisStatus.REJECTED,
                heuristic_confidence=0.9,
                rationale="Missing data explains the revenue drop.",
                supporting_evidence_ids=[],
                contradicting_evidence_ids=[revenue_evidence.evidence_id, missing_partition_evidence.evidence_id]
            ))
            
    return hypotheses, evidence
