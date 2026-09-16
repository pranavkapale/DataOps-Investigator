import json
from pathlib import Path
from typing import List

from app.evaluation_corpus import SCENARIO_2_CORPUS
from app.pipeline_evaluation import PipelineFailureEvaluator
from app.investigation.pipeline_agentic_workflow import PipelineAgenticInvestigationOrchestrator, PipelineInvestigationError
from app.models import AgenticEvaluationMetrics, InvestigationStatus

class PipelineAgenticScenarioEvaluator:
    def __init__(self, orchestrator: PipelineAgenticInvestigationOrchestrator, contract_path: Path):
        self.orchestrator = orchestrator
        with contract_path.open(encoding="utf-8") as f:
            self.contract = json.load(f)

    def evaluate_corpus(self, incident_run_id: str, corpus: List[str] = None) -> AgenticEvaluationMetrics:
        if corpus is None:
            corpus = SCENARIO_2_CORPUS
            
        total_cases = len(corpus)
        valid_plan_count = 0
        invalid_plan_count = 0
        planner_request_error_count = 0
        plan_validation_error_count = 0
        provider_error_count = 0
        investigation_error_count = 0
        unsafe_tool_count = 0
        duplicate_tool_count = 0
        successful_investigations = 0
        correct_root_cause_count = 0
        
        sum_evidence_coverage = 0.0
        sum_required_tool_coverage = 0.0

        for i, description in enumerate(corpus):
            print(f"\nEvaluating Case {i+1}: {description}")
            
            try:
                report = self.orchestrator.investigate(
                    incident_run_id=incident_run_id,
                    incident_description_override=description
                )
            except PipelineInvestigationError as e:
                # E.g. provider issues, unrecognized tools raising early, runtime failures
                print(f"--- DIAGNOSTIC: INVESTIGATION ERROR ---")
                print(f"Reason: {str(e)}")
                print(f"---------------------------------------")
                
                msg = str(e).lower()
                if "unauthorized tool" in msg:
                    invalid_plan_count += 1
                    plan_validation_error_count += 1
                    unsafe_tool_count += 1
                elif "duplicate" in msg or "unknown" in msg or "missing" in msg:
                    invalid_plan_count += 1
                    plan_validation_error_count += 1
                    if "duplicate" in msg:
                        duplicate_tool_count += 1
                else:
                    provider_error_count += 1
                continue
            except Exception as e:
                print(f"--- DIAGNOSTIC: UNHANDLED ERROR ---")
                print(f"Reason: {str(e)}")
                print(f"-----------------------------------")
                investigation_error_count += 1
                continue
                
            if report.status == InvestigationStatus.FAILED or report.status == InvestigationStatus.INSUFFICIENT_EVIDENCE:
                invalid_plan_count += 1
                failure_msg = ""
                for record in report.audit_records:
                    if record.details and ("Planner failed:" in record.details or "Plan is missing" in record.details or "unauthorized" in record.details):
                        failure_msg = record.details
                        break
                        
                print(f"--- DIAGNOSTIC: PLAN FAILED ---")
                print(f"Reason: {failure_msg}")
                print(f"-------------------------------")
                
                if "unauthorized tool" in failure_msg:
                    plan_validation_error_count += 1
                    unsafe_tool_count += 1
                elif "duplicate tool" in failure_msg:
                    plan_validation_error_count += 1
                    duplicate_tool_count += 1
                elif "missing required tool" in failure_msg or "unknown tool" in failure_msg:
                    plan_validation_error_count += 1
                elif "Planner failed:" in failure_msg:
                    if "unauthorized" in failure_msg or "duplicate" in failure_msg or "missing" in failure_msg:
                        plan_validation_error_count += 1
                    else:
                        planner_request_error_count += 1
                else:
                    investigation_error_count += 1
            else:
                valid_plan_count += 1
                sum_required_tool_coverage += 1.0
                
                # Check deterministic evaluation
                eval_result = PipelineFailureEvaluator.evaluate(report, self.contract)
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
            planner_request_error_count=planner_request_error_count,
            plan_validation_error_count=plan_validation_error_count,
            provider_error_count=provider_error_count,
            investigation_error_count=investigation_error_count,
            required_tool_coverage=required_tool_coverage,
            unsafe_tool_count=unsafe_tool_count,
            duplicate_tool_count=duplicate_tool_count,
            successful_investigations=successful_investigations,
            correct_root_cause_count=correct_root_cause_count,
            root_cause_accuracy=root_cause_accuracy,
            evidence_coverage=evidence_coverage
        )
