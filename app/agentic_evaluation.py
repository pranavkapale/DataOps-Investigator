import json
from pathlib import Path
from typing import List, Dict, Any

from app.evaluation_corpus import SCENARIO_1_CORPUS
from app.evaluation import ScenarioEvaluator
from app.investigation.agentic_workflow import SparkAgenticInvestigationOrchestrator
from app.models import AgenticEvaluationMetrics, InvestigationStatus

class AgenticScenarioEvaluator:
    def __init__(self, orchestrator: SparkAgenticInvestigationOrchestrator, contract_path: Path):
        self.orchestrator = orchestrator
        with contract_path.open(encoding="utf-8") as f:
            self.contract = json.load(f)

    def evaluate_corpus(self, incident_run_id: str, corpus: List[str] = SCENARIO_1_CORPUS) -> AgenticEvaluationMetrics:
        total_cases = len(corpus)
        valid_plan_count = 0
        invalid_plan_count = 0
        unsafe_tool_count = 0
        duplicate_tool_count = 0
        successful_investigations = 0
        correct_root_cause_count = 0
        
        sum_evidence_coverage = 0.0
        sum_required_tool_coverage = 0.0

        for i, description in enumerate(corpus):
            print(f"\nEvaluating Case {i+1}: {description}")
            report = self.orchestrator.investigate(
                incident_run_id=incident_run_id,
                incident_description_override=description
            )
            
            # Since the plan validates successfully if it has all 5 required tools,
            # required_tool_coverage is 1.0 for valid plans and 0.0 or partial for invalid.
            # But wait, if the plan is rejected, we don't have a plan. 
            # If report.status == FAILED, we look at audit records.
            if report.status == InvestigationStatus.FAILED:
                invalid_plan_count += 1
                failure_msg = ""
                for record in report.audit_records:
                    if "Planner failed:" in (record.details or ""):
                        failure_msg = record.details
                        break
                        
                if "unauthorized tool" in failure_msg:
                    unsafe_tool_count += 1
                elif "duplicate tool" in failure_msg:
                    duplicate_tool_count += 1
                print(f"--- DIAGNOSTIC: PLAN FAILED ---")
                print(f"Reason: {failure_msg}")
                print(f"-------------------------------")
                # If it failed due to missing tools, required tool coverage is technically < 1.0.
                # For simplicity, if it failed, it gets 0.0 required tool coverage for this iteration.
            else:
                valid_plan_count += 1
                sum_required_tool_coverage += 1.0 # The strict validation guarantees 100% coverage
                
                # Check deterministic evaluation
                eval_result = ScenarioEvaluator.evaluate(report, self.contract)
                if eval_result.passed:
                    successful_investigations += 1
                if eval_result.root_cause_correct:
                    correct_root_cause_count += 1
                    
                sum_evidence_coverage += eval_result.evidence_coverage

        root_cause_accuracy = correct_root_cause_count / valid_plan_count if valid_plan_count > 0 else 0.0
        evidence_coverage = sum_evidence_coverage / valid_plan_count if valid_plan_count > 0 else 0.0
        required_tool_coverage = sum_required_tool_coverage / total_cases

        return AgenticEvaluationMetrics(
            total_cases=total_cases,
            valid_plan_count=valid_plan_count,
            invalid_plan_count=invalid_plan_count,
            required_tool_coverage=required_tool_coverage,
            unsafe_tool_count=unsafe_tool_count,
            duplicate_tool_count=duplicate_tool_count,
            successful_investigations=successful_investigations,
            correct_root_cause_count=correct_root_cause_count,
            root_cause_accuracy=root_cause_accuracy,
            evidence_coverage=evidence_coverage
        )
