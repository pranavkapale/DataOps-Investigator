from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

from app.evidence_tools.pipeline import PipelineEvidenceProviderError, PipelineEvidenceProvider
from app.investigation.pipeline_failure import PipelineFailureAnalyzer
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


class PipelineInvestigationError(RuntimeError):
    """Raised when a Scenario 2 investigation cannot safely produce a report."""


class PipelineFailureInvestigationOrchestrator:
    """Bounded, deterministic Scenario 2 investigation coordinator."""

    def __init__(
        self,
        provider: PipelineEvidenceProvider,
        analyzer: PipelineFailureAnalyzer | None = None,
    ) -> None:
        self.provider = provider
        self.analyzer = analyzer or PipelineFailureAnalyzer()

    def investigate(self, incident_run_id: str) -> InvestigationReport:
        audit_records: List[AuditRecord] = []
        try:
            # We don't use 'with self.provider' because it is just a protocol without __enter__ defined
            # However, if it's expected, we can try to use it if it supports context management.
            # But the Spark provider has it. Let's just avoid it since it's not strictly required in the protocol.
            
            run = self.provider.get_run(incident_run_id)
            incident_time = _parse_timestamp(run.timestamp)
            incident = Incident(
                incident_id=f"incident-{incident_run_id}",
                investigation_type=InvestigationType.PIPELINE_FAILURE,
                title=f"Pipeline failure for {run.pipeline_name}",
                description=(
                    f"Investigate pipeline run '{run.run_id}' that failed at "
                    f"{run.timestamp}."
                ),
                created_at=incident_time,
                source_reference=SourceReference(
                    source="pipeline_fixture_telemetry",
                    location=f"run_id={run.run_id}",
                    captured_at=incident_time,
                ),
            )
            plan = _completed_plan(incident.incident_id)
            _append_audit(
                audit_records,
                incident,
                incident_time,
                AuditEventType.INVESTIGATION_STARTED,
                "Scenario 2 Pipeline failure investigation started.",
            )
            _append_audit(
                audit_records,
                incident,
                incident_time,
                AuditEventType.PLAN_CREATED,
                "Created bounded Pipeline investigation plan.",
            )
            _append_audit(
                audit_records,
                incident,
                incident_time,
                AuditEventType.EVIDENCE_COLLECTED,
                f"Retrieved run metadata for run '{run.run_id}'.",
            )
            
            # The analyzer loads logs, current_schema, and baseline_schema itself
            # We just record the audit events conceptually
            findings = self.analyzer.analyze(provider=self.provider, incident_run_id=incident_run_id)
            
            _append_audit(
                audit_records,
                incident,
                incident_time,
                AuditEventType.EVIDENCE_COLLECTED,
                "Retrieved pipeline failure logs, current schema, and baseline schema.",
            )

            _append_audit(
                audit_records,
                incident,
                incident_time,
                AuditEventType.ANALYSIS_COMPLETED,
                "Derived pipeline failure metrics and evidence.",
            )
            _append_audit(
                audit_records,
                incident,
                incident_time,
                AuditEventType.HYPOTHESIS_EVALUATED,
                "Evaluated deterministic pipeline failure hypotheses.",
            )
            _append_audit(
                audit_records,
                incident,
                incident_time,
                AuditEventType.REPORT_COMPLETED,
                "Generated evidence-supported recommendations.",
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
                confidence=None, # Pipeline analyzer does not use heuristic confidence currently
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
                        source="pipeline_fixture_telemetry",
                        # We don't have direct access to provider.scenario_dir on the protocol
                        # so we omit detailed location or provide a general one
                        location="local_fixtures",
                    )
                ],
            )
            return report
        except (PipelineEvidenceProviderError, ValueError) as exc:
            raise PipelineInvestigationError(
                f"Unable to complete Pipeline investigation for run '{incident_run_id}': {exc}"
            ) from exc


def _completed_plan(incident_id: str) -> InvestigationPlan:
    descriptions = (
        "Retrieve pipeline run metadata.",
        "Retrieve pipeline task logs.",
        "Retrieve current pipeline schema.",
        "Retrieve baseline/historical schema.",
        "Analyze schema drift and correlate with error logs.",
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
            actor="pipeline_failure_orchestrator",
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
    if leading_hypothesis_id != "SCHEMA_DRIFT":
        return []
    return [
        Recommendation(
            recommendation_id="rec-validate-schema-contract",
            description=(
                "Validate the changed field type against the historical schema contract. "
                "Ensure that upstream or ingestion processes have not accidentally dropped or altered column types."
            ),
            risk_level=RiskLevel.LOW,
            evidence_ids=[
                evidence_id
                for evidence_id in ("ev-schema-diff", "ev-log-mismatch")
                if evidence_id in evidence_ids
            ],
            requires_human_approval=False,
        ),
    ]


def _parse_timestamp(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
