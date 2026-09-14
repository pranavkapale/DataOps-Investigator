from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from app.evidence_tools.pipeline import (
    PipelineEvidenceProvider,
    PipelineRunTelemetry,
    PipelineLogTelemetry,
    SchemaTelemetry,
    SchemaField
)
from app.models import Evidence, EvidenceKind, Hypothesis, HypothesisStatus, InvestigationStatus

class FieldChange(BaseModel):
    baseline_type: str
    current_type: str

class PipelineFailureMetrics(BaseModel):
    schema_changed: bool = False
    changed_fields: Dict[str, FieldChange] = Field(default_factory=dict)
    log_indicates_schema_mismatch: bool = False
    mismatched_field_in_log: Optional[str] = None
    log_mismatch_corresponds_to_schema_diff: bool = False

class PipelineFailureFindings(BaseModel):
    incident_run_id: str
    metrics: PipelineFailureMetrics
    evidence: List[Evidence]
    hypotheses: List[Hypothesis]
    status: InvestigationStatus
    leading_hypothesis_id: Optional[str] = None

class PipelineHypothesisEvaluator:
    @staticmethod
    def evaluate(metrics: PipelineFailureMetrics) -> List[Hypothesis]:
        hypotheses = []
        
        # SCHEMA_DRIFT Hypothesis
        schema_drift_supported = metrics.log_mismatch_corresponds_to_schema_diff
        
        if schema_drift_supported:
            status = HypothesisStatus.SUPPORTED
            rationale = (
                f"Failure log indicates a schema mismatch on field '{metrics.mismatched_field_in_log}', "
                "which matches the detected difference between the baseline and current schemas."
            )
        elif metrics.schema_changed and metrics.log_indicates_schema_mismatch:
            # Different field or unparsable field in log
            status = HypothesisStatus.INCONCLUSIVE
            rationale = "Schema changed and log indicates mismatch, but fields do not explicitly correlate."
        else:
            status = HypothesisStatus.REJECTED
            rationale = "No evidence of schema drift correlating with the failure log."

        hypotheses.append(
            Hypothesis(
                hypothesis_id="SCHEMA_DRIFT",
                name="Schema Drift",
                description="The pipeline failed because the upstream schema changed, causing a type mismatch.",
                status=status,
                rationale=rationale,
                supporting_evidence_ids=["ev-schema-diff", "ev-log-mismatch"] if schema_drift_supported else [],
                contradicting_evidence_ids=[]
            )
        )
        
        # UNKNOWN_PIPELINE_FAILURE Hypothesis
        if status == HypothesisStatus.SUPPORTED:
            unknown_status = HypothesisStatus.REJECTED
            unknown_rationale = "A specific root cause (Schema Drift) was identified."
        else:
            unknown_status = HypothesisStatus.INCONCLUSIVE
            unknown_rationale = "No specific root cause could be definitively proven with available evidence."
            
        hypotheses.append(
            Hypothesis(
                hypothesis_id="UNKNOWN_PIPELINE_FAILURE",
                name="Unknown Pipeline Failure",
                description="The pipeline failed for an unknown reason.",
                status=unknown_status,
                rationale=unknown_rationale,
                supporting_evidence_ids=[],
                contradicting_evidence_ids=[]
            )
        )
        
        return hypotheses

class PipelineFailureAnalyzer:
    """Derives deterministic Scenario 2 findings from factual Pipeline telemetry."""
    
    def analyze(self, provider: PipelineEvidenceProvider, incident_run_id: str) -> PipelineFailureFindings:
        try:
            run = provider.get_run(incident_run_id)
        except Exception:
            return self._insufficient_evidence(incident_run_id, "Could not load pipeline run telemetry.")
            
        try:
            logs = provider.get_logs(incident_run_id, run.failed_task or "unknown")
        except Exception:
            logs = None

        # For the MVP, dataset and table are hardcoded or ignored by the fixture provider
        try:
            current_schema = provider.get_current_schema("default", "default")
            baseline_schema = provider.get_baseline_schema("default", "default")
        except Exception:
            current_schema = None
            baseline_schema = None

        if not current_schema or not baseline_schema or not logs:
            return self._insufficient_evidence(
                incident_run_id, "Missing required telemetry (schemas or logs)."
            )

        metrics = self._derive_metrics(current_schema, baseline_schema, logs)
        evidence = self._build_evidence(metrics)
        hypotheses = PipelineHypothesisEvaluator.evaluate(metrics)
        
        leading = None
        for h in hypotheses:
            if h.status == HypothesisStatus.SUPPORTED:
                leading = h.hypothesis_id
                break
                
        return PipelineFailureFindings(
            incident_run_id=incident_run_id,
            metrics=metrics,
            evidence=evidence,
            hypotheses=hypotheses,
            status=InvestigationStatus.COMPLETED,
            leading_hypothesis_id=leading
        )
        
    def _insufficient_evidence(self, run_id: str, reason: str) -> PipelineFailureFindings:
        return PipelineFailureFindings(
            incident_run_id=run_id,
            metrics=PipelineFailureMetrics(),
            evidence=[],
            hypotheses=[
                Hypothesis(
                    hypothesis_id="INSUFFICIENT_EVIDENCE",
                    name="Insufficient Evidence",
                    description="Could not perform analysis.",
                    status=HypothesisStatus.INCONCLUSIVE,
                    rationale=reason
                )
            ],
            status=InvestigationStatus.FAILED
        )

    def _derive_metrics(
        self, current: SchemaTelemetry, baseline: SchemaTelemetry, logs: PipelineLogTelemetry
    ) -> PipelineFailureMetrics:
        metrics = PipelineFailureMetrics()
        
        # 1 & 2 & 3. Compare schemas
        baseline_fields = {f.name: f.type for f in baseline.fields}
        current_fields = {f.name: f.type for f in current.fields}
        
        for name, current_type in current_fields.items():
            baseline_type = baseline_fields.get(name)
            if baseline_type and baseline_type != current_type:
                metrics.schema_changed = True
                metrics.changed_fields[name] = FieldChange(
                    baseline_type=baseline_type, current_type=current_type
                )
                
        # 4. Check logs for schema/type mismatch
        log_text = logs.log_content.lower()
        if "type mismatch" in log_text or "schema mismatch" in log_text or "expected" in log_text:
            metrics.log_indicates_schema_mismatch = True
            
            # 5. Extract field if possible
            import re
            match = re.search(r"field '([^']+)'", logs.log_content)
            if match:
                metrics.mismatched_field_in_log = match.group(1)
                if metrics.mismatched_field_in_log in metrics.changed_fields:
                    metrics.log_mismatch_corresponds_to_schema_diff = True
                    
        return metrics

    def _build_evidence(self, metrics: PipelineFailureMetrics) -> List[Evidence]:
        evidence = []
        
        if metrics.schema_changed:
            changed_str = ", ".join(
                f"{k} ({v.baseline_type}->{v.current_type})" 
                for k, v in metrics.changed_fields.items()
            )
            evidence.append(
                Evidence(
                    evidence_id="ev-schema-diff",
                    source="schema_comparison",
                    observation=f"Schema drifted fields: {changed_str}",
                    kind=EvidenceKind.DERIVED,
                    derived_metric_name="schema_drift",
                    derived_metric_value=True
                )
            )
            
        if metrics.log_indicates_schema_mismatch:
            evidence.append(
                Evidence(
                    evidence_id="ev-log-mismatch",
                    source="pipeline_logs",
                    observation=f"Logs indicate a type mismatch in field '{metrics.mismatched_field_in_log}'",
                    kind=EvidenceKind.OBSERVED
                )
            )
            
        return evidence
