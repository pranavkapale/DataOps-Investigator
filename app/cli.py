import argparse
import sys
from pathlib import Path

import uvicorn

from .ingestion import build_chunks
from .vector_store import get_vector_store
from .rag_pipeline import answer_question

from .evidence_tools.spark import SparkFixtureEvidenceProvider, UnknownSparkRunError, SparkEvidenceProviderError
from .investigation.spark_performance_workflow import SparkPerformanceInvestigationOrchestrator, SparkInvestigationError

def cmd_investigate(investigation_type: str, run_id: str, json_output: bool):
    if investigation_type != "spark_performance":
        print(f"Error: Unknown investigation type '{investigation_type}'. Only 'spark_performance' is currently supported.", file=sys.stderr)
        sys.exit(1)

    scenario_dir = Path(__file__).resolve().parent.parent / "scenarios" / "spark_performance"

    try:
        provider = SparkFixtureEvidenceProvider(scenario_dir)
        orchestrator = SparkPerformanceInvestigationOrchestrator(provider)
        report = orchestrator.investigate(run_id)

        if json_output:
            print(report.model_dump_json(indent=2))
        else:
            print(f"Incident: {report.incident.title}")
            print(f"Run ID: {run_id}")
            print(f"Status: {report.status.value}")

            if report.leading_hypothesis_id:
                leading = next((h for h in report.hypotheses if h.hypothesis_id == report.leading_hypothesis_id), None)
                if leading:
                    conf = f" (Confidence: {leading.heuristic_confidence:.2f})" if leading.heuristic_confidence else ""
                    print(f"\nLeading Root Cause: {leading.name}{conf}")
                    print(f"Rationale: {leading.rationale}")

            print("\nKey Evidence (Derived Metrics):")
            for ev in report.evidence:
                if ev.derived_metric_name and ev.derived_metric_value is not None:
                    val = f"{ev.derived_metric_value:.2f}" if isinstance(ev.derived_metric_value, float) else str(ev.derived_metric_value)
                    print(f"- {ev.derived_metric_name}: {val}")

            print("\nHypotheses Summary:")
            for h in report.hypotheses:
                print(f"- {h.name}: {h.status.value}")

            if report.recommendations:
                print("\nRecommendations:")
                for rec in report.recommendations:
                    print(f"- {rec.description} (Risk: {rec.risk_level.value})")

            print(f"\nAudit Events: {len(report.audit_records)} recorded")

    except (UnknownSparkRunError, SparkEvidenceProviderError, SparkInvestigationError) as exc:
        print(f"Investigation Error: {exc}", file=sys.stderr)
        sys.exit(1)

def cmd_build_index():
    print("Building index...")
    chunks = build_chunks()
    store = get_vector_store()
    store.build(chunks)
    print(f"Indexed {len(chunks)} chunks.")

def cmd_ask(question: str):
    answer, metas = answer_question(question)
    print("\nAnswer:\n")
    print(answer)
    print("\nSources:")
    for m in metas:
        print(f"- {m.source} (chunk {m.chunk_id})")

def cmd_serve(host: str = "0.0.0.0", port: int = 8000):
    uvicorn.run("app.api:app", host=host, port=port, reload=False)

def main():
    parser = argparse.ArgumentParser(description="DevDocs RAG Assistant")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("build-index")
    ask_p = sub.add_parser("ask")
    ask_p.add_argument("question", type=str)
    serve_p = sub.add_parser("serve")
    serve_p.add_argument("--host", type=str, default="0.0.0.0")
    serve_p.add_argument("--port", type=int, default=8000)

    investigate_p = sub.add_parser("investigate")
    investigate_p.add_argument("investigation_type", type=str)
    investigate_p.add_argument("run_id", type=str)
    investigate_p.add_argument("--json", action="store_true")

    args = parser.parse_args()
    if args.command == "build-index":
        cmd_build_index()
    elif args.command == "ask":
        cmd_ask(args.question)
    elif args.command == "serve":
        cmd_serve(args.host, args.port)
    elif args.command == "investigate":
        cmd_investigate(args.investigation_type, args.run_id, args.json)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
