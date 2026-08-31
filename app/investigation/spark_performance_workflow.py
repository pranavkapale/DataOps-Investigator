from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

from app.evidence_tools.spark import SparkEvidenceProviderError, SparkFixtureEvidenceProvider
from app.investigation.spark_performance import SparkPerformanceAnalyzer
from app.models import (
    AuditEventType,
    AuditRecord,
    Evidence,
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
    SourceReference,
)


class SparkInvestigationError(RuntimeError):
    """Raised when a Scenario 1 investigation cannot safely produce a report."""


class SparkPerformanceInvestigationOrchestrator:
    """Bounded, deterministic Scenario 1 investigation coordinator."""

    def __init__(
        self,
        provider: SparkFixtureEvidenceProvider,
        analyzer: SparkPerformanceAnalyzer | None = None,
    ) -> None:
        self.provider = provider
        self.analyzer = analyzer or SparkPerformanceAnalyzer()

    def investigate(self, incident_run_id: str) -> InvestigationReport:
        audit_records: List[AuditRecord] = []
        try:
            job = self.provider.get_job(incident_run_id)
            incident_time = _parse_timestamp(job.timestamp)
            incident = Incident(
                incident_id=f"incident-{incident_run_id}",
                investigation_type=InvestigationType.SPARK_PERFORMANCE,
                title=f"Spark performance regression for {job.job_name}",
                description=(
                    f"Investigate Spark run '{job.run_id}' with duration "
                    f"{job.duration_seconds} seconds."
                ),
                created_at=incident_time,
                source_reference=SourceReference(
                    source="spark_fixture_telemetry",
                    location=f"run_id={job.run_id}",
                    captured_at=incident_time,
                ),
            )
            plan = _completed_plan(incident.incident_id)
            _append_audit(
                audit_records,
                incident,
                incident_time,
                AuditEventType.INVESTIGATION_STARTED,
                "Scenario 1 Spark performance investigation started.",
            )
            _append_audit(
                audit_records,
                incident,
                incident_time,
                AuditEventType.PLAN_CREATED,
                "Created bounded Spark investigation plan.",
            )
            _append_audit(
                audit_records,
                incident,
                incident_time,
                AuditEventType.JOB_RETRIEVED,
                f"Retrieved job metadata for run '{job.run_id}'.",
            )

            self.provider.get_stages(incident_run_id)
            _append_audit(
                audit_records,
                incident,
                incident_time,
                AuditEventType.STAGES_RETRIEVED,
                f"Retrieved stage telemetry for run '{job.run_id}'.",
            )
            self.provider.get_partition_statistics(incident_run_id)
            _append_audit(
                audit_records,
                incident,
                incident_time,
                AuditEventType.PARTITION_STATISTICS_RETRIEVED,
                f"Retrieved partition statistics for run '{job.run_id}'.",
            )
            self.provider.get_configuration(incident_run_id)
            _append_audit(
                audit_records,
                incident,
                incident_time,
                AuditEventType.CONFIGURATION_RETRIEVED,
                f"Retrieved Spark configuration for run '{job.run_id}'.",
            )
            baseline = self.provider.get_baseline(job.job_id, incident_run_id)
            _append_audit(
                audit_records,
                incident,
                incident_time,
                AuditEventType.BASELINE_RETRIEVED,
                f"Retrieved baseline run '{baseline.run_id}'.",
            )

            findings = self.analyzer.analyze_runs(
                baseline=baseline,
                incident=self.provider.get_run(incident_run_id),
            )
            _append_audit(
                audit_records,
                incident,
                incident_time,
                AuditEventType.ANALYSIS_COMPLETED,
                "Derived Spark performance metrics and evidence.",
            )
            _append_audit(
                audit_records,
                incident,
                incident_time,
                AuditEventType.HYPOTHESIS_EVALUATED,
                "Evaluated deterministic Spark performance hypotheses.",
            )
            _append_audit(
                audit_records,
                incident,
                incident_time,
                AuditEventType.INVESTIGATION_COMPLETED,
                f"Investigation finished with status '{findings.status.value}'.",
            )

            report = InvestigationReport(
                incident=incident,
                status=findings.status,
                plan=plan,
                hypotheses=findings.hypotheses,
                evidence=findings.evidence,
                leading_hypothesis_id=findings.leading_hypothesis_id,
                confidence=findings.heuristic_confidence,
                rejected_hypothesis_ids=_hypothesis_ids(
                    findings.hypotheses, HypothesisStatus.REJECTED
                ),
                inconclusive_hypothesis_ids=_hypothesis_ids(
                    findings.hypotheses, HypothesisStatus.INCONCLUSIVE
                ),
                recommendations=_recommendations(findings.leading_hypothesis_id, findings.evidence),
                audit_records=audit_records,
                sources=[
                    SourceReference(
                        source="spark_fixture_telemetry",
                        location=str(self.provider.scenario_dir / "baseline"),
                    ),
                    SourceReference(
                        source="spark_fixture_telemetry",
                        location=str(self.provider.scenario_dir / "incident"),
                    ),
                ],
            )
            return report
        except (SparkEvidenceProviderError, ValueError) as exc:
            raise SparkInvestigationError(
                f"Unable to complete Spark investigation for run '{incident_run_id}': {exc}"
            ) from exc


def _completed_plan(incident_id: str) -> InvestigationPlan:
    descriptions = (
        "Retrieve Spark job metadata.",
        "Retrieve stage telemetry.",
        "Retrieve partition statistics.",
        "Retrieve Spark configuration.",
        "Retrieve a comparable baseline run.",
        "Derive performance evidence.",
        "Evaluate candidate hypotheses.",
    )
    return InvestigationPlan(
        plan_id=f"plan-{incident_id}",
        max_steps=len(descriptions),
        steps=[
            InvestigationStep(
                step_id=f"step-{order}",
                order=order,
                description=description,
                status=PlanStepStatus.COMPLETED,
            )
            for order, description in enumerate(descriptions, start=1)
        ],
    )


def _append_audit(
    records: List[AuditRecord],
    incident: Incident,
    incident_time: datetime,
    event_type: AuditEventType,
    details: str,
) -> None:
    records.append(
        AuditRecord(
            record_id=f"audit-{incident.incident_id}-{len(records) + 1}",
            timestamp=incident_time + timedelta(seconds=len(records)),
            event_type=event_type,
            actor="spark_performance_orchestrator",
            investigation_id=incident.incident_id,
            success=True,
            details=details,
        )
    )


def _hypothesis_ids(hypotheses: List, status: HypothesisStatus) -> List[str]:
    return [hypothesis.hypothesis_id for hypothesis in hypotheses if hypothesis.status == status]


def _recommendations(
    leading_hypothesis_id: str | None, evidence: List[Evidence]
) -> List[Recommendation]:
    evidence_ids = {item.evidence_id for item in evidence}
    if leading_hypothesis_id != "DATA_SKEW":
        return []
    return [
        Recommendation(
            recommendation_id="rec-investigate-skewed-keys",
            description=(
                "Investigate high-frequency aggregation keys and confirm whether they "
                "concentrate work in a small number of partitions."
            ),
            risk_level=RiskLevel.LOW,
            evidence_ids=[
                evidence_id
                for evidence_id in (
                    "ev-runtime-regression",
                    "ev-partition-distribution",
                    "ev-shuffle-write-growth",
                )
                if evidence_id in evidence_ids
            ],
            requires_human_approval=False,
        ),
        Recommendation(
            recommendation_id="rec-review-skew-mitigation",
            description=(
                "After human review, consider Spark skew handling or key salting for "
                "extreme key imbalance; do not change production configuration automatically."
            ),
            risk_level=RiskLevel.MEDIUM,
            evidence_ids=[
                evidence_id
                for evidence_id in ("ev-partition-distribution", "ev-shuffle-write-growth")
                if evidence_id in evidence_ids
            ],
            requires_human_approval=True,
        ),
    ]


def _parse_timestamp(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
