from __future__ import annotations

from typing import List

from app.evidence_tools.pipeline import PipelineEvidenceProvider, PipelineEvidenceProviderError
from app.investigation.planner import InvestigationPlannerProtocol, InvestigationPlanProposal, InvestigationPlannerError
from app.investigation.pipeline_failure import PipelineFailureAnalyzer
from app.investigation.pipeline_failure_workflow import (
    PipelineInvestigationError,
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


class PipelineAgenticInvestigationOrchestrator:
    """Agentic Scenario 2 investigation coordinator using the LLM planner."""

    def __init__(
        self,
        provider: PipelineEvidenceProvider,
        planner: InvestigationPlannerProtocol,
        analyzer: PipelineFailureAnalyzer | None = None,
    ) -> None:
        self.provider = provider
        self.planner = planner
        self.analyzer = analyzer or PipelineFailureAnalyzer()

    def investigate(self, incident_run_id: str, incident_description_override: str | None = None) -> InvestigationReport:
        audit_records: List[AuditRecord] = []
        try:
            # We assume the caller handles context management (e.g. `with provider:`),
            # or the provider connects implicitly. The prompt specifies: 
            # "The orchestrator should use the provider's existing context-management lifecycle"
            # if we are passed an MCP provider. Wait, the prompt says "reuse one MCP session... 
            # The orchestrator should use the provider's existing context-management lifecycle." 
            # Let's see if we should wrap it in `with self.provider:` here if it has an `__enter__` method.
            # `SparkAgenticInvestigationOrchestrator` does `with self.provider:`. 
            # However `PipelineEvidenceProvider` doesn't strictly have `__enter__` in its protocol but `PipelineMCPEvidenceProvider` does.
            # To be safe and identical to Spark:
            
            # Since provider might not have __enter__ if it's the fixture provider without it, we can use a conditional context manager or just try.
            # Actually, `PipelineFixtureEvidenceProvider` does not define `__enter__`. Let's just use `contextlib.nullcontext` if missing, or we can just try.
            import contextlib
            ctx = self.provider if hasattr(self.provider, "__enter__") else contextlib.nullcontext()
            
            with ctx:
                # 1. Fetch initial run metadata to form the incident
                run = self.provider.get_run(incident_run_id)
                incident_time = _parse_timestamp(run.timestamp)

                desc = incident_description_override or (
                    f"Investigate pipeline run '{run.run_id}' that failed at "
                    f"{run.timestamp}."
                )

                incident = Incident(
                    incident_id=f"incident-{incident_run_id}",
                    investigation_type=InvestigationType.PIPELINE_FAILURE,
                    title=f"Pipeline failure for {run.pipeline_name}",
                    description=desc,
                    created_at=incident_time,
                    source_reference=SourceReference(
                        source="pipeline_evidence_provider",
                        location=f"run_id={run.run_id}",
                        captured_at=incident_time,
                    ),
                )

                _append_audit(
                    audit_records,
                    incident,
                    incident_time,
                    AuditEventType.INVESTIGATION_STARTED,
                    "Scenario 2 agentic Pipeline failure investigation started.",
                )

                # 2. Invoke the LLM Planner
                try:
                    proposal = self.planner.plan_investigation(
                        incident.description,
                        InvestigationType.PIPELINE_FAILURE
                    )
                    plan = self._convert_plan(proposal, incident.incident_id)
                    _append_audit(
                        audit_records,
                        incident,
                        incident_time,
                        AuditEventType.PLAN_CREATED,
                        "Created agentic Pipeline investigation plan using LLM.",
                    )
                except InvestigationPlannerError as e:
                    _append_audit(
                        audit_records,
                        incident,
                        incident_time,
                        AuditEventType.PLAN_CREATED,
                        f"Planner failed: {e}",
                    )
                    return InvestigationReport(
                        incident=incident,
                        status=InvestigationStatus.FAILED,
                        plan=InvestigationPlan(
                            plan_id=f"plan-{incident.incident_id}",
                            max_steps=4,
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

                # 3. Execute the plan mapping tools to evidence provider calls
                task_id = run.failed_task or "unknown"
                dataset_id = "default"
                table_id = "default"

                tool_mapping = {
                    "pipeline_get_run": lambda: self.provider.get_run(incident_run_id),
                    "pipeline_get_logs": lambda: self.provider.get_logs(incident_run_id, task_id),
                    "pipeline_get_current_schema": lambda: self.provider.get_current_schema(dataset_id, table_id),
                    "pipeline_get_baseline_schema": lambda: self.provider.get_baseline_schema(dataset_id, table_id),
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
                        raise ValueError(f"Unknown or unauthorized tool '{step.tool}' requested by planner.")

                # 4. Deterministic Analysis
                # The PipelineFailureAnalyzer will internally fetch the schemas and logs it needs.
                findings = self.analyzer.analyze(
                    provider=self.provider,
                    incident_run_id=incident_run_id,
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
                    "Evaluated deterministic pipeline hypotheses.",
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
                    confidence=None, # Not heuristic yet
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
                            source="pipeline_evidence_provider",
                            location="agentic_orchestration",
                        )
                    ],
                )
                return report

        except (PipelineEvidenceProviderError, ValueError) as exc:
            raise PipelineInvestigationError(
                f"Unable to complete agentic Pipeline investigation for run '{incident_run_id}': {exc}"
            ) from exc

    def _convert_plan(self, proposal: InvestigationPlanProposal, incident_id: str) -> InvestigationPlan:
        return InvestigationPlan(
            plan_id=f"plan-{incident_id}",
            max_steps=4,
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
        # Reusing existing generic audit event types where reasonable
        mapping = {
            "pipeline_get_run": AuditEventType.EVIDENCE_COLLECTED,
            "pipeline_get_logs": AuditEventType.EVIDENCE_COLLECTED,
            "pipeline_get_current_schema": AuditEventType.EVIDENCE_COLLECTED,
            "pipeline_get_baseline_schema": AuditEventType.EVIDENCE_COLLECTED,
        }
        return mapping.get(tool_name, AuditEventType.EVIDENCE_COLLECTED)
