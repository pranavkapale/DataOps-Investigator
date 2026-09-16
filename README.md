# DataOps Investigator

> An evidence-driven AI agent for investigating, diagnosing, and optimizing data systems.

DataOps Investigator is a bounded, evidence-first AI troubleshooting agent for data engineers. Unlike generic chatbots or speculative autonomous agents, it operates on a strict principle:

**The model plans. Tools collect facts. Deterministic analyzers diagnose.**

## The Problem

Data engineers frequently face sudden, opaque incidents in their data platforms:
- *"Why did this Spark job suddenly become 4× slower?"*
- *"Why did this pipeline fail overnight?"*

Investigating these incidents typically requires manually correlating job metadata, stage metrics, shuffle sizes, configuration drifts, execution logs, and schema histories against a healthy baseline.

**DataOps Investigator** automates this workflow by treating data engineering incidents as a structured investigation, systematically gathering evidence before rendering a diagnosis.

---

## What the System Does

A DataOps investigation follows a strict lifecycle to prevent LLM hallucination and ensure auditability:

```text
Incident Reported
    ↓
Investigation Plan (LLM)
    ↓
Evidence Collection (MCP Tools)
    ↓
Deterministic Analysis
    ↓
Hypothesis Evaluation
    ↓
Evidence-Backed Diagnosis
    ↓
Recommendations
    ↓
Audit Trail
```

Every final diagnosis is traceable directly to empirical evidence retrieved from the underlying data systems.

---

## Architecture

The project cleanly separates agentic orchestration from diagnostic inference. 

```mermaid
flowchart TD
    User([User / CLI]) --> Orchestrator
    
    subgraph Agentic Orchestration
    Orchestrator[Agentic Orchestrator]
    Planner[Scenario-Aware Planner\n(LLM)]
    
    Orchestrator <--> Planner
    end
    
    subgraph Evidence Acquisition
    MCP[MCP Server]
    Provider[Typed Evidence Provider]
    
    Orchestrator -->|Calls Approved Tools| Provider
    Provider <-->|MCP Transport| MCP
    MCP -->|Fetches Runtime Facts| TargetSystem[(Target Systems)]
    end
    
    subgraph Diagnostic Inference
    Analyzer[Deterministic Analyzer]
    Report[Investigation Report\n+ Hypotheses]
    
    Orchestrator -->|Passes Collected Evidence| Analyzer
    Analyzer --> Report
    end
    
    Report --> Eval[Evaluation Harness]
```
*(In deterministic mode, the LLM planner is bypassed entirely, and a fixed scenario evidence fixture is fed directly into the analyzer.)*

---

## Core Design Principle

**LLM ≠ Source of Truth.**

The biggest risk in data engineering AI is a system that confidently hallucinates root causes without evidence. To solve this, responsibilities are strictly segregated:

1. **Planner:** Decides *what* approved evidence should be collected based on the incident context.
2. **Evidence Provider:** Connects to systems (via MCP) and returns typed, runtime facts.
3. **Analyzer:** Contains the actual diagnostic logic. It applies deterministic, domain-specific rules to the evidence.
4. **Evaluator:** Checks whether the final diagnosis and plan match the expected scenario contract in the testing suite.

---

## Supported Scenarios

| Scenario | Investigated Evidence | Demonstrated Root Cause |
| :--- | :--- | :--- |
| **Spark Performance Regression** | Runtime regression, input growth, partition skew ratios, shuffle growth, memory spills, configuration changes. | `DATA_SKEW` |
| **Pipeline Failure / Schema Drift** | Failed run metadata, failure logs, current schema, historical baseline schema. | `SCHEMA_DRIFT`<br>(`customer_id: BIGINT → STRING`) |

*Note on Pipeline Failure: The system explicitly refuses to diagnose "Upstream Schema Drift" because the evidence only proves the schema changed locally; it does not contain upstream provenance to definitively attribute the root cause further up the DAG.*

---

## Execution Modes

The Investigator supports two distinct execution paths, both of which share the exact same domain models, analyzers, and outputs.

### Deterministic Mode
```text
Fixed Bounded Plan → Fixture Provider → Analyzer
```
Used for reproducibility, CI/CD testing, and baseline evaluation without incurring LLM latency or costs.

### Agentic Mode
```text
LLM Planner → Scenario Allowlist → MCP Tools → Analyzer
```
The LLM dynamically generates the evidence collection plan based on the incident. Agentic mode changes *how evidence is acquired*, not how it is diagnosed.

---

## Safety and Guardrails

The agent operates in a highly constrained environment:
- **Scenario-Specific Allowlists:** The planner can only select tools explicitly permitted for the current investigation type.
- **Required Tools:** Plans are rejected if they miss critical baseline telemetry tools.
- **Bounded Planning:** Plans are hard-capped at 5 steps.
- **Duplicate/Unknown Rejection:** Invalid plans are rejected immediately and execute *zero* evidence calls against the infrastructure.
- **Read-Only Model:** The agent has zero autonomous remediation capabilities. It investigates and recommends; it cannot execute write operations.
- **Blind Runtime:** The runtime orchestrator cannot read the testing contracts (`expected_diagnosis.json`).

---

## MCP Architecture

**MCP is the integration boundary, not the product.**

DataOps Investigator uses the Model Context Protocol (MCP) to decouple the agent from the underlying data systems. 
- In production, evidence tools connect to an external MCP server running against the real infrastructure.
- In tests, a `FixtureEvidenceProvider` injects mock telemetry.
- Crucially, tests prove that both the fixture-backed and MCP-backed providers return equivalent typed telemetry contracts.

---

## Evaluation Strategy

Evaluation is split into two rigorously separated layers:

1. **Deterministic Evaluation:** Validates the outcome. Did the analyzer reach the correct root cause? Did it gather the required evidence? Did it correctly transition the hypotheses states?
2. **Agentic Evaluation:** Validates the LLM's planning capability. It tracks `plan_validation_errors` (e.g., hallucinations, unsafe tools), `planner_request_errors` (e.g., OpenAI API 503s), and `investigation_errors` to ensure LLM failures are not silently converted into incorrect diagnostic conclusions. It operates locally using a deterministic mock planner for offline CI testing.

---

## Demo / Quick Start

### Prerequisites
- Python 3.9+ installed.
- To run Agentic Mode, an OpenAI-compatible API key is required.

### 1. Setup Environment
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add your LLM_API_KEY and LLM_API_BASE to .env for Agentic mode
```

### 2. Run Investigations

**Spark Performance (Deterministic):**
```bash
python -m app.cli investigate spark_performance run-customer-aggregation-2026-08-28
```

**Spark Performance (Agentic):**
*(Requires `.env` configuration)*
```bash
python -m app.cli investigate spark_performance run-customer-aggregation-2026-08-28 --agentic
```

**Pipeline Failure (Deterministic):**
```bash
python -m app.cli investigate pipeline_failure run-customer-daily-2026-09-12
```

**Pipeline Failure (Agentic):**
*(Requires `.env` configuration)*
```bash
python -m app.cli investigate pipeline_failure run-customer-daily-2026-09-12 --agentic
```

**JSON Output (Available for any command):**
```bash
python -m app.cli investigate pipeline_failure run-customer-daily-2026-09-12 --json
```

---

## Example Investigation Output

### Spark Performance Regression
```text
Investigation Mode: Agentic (via LLM & MCP)
Investigation Type: spark_performance
Incident: Spark performance regression for customer_aggregation
Run ID: run-customer-aggregation-2026-08-28
Status: COMPLETED

ACTUAL EVIDENCE:
- skew_ratio: 10.50
- runtime_regression_ratio: 4.00
- input_growth_ratio: 1.06
- ...

Leading Root Cause: Data skew (Confidence: 0.95)
Rationale: The largest partition is significantly larger than the median partition size...

Recommendations:
- Check the upstream data source for missing or uneven distribution keys...
```

### Pipeline Failure
```text
Investigation Mode: Deterministic
Investigation Type: pipeline_failure
Incident: Pipeline failure for customer_daily
Run ID: run-customer-daily-2026-09-12
Status: COMPLETED

ACTUAL EVIDENCE:
- Schema drifted fields: customer_id (BIGINT->STRING)
- schema_drift: True

Leading Root Cause: Schema Drift
Rationale: Failure log indicates a schema mismatch on field 'customer_id'...

Recommendations:
- Validate the changed field type against the historical schema contract...
```

---

## Repository Structure

```text
app/
  evidence_tools/       # MCP tool definitions and typed telemetry providers
  investigation/        # Deterministic analyzers, workflows, and LLM planners
scenarios/              # Deterministic test fixtures and evaluation contracts
tests/                  # Comprehensive automated test suite
```

## Testing

The project is backed by a robust, deterministic test suite ensuring both pipeline modes behave symmetrically.

**Current Test Count:** 141 tests (Passing)
Categories tested:
- Domain Models
- Scenario Fixtures
- MCP Lifecycle Parity
- Deterministic Analysis Logic
- Orchestrator Workflows
- LLM Planner Validation & Guardrails
- Agentic Evaluators (Offline Mocking)
- CLI Outputs

Run the full suite using:
```bash
python -m pytest
```