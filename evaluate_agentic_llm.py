import os
import sys
from pathlib import Path

# Ensure the root of the project is in PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.agentic_evaluation import AgenticScenarioEvaluator
from app.evidence_tools.spark import SparkFixtureEvidenceProvider
from app.investigation.agentic_workflow import SparkAgenticInvestigationOrchestrator
from app.investigation.planner import InvestigationPlanner
from app.llm_client import LLMClient

# Scenario 2 Imports
from app.pipeline_agentic_evaluation import PipelineAgenticScenarioEvaluator
from app.evidence_tools.pipeline_mcp import PipelineMCPEvidenceProvider
from app.investigation.pipeline_agentic_workflow import PipelineAgenticInvestigationOrchestrator

SCENARIO_1_DIR = Path(__file__).resolve().parent / "scenarios" / "spark_performance"
SCENARIO_1_EVAL_PATH = SCENARIO_1_DIR / "evaluation" / "expected_diagnosis.json"
INCIDENT_1_RUN_ID = "run-customer-aggregation-2026-08-28"

SCENARIO_2_DIR = Path(__file__).resolve().parent / "scenarios" / "pipeline_failure"
SCENARIO_2_EVAL_PATH = SCENARIO_2_DIR / "evaluation" / "expected_diagnosis.json"
INCIDENT_2_RUN_ID = "run-customer-daily-2026-09-12"

def main():
    api_key = os.getenv("LLM_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        print("Error: LLM_API_KEY environment variable is not set or is invalid.")
        print("This script requires a real LLM to evaluate the agentic path.")
        sys.exit(1)
        
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    base_url = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
    scenario = os.getenv("SCENARIO", "1")
    
    print(f"Initializing LLMClient with model: {model}")
    llm_client = LLMClient(api_key=api_key, api_base=base_url, model=model)
    planner = InvestigationPlanner(llm_client)

    if scenario == "2":
        print("\nRunning Agentic Scenario 2 (Pipeline Failure) Evaluation Corpus against real LLM...")
        provider = PipelineMCPEvidenceProvider()
        orchestrator = PipelineAgenticInvestigationOrchestrator(provider, planner)
        evaluator = PipelineAgenticScenarioEvaluator(orchestrator, SCENARIO_2_EVAL_PATH)
        metrics = evaluator.evaluate_corpus(INCIDENT_2_RUN_ID)
    else:
        print("\nRunning Agentic Scenario 1 (Spark Performance) Evaluation Corpus against real LLM...")
        provider = SparkFixtureEvidenceProvider(SCENARIO_1_DIR)
        orchestrator = SparkAgenticInvestigationOrchestrator(provider, planner)
        evaluator = AgenticScenarioEvaluator(orchestrator, SCENARIO_1_EVAL_PATH)
        metrics = evaluator.evaluate_corpus(INCIDENT_1_RUN_ID)
    
    print("\n--- Evaluation Results ---")
    print(metrics.model_dump_json(indent=2))
    
    if metrics.invalid_plan_count > 0:
        print("\nWARNING: Some plans were invalid.")
    if metrics.root_cause_accuracy < 1.0:
        print("\nWARNING: Root cause accuracy is not 100%.")

if __name__ == "__main__":
    main()
