import argparse
import sys
from pathlib import Path


from .evidence_tools.spark import SparkFixtureEvidenceProvider, UnknownSparkRunError, SparkEvidenceProviderError
from .investigation.spark_performance_workflow import SparkPerformanceInvestigationOrchestrator, SparkInvestigationError
from .evidence_tools.spark_mcp import SparkMCPEvidenceProvider
from .investigation.agentic_workflow import SparkAgenticInvestigationOrchestrator
from .evidence_tools.pipeline import PipelineFixtureEvidenceProvider, UnknownPipelineRunError, PipelineEvidenceProviderError
from .investigation.pipeline_failure_workflow import PipelineFailureInvestigationOrchestrator, PipelineInvestigationError
from .evidence_tools.pipeline_mcp import PipelineMCPEvidenceProvider
from .investigation.pipeline_agentic_workflow import PipelineAgenticInvestigationOrchestrator
from .investigation.planner import InvestigationPlanner, InvestigationPlannerError
from .llm_client import LLMClient, LLMClientError
from .models import InvestigationStatus

def cmd_investigate(investigation_type: str, run_id: str, json_output: bool, agentic: bool):
    if investigation_type not in ["spark_performance", "pipeline_failure", "data_quality", "sql_regression"]:
        print(f"Error: Unknown investigation type '{investigation_type}'.", file=sys.stderr)
        sys.exit(1)

    scenario_dir = Path(__file__).resolve().parent.parent / "scenarios" / investigation_type

    try:
        if investigation_type == "pipeline_failure":
            if agentic:
                llm_client = LLMClient()
                planner = InvestigationPlanner(llm_client)
                with PipelineMCPEvidenceProvider() as provider:
                    orchestrator = PipelineAgenticInvestigationOrchestrator(provider, planner)
                    report = orchestrator.investigate(run_id)
            else:
                provider = PipelineFixtureEvidenceProvider(scenario_dir)
                orchestrator = PipelineFailureInvestigationOrchestrator(provider)
                report = orchestrator.investigate(run_id)
        elif investigation_type == "data_quality":
            from .evidence_tools.data_quality import DataQualityFixtureEvidenceProvider
            from .investigation.data_quality_workflow import DataQualityInvestigationOrchestrator
            provider = DataQualityFixtureEvidenceProvider(scenario_dir)
            orchestrator = DataQualityInvestigationOrchestrator(provider)
            report = orchestrator.investigate(run_id)
        elif investigation_type == "sql_regression":
            from .evidence_tools.sql_regression import SQLFixtureEvidenceProvider
            from .investigation.sql_regression_workflow import SQLRegressionInvestigationOrchestrator
            provider = SQLFixtureEvidenceProvider(scenario_dir)
            orchestrator = SQLRegressionInvestigationOrchestrator(provider)
            report = orchestrator.investigate(run_id)
        else: # spark_performance
            if agentic:
                llm_client = LLMClient()
                planner = InvestigationPlanner(llm_client)
                with SparkMCPEvidenceProvider() as provider:
                    orchestrator = SparkAgenticInvestigationOrchestrator(provider, planner)
                    report = orchestrator.investigate(run_id)
            else:
                provider = SparkFixtureEvidenceProvider(scenario_dir)
                orchestrator = SparkPerformanceInvestigationOrchestrator(provider)
                report = orchestrator.investigate(run_id)

        if json_output:
            print(report.model_dump_json(indent=2))
        else:
            mode_str = "Agentic (via LLM & MCP)" if agentic else "Deterministic"
            print(f"Investigation Mode: {mode_str}")
            print(f"Investigation Type: {investigation_type}")
            print(f"Incident: {report.incident.title}")
            print(f"Run ID: {run_id}")
            print(f"Status: {report.status.value}")

            if agentic and report.plan and report.plan.steps:
                print("\nPLANNED TOOLS:")
                for step in report.plan.steps:
                    print(f"- {step.description}")
            
            print("\nACTUAL EVIDENCE:")
            for ev in report.evidence:
                if investigation_type == "pipeline_failure" and ev.evidence_id == "ev-schema-diff":
                    print(f"- {ev.observation}")
                elif ev.derived_metric_name and ev.derived_metric_value is not None:
                    val = f"{ev.derived_metric_value:.2f}" if isinstance(ev.derived_metric_value, float) else str(ev.derived_metric_value)
                    print(f"- {ev.derived_metric_name}: {val}")

            if report.leading_hypothesis_id:
                leading = next((h for h in report.hypotheses if h.hypothesis_id == report.leading_hypothesis_id), None)
                if leading:
                    conf = f" (Confidence: {leading.heuristic_confidence:.2f})" if leading.heuristic_confidence else ""
                    print(f"\nLeading Root Cause: {leading.name}{conf}")
                    print(f"Rationale: {leading.rationale}")

            print("\nHypotheses Summary:")
            for h in report.hypotheses:
                print(f"- {h.name}: {h.status.value}")

            if report.recommendations:
                print("\nRecommendations:")
                for rec in report.recommendations:
                    print(f"- {rec.description} (Risk: {rec.risk_level.value})")

            print(f"\nAudit Events: {len(report.audit_records)} recorded")

        if report.status == InvestigationStatus.FAILED:
            if report.audit_records:
                print(f"\nInvestigation Failed: {report.audit_records[-1].details}")
            sys.exit(1)

    except Exception as exc:
        print(f"Investigation Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except (LLMClientError, InvestigationPlannerError) as exc:
        print(f"Agentic Planning Error: {exc}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="DevDocs RAG Assistant")
    sub = parser.add_subparsers(dest="command")

    investigate_p = sub.add_parser("investigate")
    investigate_p.add_argument("investigation_type", type=str)
    investigate_p.add_argument("run_id", type=str)
    investigate_p.add_argument("--json", action="store_true")
    investigate_p.add_argument("--agentic", action="store_true", help="Use agentic workflow with LLM and MCP")

    args = parser.parse_args()
    if args.command == "investigate":
        cmd_investigate(args.investigation_type, args.run_id, args.json, args.agentic)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
