from __future__ import annotations

from datetime import datetime, timedelta
from typing import List

from app.evidence_tools.spark import SparkEvidenceProvider, SparkEvidenceProviderError
from app.investigation.planner import InvestigationPlanner, InvestigationPlanProposal, InvestigationPlannerError
from app.investigation.spark_performance import SparkPerformanceAnalyzer
from app.investigation.spark_performance_workflow import (
    SparkInvestigationError,
    _append_audit,
    _hypothesis_ids,
    _parse_timestamp,
    _recommendations,
)
from app.models import (
    AuditEventType,
    AuditRecord,
    HypothesisStatus,
    Incident,
    InvestigationPlan,
    InvestigationReport,
    InvestigationStatus,
    InvestigationStep,
    InvestigationType,
    PlanStepStatus,
    SourceReference,
)


class SparkAgenticInvestigationOrchestrator:
    """Agentic Scenario 1 investigation coordinator using the LLM planner."""

    def __init__(
        self,
        provider: SparkEvidenceProvider,
        planner: InvestigationPlanner,
        analyzer: SparkPerformanceAnalyzer | None = None,
    ) -> None:
        self.provider = provider
        self.planner = planner
        self.analyzer = analyzer or SparkPerformanceAnalyzer()

    def investigate(self, incident_run_id: str) -> InvestigationReport:
        audit_records: List[AuditRecord] = []
        try:
            with self.provider:
                # 1. Fetch initial job metadata to form the incident
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
                
                _append_audit(
                    audit_records,
                    incident,
                    incident_time,
                    AuditEventType.INVESTIGATION_STARTED,
                    "Scenario 1 agentic Spark performance investigation started.",
                )
                
                # 2. Invoke the LLM Planner
                try:
                    proposal = self.planner.plan_investigation(incident.description)
                    plan = self._convert_plan(proposal, incident.incident_id)
                    _append_audit(
                        audit_records,
                        incident,
                        incident_time,
                        AuditEventType.PLAN_CREATED,
                        "Created agentic Spark investigation plan using LLM.",
                    )
                except InvestigationPlannerError as e:
                    _append_audit(
                        audit_records,
                        incident,
                        incident_time,
                        AuditEventType.PLAN_CREATED, # Reusing this event type to denote planning phase failure
                        f"Planner failed: {e}",
                    )
                    return InvestigationReport(
                        incident=incident,
                        status=InvestigationStatus.FAILED,
                        plan=InvestigationPlan(
                            plan_id=f"plan-{incident.incident_id}",
                            max_steps=5,
                            steps=[]
                        ),
                        hypotheses=[],
                        evidence=[],
                        leading_hypothesis_id=None,
                        confidence=None,
                        rejected_hypothesis_ids=[],
                        inconclusive_hypothesis_ids=[],
                        recommendations=[],
                        audit_records=audit_records,
                        sources=[],
                    )

                # 3. Execute the plan
                tool_mapping = {
                    "spark_get_job": lambda: self.provider.get_job(incident_run_id),
                    "spark_get_stages": lambda: self.provider.get_stages(incident_run_id),
                    "spark_get_partition_statistics": lambda: self.provider.get_partition_statistics(incident_run_id),
                    "spark_get_configuration": lambda: self.provider.get_configuration(incident_run_id),
                    "spark_get_baseline": lambda: self.provider.get_baseline(job.job_id, incident_run_id),
                }

                for step in proposal.steps:
                    if step.tool in tool_mapping:
                        tool_mapping[step.tool]()
                        _append_audit(
                            audit_records,
                            incident,
                            incident_time,
                            self._map_audit_event_type(step.tool),
                            f"Executed planned tool '{step.tool}': {step.reason}",
                        )
                    else:
                        # Should be prevented by planner validation, but double checking at execution boundary
                        raise ValueError(f"Unknown or unauthorized tool '{step.tool}' requested by planner.")

                # 4. Fetch the full runs for the deterministic analyzer.
                # Implicitly fetching baseline if the LLM forgot, to satisfy the analyzer's signature.
                # (The LLM should plan it, but the deterministic analyzer requires it structurally)
                incident_telemetry = self.provider.get_run(incident_run_id)
                baseline_telemetry = self.provider.get_baseline(job.job_id, incident_run_id)

                # 5. Deterministic Analysis
                findings = self.analyzer.analyze_runs(
                    baseline=baseline_telemetry,
                    incident=incident_telemetry,
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
                    f"Agentic investigation finished with status '{findings.status.value}'.",
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
                f"Unable to complete agentic Spark investigation for run '{incident_run_id}': {exc}"
            ) from exc

    def _convert_plan(self, proposal: InvestigationPlanProposal, incident_id: str) -> InvestigationPlan:
        return InvestigationPlan(
            plan_id=f"plan-{incident_id}",
            max_steps=5,
            steps=[
                InvestigationStep(
                    step_id=f"step-{i+1}",
                    order=i+1,
                    description=f"{step.tool}: {step.reason}",
                    status=PlanStepStatus.COMPLETED,
                )
                for i, step in enumerate(proposal.steps)
            ],
        )

    def _map_audit_event_type(self, tool_name: str) -> AuditEventType:
        mapping = {
            "spark_get_job": AuditEventType.JOB_RETRIEVED,
            "spark_get_stages": AuditEventType.STAGES_RETRIEVED,
            "spark_get_partition_statistics": AuditEventType.PARTITION_STATISTICS_RETRIEVED,
            "spark_get_configuration": AuditEventType.CONFIGURATION_RETRIEVED,
            "spark_get_baseline": AuditEventType.BASELINE_RETRIEVED,
        }
        return mapping.get(tool_name, AuditEventType.INVESTIGATION_STARTED)
