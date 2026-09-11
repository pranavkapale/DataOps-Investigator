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

SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios" / "spark_performance"
EVALUATION_PATH = SCENARIO_DIR / "evaluation" / "expected_diagnosis.json"
INCIDENT_RUN_ID = "run-customer-aggregation-2026-08-28"

def main():
    api_key = os.getenv("LLM_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        print("Error: LLM_API_KEY environment variable is not set or is invalid.")
        print("This script requires a real LLM to evaluate the agentic path.")
        sys.exit(1)
        
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    base_url = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
    
    print(f"Initializing LLMClient with model: {model}")
    llm_client = LLMClient(api_key=api_key, api_base=base_url, model=model)
    planner = InvestigationPlanner(llm_client)
    provider = SparkFixtureEvidenceProvider(SCENARIO_DIR)
    orchestrator = SparkAgenticInvestigationOrchestrator(provider, planner)
    
    evaluator = AgenticScenarioEvaluator(orchestrator, EVALUATION_PATH)
    
    print("\nRunning Agentic Scenario 1 Evaluation Corpus against real LLM...")
    metrics = evaluator.evaluate_corpus(INCIDENT_RUN_ID)
    
    print("\n--- Evaluation Results ---")
    print(metrics.model_dump_json(indent=2))
    
    if metrics.invalid_plan_count > 0:
        print("\nWARNING: Some plans were invalid.")
    if metrics.root_cause_accuracy < 1.0:
        print("\nWARNING: Root cause accuracy is not 100%.")

if __name__ == "__main__":
    main()
