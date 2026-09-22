from app.evidence_tools.sql_regression import SQLEvidenceProvider
from app.investigation.sql_regression_analysis import analyze_sql_regression
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

class SQLRegressionInvestigationOrchestrator:
    def __init__(self, provider: SQLEvidenceProvider):
        self.provider = provider

    def investigate(self, run_id: str) -> InvestigationReport:
        incident = Incident(
            incident_id=f"inc-{run_id}",
            title="SQL query performance regression",
            description=f"Investigating SQL query {run_id}",
            investigation_type=InvestigationType.SQL_REGRESSION
        )
        plan = InvestigationPlan(
            plan_id=f"plan-{run_id}",
            steps=[
                InvestigationStep(step_id="1", order=1, description="Collect query plan", status=PlanStepStatus.COMPLETED),
                InvestigationStep(step_id="2", order=2, description="Collect baseline plan", status=PlanStepStatus.COMPLETED),
                InvestigationStep(step_id="3", order=3, description="Analyze", status=PlanStepStatus.COMPLETED)
            ]
        )
        report = InvestigationReport(incident=incident, plan=plan, status=InvestigationStatus.PENDING)
        
        try:
            # Step 1: Collect Evidence
            incident_run = self.provider.get_query(run_id)
            baseline_run = self.provider.get_baseline_query()
            
            # Step 2: Analyze Evidence
            hypotheses, evidence = analyze_sql_regression(incident_run, baseline_run)
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
                if leading.hypothesis_id == "JOIN_CARDINALITY_EXPLOSION":
                    report.recommendations.append(Recommendation(
                        recommendation_id="rec-sql-01",
                        description="Review the JOIN conditions for missing keys or many-to-many explosions. Add appropriate filters or distinct logic.",
                        risk_level=RiskLevel.MEDIUM,
                        requires_approval=True
                    ))
            
            report.status = InvestigationStatus.COMPLETED
            
        except Exception as e:
            report.status = InvestigationStatus.FAILED
            report.audit_records.append(AuditRecord(
                record_id=f"audit-{run_id}-err",
                event_type=AuditEventType.REPORT_COMPLETED,
                actor="sql_orchestrator",
                success=False,
                details=str(e)
            ))
            
        return report
