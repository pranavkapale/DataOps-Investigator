from pathlib import Path

import pytest

from app.evidence_tools.spark import (
    SparkFixtureEvidenceProvider,
    SparkRunTelemetry,
    UnknownSparkJobError,
)
from app.investigation.spark_performance_workflow import (
    SparkInvestigationError,
    SparkPerformanceInvestigationOrchestrator,
)
from app.models import AuditEventType, HypothesisStatus, InvestigationReport, InvestigationStatus


SCENARIO_DIR = Path(__file__).resolve().parents[1] / "scenarios" / "spark_performance"
BASELINE_RUN_ID = "run-customer-aggregation-2026-08-21"
INCIDENT_RUN_ID = "run-customer-aggregation-2026-08-28"


@pytest.fixture
def provider() -> SparkFixtureEvidenceProvider:
    return SparkFixtureEvidenceProvider(SCENARIO_DIR)


def investigate(provider: SparkFixtureEvidenceProvider) -> InvestigationReport:
    return SparkPerformanceInvestigationOrchestrator(provider).investigate(INCIDENT_RUN_ID)


def test_successful_scenario_one_investigation_returns_valid_report(
    provider: SparkFixtureEvidenceProvider,
) -> None:
    report = investigate(provider)

    assert isinstance(report, InvestigationReport)
    assert report.incident.incident_id == f"incident-{INCIDENT_RUN_ID}"
    assert report.incident.title == "Spark performance regression for customer_aggregation"
    assert report.incident.investigation_type.value == "SPARK_PERFORMANCE"
    assert report.status == InvestigationStatus.COMPLETED
    assert report.leading_hypothesis_id == "DATA_SKEW"
    assert report.confidence is not None and 0.0 <= report.confidence <= 1.0
    assert [source.location for source in report.sources] == [
        str(SCENARIO_DIR / "baseline"),
        str(SCENARIO_DIR / "incident"),
    ]


def test_workflow_plan_evidence_hypotheses_and_recommendations_are_grounded(
    provider: SparkFixtureEvidenceProvider,
) -> None:
    report = investigate(provider)
    evidence_ids = {evidence.evidence_id for evidence in report.evidence}

    assert report.plan.max_steps == 7
    assert [step.order for step in report.plan.steps] == list(range(1, 8))
    assert all(step.status.value == "COMPLETED" for step in report.plan.steps)
    assert "ev-runtime-regression" in evidence_ids
    assert all(
        set(hypothesis.supporting_evidence_ids) <= evidence_ids
        and set(hypothesis.contradicting_evidence_ids) <= evidence_ids
        for hypothesis in report.hypotheses
    )
    assert all(
        set(recommendation.evidence_ids) <= evidence_ids
        for recommendation in report.recommendations
    )
    assert all(recommendation.action_id is None for recommendation in report.recommendations)


def test_workflow_records_major_audit_events(provider: SparkFixtureEvidenceProvider) -> None:
    report = investigate(provider)
    event_types = [record.event_type for record in report.audit_records]

    assert event_types == [
        AuditEventType.INVESTIGATION_STARTED,
        AuditEventType.PLAN_CREATED,
        AuditEventType.JOB_RETRIEVED,
        AuditEventType.STAGES_RETRIEVED,
        AuditEventType.PARTITION_STATISTICS_RETRIEVED,
        AuditEventType.CONFIGURATION_RETRIEVED,
        AuditEventType.BASELINE_RETRIEVED,
        AuditEventType.ANALYSIS_COMPLETED,
        AuditEventType.HYPOTHESIS_EVALUATED,
        AuditEventType.INVESTIGATION_COMPLETED,
    ]
    assert all(record.success is True for record in report.audit_records)


def test_unknown_run_is_wrapped_as_a_controlled_investigation_error(
    provider: SparkFixtureEvidenceProvider,
) -> None:
    orchestrator = SparkPerformanceInvestigationOrchestrator(provider)

    with pytest.raises(SparkInvestigationError, match="was not found"):
        orchestrator.investigate("run-does-not-exist")


def test_missing_baseline_is_wrapped_as_a_controlled_investigation_error(
    provider: SparkFixtureEvidenceProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing_baseline(job_id: str, run_id: str) -> SparkRunTelemetry:
        raise UnknownSparkJobError(f"No baseline for '{job_id}'.")

    monkeypatch.setattr(provider, "get_baseline", missing_baseline)

    with pytest.raises(SparkInvestigationError, match="No baseline"):
        investigate(provider)


def test_insufficient_evidence_returns_no_leading_hypothesis(
    provider: SparkFixtureEvidenceProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline_data = provider.get_run(BASELINE_RUN_ID).model_dump()
    baseline_data["duration_seconds"] = 0
    baseline_data["input_size_bytes"] = 0
    baseline_data["shuffle_bytes"] = {"read": 0, "write": 0}
    baseline_data["executor_metrics"]["memory_spill_bytes"] = 0
    zero_baseline = SparkRunTelemetry.model_validate(baseline_data)
    monkeypatch.setattr(provider, "get_baseline", lambda job_id, run_id: zero_baseline)

    report = investigate(provider)

    assert report.status == InvestigationStatus.INSUFFICIENT_EVIDENCE
    assert report.leading_hypothesis_id is None
    assert report.recommendations == []
    assert all(
        hypothesis.status != HypothesisStatus.SUPPORTED
        or hypothesis.hypothesis_id == "SHUFFLE_GROWTH"
        for hypothesis in report.hypotheses
    )


def test_workflow_never_reads_the_evaluation_contract(
    provider: SparkFixtureEvidenceProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    evaluation_path = SCENARIO_DIR / "evaluation" / "expected_diagnosis.json"
    original_open = Path.open

    def forbid_evaluation_read(path: Path, *args: object, **kwargs: object):
        if path == evaluation_path:
            raise AssertionError("Workflow must not read the evaluation contract.")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", forbid_evaluation_read)

    report = investigate(provider)

    assert report.leading_hypothesis_id == "DATA_SKEW"
