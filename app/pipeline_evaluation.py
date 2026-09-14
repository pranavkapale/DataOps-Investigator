from __future__ import annotations

import json
from typing import Any, Dict, List
from pathlib import Path

from pydantic import BaseModel, Field

from app.models import InvestigationReport


class PipelineEvaluationResult(BaseModel):
    scenario_id: str
    passed: bool
    root_cause_correct: bool
    evidence_coverage: float
    changed_field_correct: bool
    old_type_correct: bool
    new_type_correct: bool
    failure_reasons: List[str] = Field(default_factory=list)


class PipelineFailureEvaluator:
    """Evaluates an InvestigationReport against a pipeline failure expected_diagnosis.json contract."""

    @staticmethod
    def evaluate(report: InvestigationReport, contract: dict[str, Any]) -> PipelineEvaluationResult:
        reasons: List[str] = []
        
        # 1. Check root cause
        expected_root_cause = contract.get("root_cause")
        root_cause_correct = report.leading_hypothesis_id == expected_root_cause
        if not root_cause_correct:
            reasons.append(
                f"Expected leading hypothesis '{expected_root_cause}', "
                f"but got '{report.leading_hypothesis_id}'"
            )

        # 2. Check required evidence
        required_evidence_ids = contract.get("required_evidence", [])
        report_evidence_ids = {ev.evidence_id for ev in report.evidence}
        
        missing_evidence = [ev_id for ev_id in required_evidence_ids if ev_id not in report_evidence_ids]
        if missing_evidence:
            reasons.append(f"Missing required evidence IDs: {missing_evidence}")
            
        evidence_coverage = (
            (len(required_evidence_ids) - len(missing_evidence)) / len(required_evidence_ids) 
            if required_evidence_ids else 1.0
        )
        
        # 3. Check expected changed field and types
        expected_changed_field = contract.get("changed_field")
        expected_old_type = contract.get("old_type")
        expected_new_type = contract.get("new_type")
        
        changed_field_correct = False
        old_type_correct = False
        new_type_correct = False
        
        # We need to find this in the schema_drift evidence observation
        # "Schema drifted fields: customer_id (BIGINT->STRING)"
        schema_drift_ev = next((ev for ev in report.evidence if ev.evidence_id == "ev-schema-diff"), None)
        if schema_drift_ev:
            obs = schema_drift_ev.observation
            if expected_changed_field and expected_changed_field in obs:
                changed_field_correct = True
            else:
                reasons.append(f"Expected changed field '{expected_changed_field}' not found in evidence observation.")
                
            if expected_old_type and expected_new_type:
                expected_transition = f"({expected_old_type}->{expected_new_type})"
                if expected_transition in obs:
                    old_type_correct = True
                    new_type_correct = True
                else:
                    reasons.append(f"Expected type transition '{expected_transition}' not found in evidence observation.")
        else:
            if expected_changed_field or expected_old_type or expected_new_type:
                reasons.append("Schema drift evidence ('ev-schema-diff') not found, cannot verify fields/types.")
                
        passed = (
            root_cause_correct
            and len(missing_evidence) == 0
            and (not expected_changed_field or changed_field_correct)
            and (not expected_old_type or old_type_correct)
            and (not expected_new_type or new_type_correct)
        )

        return PipelineEvaluationResult(
            scenario_id=contract.get("scenario_id", "unknown"),
            passed=passed,
            root_cause_correct=root_cause_correct,
            evidence_coverage=evidence_coverage,
            changed_field_correct=changed_field_correct,
            old_type_correct=old_type_correct,
            new_type_correct=new_type_correct,
            failure_reasons=reasons,
        )

    @staticmethod
    def load_contract(scenario_dir: Path) -> dict[str, Any]:
        """Loads the evaluation contract. Fails clearly if missing/malformed."""
        eval_file = scenario_dir / "evaluation" / "expected_diagnosis.json"
        if not eval_file.exists():
            raise FileNotFoundError(f"Evaluation contract not found at {eval_file}")
        try:
            with open(eval_file, "r") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Malformed evaluation contract at {eval_file}: {e}") from e
