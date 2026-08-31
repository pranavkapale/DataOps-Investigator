from pathlib import Path

import pytest

from app.evidence_tools.spark import SparkFixtureEvidenceProvider, SparkRunTelemetry
from app.investigation.spark_performance import SparkPerformanceAnalyzer
from app.models import HypothesisStatus, InvestigationStatus


SCENARIO_DIR = Path(__file__).resolve().parents[1] / "scenarios" / "spark_performance"
BASELINE_RUN_ID = "run-customer-aggregation-2026-08-21"
INCIDENT_RUN_ID = "run-customer-aggregation-2026-08-28"


def analyze_fixture():
    provider = SparkFixtureEvidenceProvider(SCENARIO_DIR)
    return SparkPerformanceAnalyzer().analyze(provider, INCIDENT_RUN_ID)


def hypothesis_by_id(findings, hypothesis_id: str):
    return next(
        hypothesis
        for hypothesis in findings.hypotheses
        if hypothesis.hypothesis_id == hypothesis_id
    )


def test_analysis_derives_expected_metrics_from_real_fixtures() -> None:
    findings = analyze_fixture()

    assert findings.metrics.runtime_regression_ratio == 4.0
    assert findings.metrics.input_growth_ratio == 1.08
    assert round(findings.metrics.skew_ratio or 0, 2) == 11.03
    assert round(findings.metrics.shuffle_write_growth_ratio or 0, 2) == 4.11


def test_analysis_generates_stable_factual_evidence() -> None:
    findings = analyze_fixture()
    evidence_by_id = {evidence.evidence_id: evidence for evidence in findings.evidence}

    assert set(evidence_by_id) == {
        "ev-runtime-regression",
        "ev-input-growth",
        "ev-partition-distribution",
        "ev-shuffle-write-growth",
        "ev-memory-spill-growth",
        "ev-configuration-comparison",
    }
    assert evidence_by_id["ev-runtime-regression"].derived_metric_value == 4.0
    assert evidence_by_id["ev-input-growth"].derived_metric_value == 1.08
    assert round(evidence_by_id["ev-partition-distribution"].derived_metric_value or 0, 2) == 11.03
    assert round(evidence_by_id["ev-shuffle-write-growth"].derived_metric_value or 0, 2) == 4.11
    assert (
        evidence_by_id["ev-configuration-comparison"].observation
        == "Relevant Spark configuration is unchanged between runs."
    )
    assert all("DATA_SKEW" not in evidence.observation for evidence in findings.evidence)
    assert all("Data skew" not in evidence.observation for evidence in findings.evidence)


def test_data_skew_is_supported_and_selected_from_telemetry() -> None:
    findings = analyze_fixture()
    data_skew = hypothesis_by_id(findings, "DATA_SKEW")

    assert data_skew.status == HypothesisStatus.SUPPORTED
    assert data_skew.heuristic_confidence == 0.90
    assert findings.leading_hypothesis_id == "DATA_SKEW"
    assert findings.status == InvestigationStatus.COMPLETED


def test_alternative_hypotheses_are_evaluated_without_promoting_memory_pressure() -> None:
    findings = analyze_fixture()

    assert hypothesis_by_id(findings, "INPUT_VOLUME_INCREASE").status == HypothesisStatus.REJECTED
    assert hypothesis_by_id(findings, "MEMORY_RESOURCE_PRESSURE").status == HypothesisStatus.INCONCLUSIVE
    assert hypothesis_by_id(findings, "CONFIGURATION_REGRESSION").status == HypothesisStatus.REJECTED


def test_shuffle_growth_is_supported_as_a_contributing_signal_not_the_leading_cause() -> None:
    findings = analyze_fixture()
    shuffle = hypothesis_by_id(findings, "SHUFFLE_GROWTH")

    assert shuffle.status == HypothesisStatus.SUPPORTED
    assert "contributing signal" in shuffle.rationale
    assert findings.leading_hypothesis_id != "SHUFFLE_GROWTH"


def test_analysis_handles_zero_baseline_values_as_insufficient_evidence() -> None:
    provider = SparkFixtureEvidenceProvider(SCENARIO_DIR)
    baseline_data = provider.get_run(BASELINE_RUN_ID).model_dump()
    baseline_data.update(
        {
            "duration_seconds": 0,
            "input_size_bytes": 0,
            "shuffle_bytes": {"read": 0, "write": 0},
            "partition_size_stats_bytes": {
                "smallest": 0,
                "median": 0,
                "p95": 0,
                "largest": 0,
            },
            "executor_metrics": {
                "peak_executor_memory_bytes": 0,
                "memory_spill_bytes": 0,
                "disk_spill_bytes": 0,
                "gc_time_seconds": 0,
                "failed_task_count": 0,
            },
        }
    )
    baseline = SparkRunTelemetry.model_validate(baseline_data)
    incident = provider.get_run(INCIDENT_RUN_ID)

    findings = SparkPerformanceAnalyzer().analyze_runs(baseline, incident)

    assert findings.metrics.runtime_regression_ratio is None
    assert findings.metrics.input_growth_ratio is None
    assert findings.metrics.shuffle_write_growth_ratio is None
    assert findings.metrics.skew_ratio is not None
    assert findings.status == InvestigationStatus.INSUFFICIENT_EVIDENCE
    assert findings.leading_hypothesis_id is None


def test_hypothesis_evidence_references_resolve_to_generated_evidence() -> None:
    findings = analyze_fixture()
    evidence_ids = {evidence.evidence_id for evidence in findings.evidence}

    for hypothesis in findings.hypotheses:
        assert set(hypothesis.supporting_evidence_ids) <= evidence_ids
        assert set(hypothesis.contradicting_evidence_ids) <= evidence_ids


def test_analysis_does_not_read_the_evaluation_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation_path = SCENARIO_DIR / "evaluation" / "expected_diagnosis.json"
    original_open = Path.open

    def forbid_evaluation_read(path: Path, *args: object, **kwargs: object):
        if path == evaluation_path:
            raise AssertionError("Analysis must not read the evaluation contract.")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", forbid_evaluation_read)

    findings = analyze_fixture()

    assert findings.leading_hypothesis_id == "DATA_SKEW"
