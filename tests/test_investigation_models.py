from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models import (
    AuditEventType,
    AuditRecord,
    Evidence,
    EvidenceKind,
    Hypothesis,
    HypothesisStatus,
    Incident,
    InvestigationPlan,
    InvestigationReport,
    InvestigationStatus,
    InvestigationStep,
    InvestigationType,
    PlanStepStatus,
    Recommendation,
    RiskLevel,
)


def build_spark_report() -> InvestigationReport:
    evidence = Evidence(
        evidence_id="ev-skew-ratio",
        source="spark_stage_metrics",
        observation="The largest partition is 10.5 times the median partition size.",
        kind=EvidenceKind.DERIVED,
        observed_at=datetime(2026, 8, 28, 2, 14, tzinfo=timezone.utc),
        observed_value=4.3,
        baseline_value=0.41,
        derived_metric_name="skew_ratio",
        derived_metric_value=10.5,
    )
    skew = Hypothesis(
        hypothesis_id="H1",
        name="Data skew",
        description="An uneven key distribution caused one partition to dominate stage runtime.",
        status=HypothesisStatus.SUPPORTED,
        supporting_evidence_ids=[evidence.evidence_id],
        heuristic_confidence=0.9,
        rationale="The partition-size ratio is substantially above the historical baseline.",
    )
    input_growth = Hypothesis(
        hypothesis_id="H2",
        name="Input volume increase",
        description="More input data caused the regression.",
        status=HypothesisStatus.INCONCLUSIVE,
        rationale="Input-volume evidence has not yet been collected.",
    )
    return InvestigationReport(
        incident=Incident(
            incident_id="inc-spark-001",
            investigation_type=InvestigationType.SPARK_PERFORMANCE,
            title="Customer aggregation job is slower than baseline",
            description="The run took 100 minutes instead of the usual 25 minutes.",
        ),
        status=InvestigationStatus.COMPLETED,
        plan=InvestigationPlan(
            plan_id="plan-spark-001",
            max_steps=3,
            steps=[
                InvestigationStep(
                    step_id="step-1",
                    order=1,
                    description="Compare stage and partition metrics with the baseline.",
                    status=PlanStepStatus.COMPLETED,
                )
            ],
        ),
        hypotheses=[skew, input_growth],
        evidence=[evidence],
        leading_hypothesis_id=skew.hypothesis_id,
        confidence=0.9,
        inconclusive_hypothesis_ids=[input_growth.hypothesis_id],
        recommendations=[
            Recommendation(
                recommendation_id="rec-1",
                description="Investigate the skewed join key before changing production settings.",
                risk_level=RiskLevel.LOW,
                evidence_ids=[evidence.evidence_id],
            )
        ],
        audit_records=[
            AuditRecord(
                record_id="audit-1",
                event_type=AuditEventType.EVIDENCE_COLLECTED,
                actor="spark.get_stages",
                investigation_id="inc-spark-001",
                success=True,
            )
        ],
    )


def test_complete_minimal_spark_performance_report_can_be_constructed() -> None:
    report = build_spark_report()

    assert report.incident.investigation_type is InvestigationType.SPARK_PERFORMANCE
    assert report.leading_hypothesis_id == "H1"
    assert report.evidence[0].derived_metric_value == 10.5


def test_enum_and_required_field_validation() -> None:
    with pytest.raises(ValidationError):
        Incident(
            incident_id="inc-1",
            investigation_type="NOT_A_TYPE",
            title="Missing data",
            description="A partition may be missing.",
        )

    with pytest.raises(ValidationError):
        Evidence(
            evidence_id="ev-1",
            source="spark_stage_metrics",
            kind=EvidenceKind.OBSERVED,
        )


def test_plan_enforces_bounded_unique_ordered_steps() -> None:
    with pytest.raises(ValidationError, match="unique"):
        InvestigationPlan(
            plan_id="plan-1",
            max_steps=2,
            steps=[
                InvestigationStep(step_id="a", order=1, description="Collect metrics."),
                InvestigationStep(step_id="b", order=1, description="Compare baseline."),
            ],
        )


def test_report_rejects_unknown_evidence_references() -> None:
    report = build_spark_report().model_dump()
    report["hypotheses"][0]["supporting_evidence_ids"] = ["ev-missing"]

    with pytest.raises(ValidationError, match="unknown evidence"):
        InvestigationReport(**report)


def test_report_serializes_and_deserializes_cleanly() -> None:
    report = build_spark_report()

    restored = InvestigationReport.model_validate_json(report.model_dump_json())

    assert restored.model_dump() == report.model_dump()


@pytest.mark.parametrize(
    ("field", "value"),
    [("confidence", 1.1), ("confidence", -0.1)],
)
def test_report_rejects_invalid_confidence(field: str, value: float) -> None:
    report = build_spark_report().model_dump()
    report[field] = value

    with pytest.raises(ValidationError):
        InvestigationReport(**report)


def test_models_reject_invalid_risk_and_hypothesis_status() -> None:
    with pytest.raises(ValidationError):
        Recommendation(
            recommendation_id="rec-1",
            description="Inspect the skewed key.",
            risk_level="EXTREME",
        )

    with pytest.raises(ValidationError):
        Hypothesis(
            hypothesis_id="H1",
            name="Data skew",
            description="Skewed partition sizes.",
            status="MAYBE",
            rationale="No evidence yet.",
        )
