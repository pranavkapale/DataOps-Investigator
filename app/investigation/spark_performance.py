from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.evidence_tools.spark import SparkFixtureEvidenceProvider, SparkRunTelemetry
from app.models import Evidence, EvidenceKind, Hypothesis, HypothesisStatus, InvestigationStatus


RUNTIME_REGRESSION_THRESHOLD = 2.0
MODEST_INPUT_GROWTH_THRESHOLD = 1.25
INPUT_VOLUME_SUPPORT_THRESHOLD = 1.5
SKEW_RATIO_THRESHOLD = 3.0
SHUFFLE_GROWTH_THRESHOLD = 1.5
MEMORY_PRESSURE_SPILL_THRESHOLD = 3.0


class SparkPerformanceMetrics(BaseModel):
    runtime_regression_ratio: Optional[float] = None
    input_growth_ratio: Optional[float] = None
    skew_ratio: Optional[float] = None
    shuffle_write_growth_ratio: Optional[float] = None
    memory_spill_growth_ratio: Optional[float] = None
    configuration_changed_keys: List[str] = Field(default_factory=list)


class SparkPerformanceFindings(BaseModel):
    baseline_run_id: str
    incident_run_id: str
    metrics: SparkPerformanceMetrics
    evidence: List[Evidence]
    hypotheses: List[Hypothesis]
    status: InvestigationStatus
    leading_hypothesis_id: Optional[str] = None
    heuristic_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class SparkPerformanceAnalyzer:
    """Derives deterministic Scenario 1 findings from factual Spark telemetry.

    Confidence is heuristic, not probabilistic: 0.90 is assigned to data skew only
    when all four explicit supporting conditions hold. Other supported hypotheses
    use lower fixed scores because the fixture offers less direct causal evidence.
    """

    def analyze(
        self, provider: SparkFixtureEvidenceProvider, incident_run_id: str
    ) -> SparkPerformanceFindings:
        incident = provider.get_run(incident_run_id)
        baseline = provider.get_baseline(incident.job_id, incident_run_id)
        return self.analyze_runs(baseline=baseline, incident=incident)

    def analyze_runs(
        self, baseline: SparkRunTelemetry, incident: SparkRunTelemetry
    ) -> SparkPerformanceFindings:
        metrics = self._derive_metrics(baseline, incident)
        evidence = self._build_evidence(baseline, incident, metrics)
        hypotheses = SparkHypothesisEvaluator.evaluate(
            baseline, incident, metrics, evidence
        )
        leading_hypothesis = SparkHypothesisEvaluator.select_leading_hypothesis(
            hypotheses
        )

        return SparkPerformanceFindings(
            baseline_run_id=baseline.run_id,
            incident_run_id=incident.run_id,
            metrics=metrics,
            evidence=evidence,
            hypotheses=hypotheses,
            status=(
                InvestigationStatus.COMPLETED
                if leading_hypothesis is not None
                else InvestigationStatus.INSUFFICIENT_EVIDENCE
            ),
            leading_hypothesis_id=(
                leading_hypothesis.hypothesis_id if leading_hypothesis else None
            ),
            heuristic_confidence=(
                leading_hypothesis.heuristic_confidence if leading_hypothesis else None
            ),
        )

    @staticmethod
    def _derive_metrics(
        baseline: SparkRunTelemetry, incident: SparkRunTelemetry
    ) -> SparkPerformanceMetrics:
        changed_keys = sorted(
            key
            for key in set(baseline.spark_configuration)
            | set(incident.spark_configuration)
            if baseline.spark_configuration.get(key) != incident.spark_configuration.get(key)
        )
        return SparkPerformanceMetrics(
            runtime_regression_ratio=_safe_ratio(
                incident.duration_seconds, baseline.duration_seconds
            ),
            input_growth_ratio=_safe_ratio(
                incident.input_size_bytes, baseline.input_size_bytes
            ),
            skew_ratio=_safe_ratio(
                incident.partition_size_stats_bytes.largest,
                incident.partition_size_stats_bytes.median,
            ),
            shuffle_write_growth_ratio=_safe_ratio(
                incident.shuffle_bytes.get("write", 0),
                baseline.shuffle_bytes.get("write", 0),
            ),
            memory_spill_growth_ratio=_safe_ratio(
                incident.executor_metrics.memory_spill_bytes,
                baseline.executor_metrics.memory_spill_bytes,
            ),
            configuration_changed_keys=changed_keys,
        )

    @staticmethod
    def _build_evidence(
        baseline: SparkRunTelemetry,
        incident: SparkRunTelemetry,
        metrics: SparkPerformanceMetrics,
    ) -> List[Evidence]:
        evidence: List[Evidence] = []
        comparisons = (
            (
                "ev-runtime-regression",
                "Runtime increased compared with the baseline run.",
                "runtime_regression_ratio",
                metrics.runtime_regression_ratio,
                incident.duration_seconds,
                baseline.duration_seconds,
            ),
            (
                "ev-input-growth",
                "Input volume changed compared with the baseline run.",
                "input_growth_ratio",
                metrics.input_growth_ratio,
                incident.input_size_bytes,
                baseline.input_size_bytes,
            ),
            (
                "ev-partition-distribution",
                "Largest incident partition was compared with the incident median partition.",
                "skew_ratio",
                metrics.skew_ratio,
                incident.partition_size_stats_bytes.largest,
                incident.partition_size_stats_bytes.median,
            ),
            (
                "ev-shuffle-write-growth",
                "Shuffle write volume changed compared with the baseline run.",
                "shuffle_write_growth_ratio",
                metrics.shuffle_write_growth_ratio,
                incident.shuffle_bytes.get("write", 0),
                baseline.shuffle_bytes.get("write", 0),
            ),
            (
                "ev-memory-spill-growth",
                "Executor memory spill changed compared with the baseline run.",
                "memory_spill_growth_ratio",
                metrics.memory_spill_growth_ratio,
                incident.executor_metrics.memory_spill_bytes,
                baseline.executor_metrics.memory_spill_bytes,
            ),
        )
        for evidence_id, observation, metric_name, metric_value, observed, baseline_value in comparisons:
            if metric_value is not None:
                evidence.append(
                    Evidence(
                        evidence_id=evidence_id,
                        source="spark_fixture_telemetry",
                        observation=observation,
                        kind=EvidenceKind.DERIVED,
                        observed_value=observed,
                        baseline_value=baseline_value,
                        derived_metric_name=metric_name,
                        derived_metric_value=metric_value,
                    )
                )

        changed_keys = metrics.configuration_changed_keys
        evidence.append(
            Evidence(
                evidence_id="ev-configuration-comparison",
                source="spark_fixture_telemetry",
                observation=(
                    "Relevant Spark configuration changed between runs."
                    if changed_keys
                    else "Relevant Spark configuration is unchanged between runs."
                ),
                kind=EvidenceKind.DERIVED,
                observed_value=", ".join(changed_keys) if changed_keys else "unchanged",
                baseline_value="baseline configuration",
                derived_metric_name="configuration_changed_key_count",
                derived_metric_value=len(changed_keys),
            )
        )
        return evidence


class SparkHypothesisEvaluator:
    """Applies the explicit, deterministic Scenario 1 hypothesis rules."""

    @staticmethod
    def evaluate(
        baseline: SparkRunTelemetry,
        incident: SparkRunTelemetry,
        metrics: SparkPerformanceMetrics,
        evidence: List[Evidence],
    ) -> List[Hypothesis]:
        evidence_ids = {item.evidence_id for item in evidence}
        runtime = metrics.runtime_regression_ratio
        input_growth = metrics.input_growth_ratio
        skew = metrics.skew_ratio
        shuffle_growth = metrics.shuffle_write_growth_ratio
        spill_growth = metrics.memory_spill_growth_ratio

        skew_supported = all(
            value is not None
            for value in (runtime, input_growth, skew, shuffle_growth)
        ) and (
            runtime >= RUNTIME_REGRESSION_THRESHOLD
            and input_growth <= MODEST_INPUT_GROWTH_THRESHOLD
            and skew >= SKEW_RATIO_THRESHOLD
            and shuffle_growth >= SHUFFLE_GROWTH_THRESHOLD
        )
        data_skew = Hypothesis(
            hypothesis_id="DATA_SKEW",
            name="Data skew",
            description="Uneven partition sizes caused an imbalanced aggregation stage.",
            status=(
                HypothesisStatus.SUPPORTED
                if skew_supported
                else HypothesisStatus.INCONCLUSIVE
            ),
            supporting_evidence_ids=_present_evidence_ids(
                evidence_ids,
                "ev-runtime-regression",
                "ev-input-growth",
                "ev-partition-distribution",
                "ev-shuffle-write-growth",
            ) if skew_supported else [],
            heuristic_confidence=0.90 if skew_supported else None,
            rationale=(
                "Runtime and shuffle growth coincide with a high partition imbalance, "
                "while input growth remains modest."
                if skew_supported
                else "Available telemetry does not meet all deterministic data-skew conditions."
            ),
        )

        input_rejected = (
            runtime is not None
            and input_growth is not None
            and runtime >= RUNTIME_REGRESSION_THRESHOLD
            and input_growth <= MODEST_INPUT_GROWTH_THRESHOLD
        )
        input_supported = (
            runtime is not None
            and input_growth is not None
            and input_growth >= INPUT_VOLUME_SUPPORT_THRESHOLD
            and input_growth >= runtime * 0.75
        )
        input_volume = Hypothesis(
            hypothesis_id="INPUT_VOLUME_INCREASE",
            name="Input volume increase",
            description="A larger input volume caused the runtime regression.",
            status=(
                HypothesisStatus.REJECTED
                if input_rejected
                else HypothesisStatus.SUPPORTED
                if input_supported
                else HypothesisStatus.INCONCLUSIVE
            ),
            supporting_evidence_ids=(
                _present_evidence_ids(evidence_ids, "ev-input-growth", "ev-runtime-regression")
                if input_supported
                else []
            ),
            contradicting_evidence_ids=(
                _present_evidence_ids(evidence_ids, "ev-input-growth", "ev-runtime-regression")
                if input_rejected
                else []
            ),
            heuristic_confidence=0.65 if input_supported else None,
            rationale=(
                "Input growth is small relative to the runtime regression."
                if input_rejected
                else "Input growth is large enough to account for much of the runtime regression."
                if input_supported
                else "Input telemetry does not establish or rule out this cause."
            ),
        )

        shuffle_supported = (
            runtime is not None
            and shuffle_growth is not None
            and runtime >= RUNTIME_REGRESSION_THRESHOLD
            and shuffle_growth >= SHUFFLE_GROWTH_THRESHOLD
        )
        shuffle = Hypothesis(
            hypothesis_id="SHUFFLE_GROWTH",
            name="Shuffle growth",
            description="Increased shuffle volume contributed to the performance regression.",
            status=(
                HypothesisStatus.SUPPORTED
                if shuffle_supported
                else HypothesisStatus.INCONCLUSIVE
            ),
            supporting_evidence_ids=(
                _present_evidence_ids(
                    evidence_ids, "ev-runtime-regression", "ev-shuffle-write-growth"
                )
                if shuffle_supported
                else []
            ),
            heuristic_confidence=0.65 if shuffle_supported else None,
            rationale=(
                "Shuffle volume increased with runtime; this is a contributing signal, "
                "not a selected root cause by itself."
                if shuffle_supported
                else "Shuffle telemetry does not establish a meaningful contributing signal."
            ),
        )

        memory_supported = (
            spill_growth is not None
            and spill_growth >= MEMORY_PRESSURE_SPILL_THRESHOLD
            and incident.executor_metrics.failed_task_count
            > baseline.executor_metrics.failed_task_count
        )
        memory_pressure = Hypothesis(
            hypothesis_id="MEMORY_RESOURCE_PRESSURE",
            name="Memory or resource pressure",
            description="Resource pressure caused the runtime regression.",
            status=(
                HypothesisStatus.SUPPORTED
                if memory_supported
                else HypothesisStatus.INCONCLUSIVE
            ),
            supporting_evidence_ids=(
                _present_evidence_ids(evidence_ids, "ev-memory-spill-growth")
                if memory_supported
                else []
            ),
            heuristic_confidence=0.60 if memory_supported else None,
            rationale=(
                "Spill growth coincides with an increase in failed tasks."
                if memory_supported
                else "Spill may be elevated, but the fixture does not show failure or exhaustion "
                "evidence needed to establish it as the cause."
            ),
        )

        configuration_changed = bool(metrics.configuration_changed_keys)
        configuration = Hypothesis(
            hypothesis_id="CONFIGURATION_REGRESSION",
            name="Configuration regression",
            description="A Spark configuration change caused the runtime regression.",
            status=(
                HypothesisStatus.SUPPORTED
                if configuration_changed and runtime is not None and runtime >= RUNTIME_REGRESSION_THRESHOLD
                else HypothesisStatus.REJECTED
                if not configuration_changed
                else HypothesisStatus.INCONCLUSIVE
            ),
            supporting_evidence_ids=(
                _present_evidence_ids(evidence_ids, "ev-configuration-comparison")
                if configuration_changed and runtime is not None and runtime >= RUNTIME_REGRESSION_THRESHOLD
                else []
            ),
            contradicting_evidence_ids=(
                _present_evidence_ids(evidence_ids, "ev-configuration-comparison")
                if not configuration_changed
                else []
            ),
            heuristic_confidence=(
                0.70
                if configuration_changed and runtime is not None and runtime >= RUNTIME_REGRESSION_THRESHOLD
                else None
            ),
            rationale=(
                "Relevant Spark configuration is unchanged between the baseline and incident."
                if not configuration_changed
                else "A configuration difference exists, but it is not paired with a measurable regression."
                if runtime is None or runtime < RUNTIME_REGRESSION_THRESHOLD
                else "A configuration difference coincides with the runtime regression."
            ),
        )
        return [data_skew, input_volume, shuffle, memory_pressure, configuration]

    @staticmethod
    def select_leading_hypothesis(
        hypotheses: List[Hypothesis],
    ) -> Optional[Hypothesis]:
        root_cause_candidates = (
            "DATA_SKEW",
            "INPUT_VOLUME_INCREASE",
            "MEMORY_RESOURCE_PRESSURE",
            "CONFIGURATION_REGRESSION",
        )
        supported = [
            hypothesis
            for hypothesis in hypotheses
            if hypothesis.hypothesis_id in root_cause_candidates
            and hypothesis.status == HypothesisStatus.SUPPORTED
            and hypothesis.heuristic_confidence is not None
        ]
        return max(supported, key=lambda item: item.heuristic_confidence, default=None)


def _safe_ratio(numerator: int, denominator: int) -> Optional[float]:
    if denominator <= 0:
        return None
    return numerator / denominator


def _present_evidence_ids(available_ids: set[str], *evidence_ids: str) -> List[str]:
    return [evidence_id for evidence_id in evidence_ids if evidence_id in available_ids]
