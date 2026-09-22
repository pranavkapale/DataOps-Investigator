from app.evidence_tools.data_quality import DataQualityEvidenceProvider
from app.investigation.data_quality_analysis import analyze_data_quality
from app.models import (
    Incident,
    InvestigationReport,
    InvestigationStatus,
    InvestigationType,
    InvestigationStep,
    InvestigationPlan,
    PlanStepStatus,
    Recommendation,
    RiskLevel,
    HypothesisStatus,
    AuditRecord,
    AuditEventType,
)

class DataQualityInvestigationOrchestrator:
    def __init__(self, provider: DataQualityEvidenceProvider):
        self.provider = provider

    def investigate(self, run_id: str) -> InvestigationReport:
        incident = Incident(
            incident_id=f"inc-{run_id}",
            title="Data quality anomaly detected",
            description=f"Investigating data quality for run {run_id}",
            investigation_type=InvestigationType.DATA_QUALITY
        )
        plan = InvestigationPlan(
            plan_id=f"plan-{run_id}",
            steps=[
                InvestigationStep(step_id="1", order=1, description="Collect run", status=PlanStepStatus.COMPLETED),
                InvestigationStep(step_id="2", order=2, description="Collect baseline", status=PlanStepStatus.COMPLETED),
                InvestigationStep(step_id="3", order=3, description="Analyze", status=PlanStepStatus.COMPLETED)
            ]
        )
        report = InvestigationReport(incident=incident, plan=plan, status=InvestigationStatus.PENDING)
        
        try:
            # Step 1: Collect Evidence
            incident_run = self.provider.get_run(run_id)
            baseline_run = self.provider.get_baseline(incident_run.dataset, incident_run.table)
            
            # Step 2: Analyze Evidence
            hypotheses, evidence = analyze_data_quality(incident_run, baseline_run)
            report.hypotheses = hypotheses
            
            # Step 3: Collect Evidence objects from hypotheses
            report.evidence.extend(evidence)
                
            # Step 4: Determine Leading Hypothesis
            supported = [h for h in hypotheses if h.status == HypothesisStatus.SUPPORTED]
            if supported:
                # Pick the highest confidence
                leading = max(supported, key=lambda h: h.heuristic_confidence or 0.0)
                report.leading_hypothesis_id = leading.hypothesis_id
                report.confidence = leading.heuristic_confidence
                
                # Step 5: Recommendations
                if leading.hypothesis_id == "INCOMPLETE_UPSTREAM_DATA":
                    report.recommendations.append(Recommendation(
                        recommendation_id="rec-dq-01",
                        description=f"Backfill the missing {len(incident_run.metrics.missing_partitions)} partitions.",
                        risk_level=RiskLevel.MEDIUM,
                        requires_approval=True
                    ))
                elif leading.hypothesis_id == "GENUINE_BUSINESS_DROP":
                    report.recommendations.append(Recommendation(
                        recommendation_id="rec-dq-02",
                        description="Data is complete. Investigate external business factors for revenue drop.",
                        risk_level=RiskLevel.LOW,
                        requires_approval=False
                    ))
            
            report.status = InvestigationStatus.COMPLETED
            
        except Exception as e:
            report.status = InvestigationStatus.FAILED
            report.audit_records.append(AuditRecord(
                record_id=f"audit-{run_id}-err",
                event_type=AuditEventType.REPORT_COMPLETED,
                actor="dq_orchestrator",
                success=False,
                details=str(e)
            ))
            
        return report
