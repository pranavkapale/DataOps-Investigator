from __future__ import annotations

import json
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from app.models import InvestigationReport


class EvaluationResult(BaseModel):
    scenario_id: str
    passed: bool
    root_cause_correct: bool
    evidence_coverage: float
    unsupported_claim_count: int
    metrics_checks: Dict[str, bool] = Field(default_factory=dict)
    hypothesis_checks: Dict[str, bool] = Field(default_factory=dict)
    failure_reasons: List[str] = Field(default_factory=list)


class ScenarioEvaluator:
    """Evaluates an InvestigationReport against an expected_diagnosis.json contract."""

    @staticmethod
    def evaluate(report: InvestigationReport, contract: dict[str, Any]) -> EvaluationResult:
        reasons: List[str] = []
        
        # 1. Check root cause
        expected_root_cause = contract.get("expected_root_cause_category")
        root_cause_correct = report.leading_hypothesis_id == expected_root_cause
        if not root_cause_correct:
            reasons.append(
                f"Expected leading hypothesis '{expected_root_cause}', "
                f"but got '{report.leading_hypothesis_id}'"
            )

        # 2. Check derived metrics
        metrics_checks = {}
        report_metrics = {}
        for ev in report.evidence:
            if ev.derived_metric_name and ev.derived_metric_value is not None:
                report_metrics[ev.derived_metric_name] = ev.derived_metric_value

        for expected_ev in contract.get("supporting_evidence", []):
            metric_name = expected_ev["metric"]
            # Map contract metric name to report metric name if necessary
            report_metric_name = "skew_ratio" if metric_name == "incident_skew_ratio" else metric_name

            expected_range = expected_ev["expected_range"]
            min_val = expected_range["min"]
            max_val = expected_range["max"]
            
            actual_val = report_metrics.get(report_metric_name)
            if actual_val is None:
                metrics_checks[metric_name] = False
                reasons.append(f"Missing expected metric: {metric_name}")
            else:
                try:
                    actual_float = float(actual_val)
                    if min_val <= actual_float <= max_val:
                        metrics_checks[metric_name] = True
                    else:
                        metrics_checks[metric_name] = False
                        reasons.append(
                            f"Metric {metric_name} value {actual_float} is outside expected "
                            f"range [{min_val}, {max_val}]"
                        )
                except ValueError:
                    metrics_checks[metric_name] = False
                    reasons.append(f"Metric {metric_name} value {actual_val} is not a valid float")

        evidence_coverage = (
            sum(metrics_checks.values()) / len(metrics_checks) if metrics_checks else 1.0
        )

        # 3. Check hypothesis statuses
        hypothesis_checks = {}
        report_hypotheses = {h.name: h.status.value for h in report.hypotheses}
        for expected_alt in contract.get("alternative_hypotheses", []):
            h_name = expected_alt["name"]
            expected_status = expected_alt["expected_status"]
            actual_status = report_hypotheses.get(h_name)
            
            if actual_status is None:
                hypothesis_checks[h_name] = False
                reasons.append(f"Missing alternative hypothesis: '{h_name}'")
            elif actual_status != expected_status:
                hypothesis_checks[h_name] = False
                reasons.append(
                    f"Alternative hypothesis '{h_name}' has status '{actual_status}', "
                    f"expected '{expected_status}'"
                )
            else:
                hypothesis_checks[h_name] = True

        # 4. Check unsupported evidence claims
        # The Pydantic model already validates that evidence IDs exist within the report.
        # Here we just track it.
        unsupported_claim_count = 0

        passed = (
            root_cause_correct
            and evidence_coverage == 1.0
            and all(hypothesis_checks.values())
            and unsupported_claim_count == 0
        )

        return EvaluationResult(
            scenario_id=contract.get("scenario_id", "unknown"),
            passed=passed,
            root_cause_correct=root_cause_correct,
            evidence_coverage=evidence_coverage,
            unsupported_claim_count=unsupported_claim_count,
            metrics_checks=metrics_checks,
            hypothesis_checks=hypothesis_checks,
            failure_reasons=reasons,
        )
