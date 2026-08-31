# AGENTS.md — DataOps Investigator

## 1. Project Identity

**Project name:** DataOps Investigator
**Repository:** `dataops-investigator`

DataOps Investigator is an **evidence-driven AI investigation platform for data engineering incidents**.

The goal is NOT to build another generic chatbot, generic RAG application, or generic autonomous agent.

The system should help a Data Engineer answer:

> **"Something went wrong or changed in my data platform. What happened, why did it happen, what evidence supports that conclusion, and what should I do next?"**

The system investigates real or reproducible synthetic incidents by:

1. Understanding the reported incident.
2. Creating an investigation plan.
3. Generating plausible hypotheses.
4. Collecting evidence from data systems and engineering knowledge.
5. Evaluating competing hypotheses.
6. Identifying the most likely root cause.
7. Producing an evidence-backed diagnosis.
8. Recommending remediation.
9. Requiring human approval before any potentially destructive/write action.

The primary product concept is:

**Investigation, not chat.**

---

# 2. V2 Product Goal

The project is evolving from a V1 "Agentic Data Engineering Assistant" into:

> **A local-first, MCP-powered DataOps investigation platform that can diagnose data engineering incidents using evidence from data systems, runtime telemetry, metadata, logs, and engineering documentation.**

The V2 MVP focuses on three concrete investigation scenarios:

### P0 — Spark Performance Regression

Example:

> "This Spark job normally takes 25 minutes but today's run took 100 minutes. Why?"

The investigator should be able to identify issues such as:

* data skew
* excessive shuffle
* partition imbalance
* increased input volume
* memory pressure
* join strategy regression
* inefficient execution plans

### P0 — Pipeline Failure / Root Cause Investigation

Example:

> "The daily customer pipeline failed at 02:14. Find the root cause."

Potential causes include:

* schema drift
* upstream failure
* malformed data
* missing partition
* dependency failure
* configuration regression
* infrastructure/resource issue

The investigator should reconstruct a useful incident timeline where possible.

### P1 — Data Quality / Data Anomaly Investigation

Example:

> "Revenue is 35% lower than normal today. Why?"

Potential causes include:

* missing data
* incomplete partition
* upstream ingestion failure
* duplication/filtering issue
* freshness issue
* transformation regression
* genuine metric change

The system should distinguish operational/data problems from plausible business changes using evidence.

---

# 3. Future Scenarios

These are planned extensions, not part of the initial MVP:

* Delta table performance investigation
* SQL query performance regression
* data pipeline cost investigation
* additional database/platform investigations

Do NOT implement these merely to create breadth.

Only introduce them after the MVP scenarios are working and evaluated.

---

# 4. Core Product Philosophy

The following principles are mandatory.

## 4.1 Evidence over intuition

The LLM must not simply guess a root cause.

A diagnosis should be supported by observable evidence.

Bad:

> "The Spark job is probably slow because of data skew."

Good:

> "Data skew is the leading hypothesis because the largest partition is 10.5× the median partition size, while input volume increased by only 6%."

Whenever possible, recommendations must identify:

* what was observed
* where it was observed
* how it compares with a baseline
* why it supports the hypothesis

---

## 4.2 Hypotheses are explicit

The investigator should be able to represent multiple possible causes.

Example:

```text
H1: Data skew
H2: Increased input volume
H3: Executor memory pressure
H4: Join strategy regression
H5: Excessive shuffle
```

Each hypothesis should be evaluated using evidence and assigned a state such as:

* SUPPORTED
* REJECTED
* INCONCLUSIVE

Do not force a root cause when available evidence is insufficient.

---

## 4.3 Read-only by default

The MVP is an investigation system, not an autonomous production-remediation system.

All investigation tools must be read-only by default.

Examples of acceptable operations:

* read logs
* inspect job metadata
* inspect Spark metrics
* inspect schemas
* inspect table statistics
* inspect query plans
* inspect documentation
* compare historical runs

Potentially mutating actions must be separated from investigation and require explicit human approval.

Never silently execute:

* DELETE
* UPDATE
* ALTER
* DROP
* OPTIMIZE
* restart
* deployment
* configuration changes
* pipeline reruns
* other destructive/write operations

---

## 4.4 Local-first

The project must be runnable locally without requiring paid cloud infrastructure.

Prefer:

* Docker
* Docker Compose
* Apache Spark
* PostgreSQL
* Parquet
* Delta Lake where practical
* MinIO where object storage is needed
* local/synthetic datasets
* local LLMs where practical
* open-source libraries

Cloud integrations may be designed behind interfaces, but must not be required for the MVP.

---

## 4.5 Build from scenarios, not abstractions

Do NOT build a large generic agent framework first.

Every major abstraction should exist because one or more concrete investigation scenarios require it.

Preferred sequence:

```text
Scenario
  ↓
Required evidence
  ↓
Required tool
  ↓
Investigation behavior
  ↓
Reusable abstraction
```

Not:

```text
Generic framework
  ↓
Plugin system
  ↓
Agent hierarchy
  ↓
20 tools
  ↓
Maybe build a scenario later
```

Avoid speculative architecture.

---

# 5. Target Investigation Lifecycle

A typical investigation should follow this conceptual flow:

```text
Incident
   ↓
Understand incident
   ↓
Classify investigation type
   ↓
Create investigation plan
   ↓
Generate hypotheses
   ↓
Collect evidence
   ↓
Compare against baselines
   ↓
Evaluate hypotheses
   ↓
Determine root cause / leading cause
   ↓
Assign confidence
   ↓
Generate remediation recommendation
   ↓
Human approval if action is required
   ↓
Optional controlled execution
```

The implementation does not need to match these steps one-to-one internally, but the resulting behavior should preserve this lifecycle.

---

# 6. Investigation Output Contract

Every completed investigation should aim to produce a structured result containing:

```text
Incident
Investigation Type
Investigation Status
Investigation Plan
Hypotheses
Evidence
Root Cause / Leading Cause
Confidence
Rejected or Inconclusive Hypotheses
Recommendations
Risk
Required Approval
Sources
Audit Information
```

A diagnosis without supporting evidence should be considered incomplete.

---

# 7. Evidence Model

Evidence is a first-class domain concept.

Evidence should contain enough information to answer:

* What was observed?
* Where did it come from?
* When was it observed?
* What baseline was used?
* Was the value measured or derived?
* Which hypothesis does it support or contradict?

A conceptual evidence object may look like:

```json
{
  "evidence_id": "ev-1842-07",
  "source": "spark_stage_metrics",
  "observation": "Largest partition is 4.3 GB",
  "baseline": "Median partition size is 410 MB",
  "derived_metric": {
    "name": "skew_ratio",
    "value": 10.5
  },
  "timestamp": "2026-08-28T02:14:00Z"
}
```

Do not fabricate evidence.

---

# 8. Hypothesis Model

A conceptual hypothesis may look like:

```json
{
  "hypothesis_id": "H1",
  "name": "Data skew",
  "status": "SUPPORTED",
  "confidence": 0.93,
  "supporting_evidence": [
    "ev-1842-07"
  ],
  "contradicting_evidence": []
}
```

Confidence must represent evidence strength, not simply LLM certainty.

Avoid presenting arbitrary numeric confidence values as scientific probabilities.

When confidence is heuristic, document that fact.

---

# 9. Core MCP Direction

MCP is an important integration mechanism, but MCP itself is NOT the product.

Do not name architecture or repository concepts around MCP unnecessarily.

Use MCP to expose evidence sources and controlled actions.

The MVP should prefer small, composable tools.

### Spark tools

Examples:

```text
spark.get_job
spark.get_stages
spark.get_tasks
spark.get_executors
spark.get_query_plan
spark.get_configuration
```

### Pipeline tools

Examples:

```text
pipeline.get_run
pipeline.get_task
pipeline.get_logs
pipeline.get_dependencies
pipeline.get_history
```

### Data quality tools

Examples:

```text
quality.profile_table
quality.get_anomaly
quality.get_freshness
quality.get_partition_stats
```

### Knowledge tools

Examples:

```text
knowledge.search
knowledge.get_document
```

Do NOT create a giant tool such as:

```text
investigate_everything()
```

Tools should expose focused evidence capabilities.

---

# 10. Knowledge / RAG Layer

The existing V1 RAG implementation should be reused where practical.

The knowledge layer may contain:

* internal engineering runbooks
* Spark documentation
* Delta documentation
* database documentation
* architecture documentation
* troubleshooting guides
* engineering standards

RAG is a knowledge source.

It must not be treated as the only source of truth for runtime incidents.

Runtime evidence should come from system/instrumentation tools.

The preferred model is:

```text
Documentation
      +
Runtime Evidence
      +
Metadata
      +
Historical Baseline
      ↓
Investigation
```

---

# 11. Existing V1 Code

The repository contains an earlier prototype.

Existing components may include concepts such as:

```text
app/agent/
app/mcp_tools/
app/ingestion.py
app/vector_store.py
app/rag_pipeline.py
app/api.py
app/cli.py
web/
data/docs/
data/index/
```

Do not rewrite these components automatically.

First determine:

1. What can be reused.
2. What should be adapted.
3. What is obsolete.
4. What can be removed safely.

Prefer incremental evolution over unnecessary rewrites.

---

# 12. Preferred Technical Stack

Default choices:

### Backend

* Python
* FastAPI
* Pydantic

### Agent / orchestration

Prefer lightweight/custom orchestration initially.

Do NOT introduce LangChain, LangGraph, or another large agent framework unless there is a demonstrated requirement.

A framework should solve an identified problem; it should not be added merely because this is an agent project.

### Storage

Initial prototype:

* FAISS is acceptable.

A future evolution may use:

* PostgreSQL
* pgvector

Do not migrate storage merely for theoretical production readiness.

### Data

* Apache Spark
* PySpark
* PostgreSQL
* Parquet
* Delta Lake where useful

### Infrastructure

* Docker
* Docker Compose

### Observability

* structured logs initially
* OpenTelemetry later if useful

---

# 13. Synthetic DataOps Laboratory

Because the project must be reproducible locally, use deterministic synthetic incidents.

The project should eventually contain scenario fixtures similar to:

```text
scenarios/
├── spark_performance/
├── pipeline_failure/
└── data_quality/
```

Each scenario should define, where applicable:

```text
data/
baseline/
incident/
logs/
metrics/
metadata/
expected_diagnosis/
evaluation/
```

The agent should not be given the root cause directly.

The scenario should contain enough evidence for a competent investigator to discover it.

---

# 14. Scenario 1 — Spark Performance Regression

The first implementation target is Spark performance regression.

The scenario should support a question such as:

> "Why did this Spark job become significantly slower than its historical baseline?"

The synthetic scenario should ideally include:

* baseline execution
* degraded execution
* job metadata
* stage metrics
* task metrics or useful approximations
* shuffle metrics
* partition statistics
* relevant configuration
* known expected root cause

A first target failure mode should be:

**data skew**

The implementation should be able to establish evidence such as:

```text
largest_partition / median_partition
```

and compare current execution with the baseline.

The scenario should be deterministic enough for automated testing.

---

# 15. Scenario 2 — Pipeline Failure

The second scenario should investigate a reproducible pipeline failure.

Initial preferred failure mode:

**schema drift**

Example:

```text
Previous:
customer_id = BIGINT

Current:
customer_id = STRING
```

The investigation should correlate:

* pipeline failure
* error logs
* current schema
* previous schema
* timing/history
* upstream change where available

Expected outcome:

```text
Root cause:
upstream schema drift

Evidence:
schema mismatch + timeline correlation
```

---

# 16. Scenario 3 — Data Quality Anomaly

The third scenario should investigate an abnormal business/data metric.

Initial preferred failure mode:

**missing upstream data / missing partition**

Example:

```text
Revenue down 35%
```

The system should investigate:

* current record count
* historical baseline
* partition presence
* freshness
* upstream ingestion state
* relevant data-quality metrics

The investigator should avoid assuming that a metric decline is a real business event before checking data completeness.

---

# 17. UI Philosophy

The primary interface should be an **Investigation Workspace**, not a generic chat clone.

The UI should make visible:

* incident
* investigation status
* current hypothesis
* evidence
* timeline
* diagnosis
* confidence
* recommendations
* sources
* approval/action state

Chat may be available, but should not be the only representation of the investigation.

Do not prioritize visual polish before the investigation workflow works correctly.

---

# 18. Evaluation Is a Core Feature

This project must be evaluated against deterministic scenarios.

Each scenario should define expected:

* root cause
* supporting evidence
* relevant tools
* expected recommendation
* unsafe/incorrect conclusions

At minimum, evaluate:

### Root-cause accuracy

Was the correct cause identified?

### Tool-selection quality

Did the agent use appropriate evidence sources?

### Evidence coverage

Did it collect important supporting evidence?

### Recommendation quality

Was the recommendation relevant and safe?

### Unsupported-claim rate

How often does the system make claims that lack evidence?

### Investigation efficiency

Track, where practical:

* number of tool calls
* latency
* token usage

Do not claim accuracy metrics without actually measuring them.

---

# 19. Testing Strategy

Every feature should have the smallest appropriate test layer.

Preferred hierarchy:

```text
unit tests
    ↓
component tests
    ↓
integration tests
    ↓
scenario tests
    ↓
agent evaluation
```

Tests must not depend on paid external services unless explicitly marked as optional.

The synthetic investigation scenarios should be runnable in CI.

---

# 20. Development Workflow

Before modifying code:

1. Inspect the current repository.
2. Locate the relevant implementation.
3. Understand existing contracts.
4. Identify the smallest required change.
5. Avoid touching unrelated files.

For each task:

```text
Understand
  ↓
Plan
  ↓
Implement minimal change
  ↓
Test
  ↓
Inspect diff
  ↓
Document important behavior
```

Do not perform broad refactors while implementing an unrelated feature.

---

# 21. Codex Working Rules

When asked to implement a feature:

### First inspect

Read the relevant files before proposing changes.

### Then plan

Briefly explain:

* current behavior
* gap
* files to change
* implementation approach
* tests required

### Then implement

Make the smallest coherent change that satisfies the request.

### Then validate

Run relevant tests, linters, type checks, or scenario commands where available.

### Then summarize

Report:

* what changed
* tests run
* test results
* known limitations

Do not claim validation that was not actually performed.

---

# 22. Scope Control

This repository is being developed as a focused portfolio project under a strict time constraint.

The initial target is a **15-day maximum implementation window**.

Optimize for:

**working depth > feature breadth**

Do not add features merely because they sound impressive.

Every feature should answer:

> Does this materially improve the ability to investigate a real DataOps incident?

If not, defer it.

---

# 23. Explicitly Avoid

Unless explicitly requested, do NOT introduce:

* generic chatbot functionality
* voice interfaces
* generic web search
* autonomous unrestricted production actions
* Kubernetes/platform-wide troubleshooting
* dozens of MCP integrations
* every cloud provider
* every database
* microservices without demonstrated need
* Kubernetes deployment for the MVP
* a large agent framework without a concrete requirement
* speculative plugin architecture
* unnecessary frontend frameworks
* unnecessary vector databases
* unnecessary abstractions
* premature distributed infrastructure
* cloud infrastructure that introduces cost
* employer-specific data or proprietary information

Never expose or hard-code private company data.

---

# 24. Architecture Principles

Prefer:

```text
simple
typed
testable
observable
deterministic where possible
local-first
read-only by default
evidence-backed
scenario-driven
```

Avoid:

```text
magic
implicit state
global mutable configuration
unbounded agent loops
giant tools
giant prompts
speculative abstractions
hidden side effects
```

The system should fail safely.

---

# 25. Agent Safety Rules

Agent loops must have bounded execution.

Use limits for:

* maximum tool calls
* maximum investigation steps
* maximum retries
* timeouts
* model/tool failures

The agent must be able to terminate with:

```text
INSUFFICIENT_EVIDENCE
```

rather than inventing an answer.

When tools disagree, expose the disagreement rather than silently selecting one source.

When evidence is incomplete, say so.

---

# 26. Repository Documentation

Keep architecture and product reasoning in:

```text
docs/
```

Useful documents include:

```text
docs/product-spec.md
docs/scenarios.md
docs/architecture.md
docs/investigation-model.md
docs/evaluation.md
```

Documentation should explain **why** important architectural decisions were made, not merely restate code.

Keep README focused on:

* problem
* solution
* architecture
* supported scenarios
* demo
* setup
* evaluation
* limitations
* roadmap

---

# 27. Definition of Done for V2 MVP

V2 MVP is complete only when:

### Scenario 1

A user can provide a Spark performance incident and receive:

* investigation plan
* relevant tool calls
* evidence
* hypotheses
* root cause
* confidence
* recommendations

### Scenario 2

A user can provide a reproducible pipeline failure and receive:

* failure analysis
* evidence
* root cause
* timeline where possible
* remediation recommendation

### Scenario 3

A user can provide a data anomaly and receive:

* baseline comparison
* evidence
* likely cause
* rejected/inconclusive alternatives
* remediation recommendation

### Across all scenarios

The system has:

* structured investigation state
* evidence objects
* hypothesis objects
* provenance/source tracking
* read-only safety model
* deterministic scenario fixtures
* automated tests
* basic evaluation metrics
* reproducible local setup

---

# 28. Priority Order

Implement in this order unless there is a strong reason not to:

```text
1. Repository inspection and cleanup
2. Investigation domain model
3. Scenario 1 synthetic Spark incident
4. Spark evidence tools
5. Investigation workflow
6. Hypothesis/evidence evaluation
7. Scenario 1 end-to-end evaluation
8. Scenario 2 pipeline failure
9. Scenario 3 data quality anomaly
10. Shared investigation/reporting improvements
11. Basic UI
12. Observability
13. Docker/local reproducibility
14. README/documentation/demo polish
```

Do not reverse this order to build UI or infrastructure first.

---

# 29. Engineering Quality Bar

Code should be:

* Pythonically clean
* type annotated where useful
* modular
* testable
* explicit
* readable by another engineer

Prefer clear names over clever abstractions.

Prefer a small amount of duplication over premature abstraction when requirements are still evolving.

Every bug fix should add or improve a regression test when practical.

---

# 30. Important Product Distinction

Do not describe the project primarily as:

> "An Agentic RAG application."

That is an implementation description.

The product is:

> **An evidence-driven DataOps investigation platform.**

RAG provides engineering knowledge.

MCP provides access to tools and systems.

The LLM orchestrates reasoning.

Deterministic analysis and system evidence provide grounding.

The investigation result is the product.

---

# 31. Expected End State

The intended end-to-end experience is:

```text
User reports incident
        ↓
DataOps Investigator
        ↓
Understands incident
        ↓
Builds investigation plan
        ↓
Selects evidence sources
        ↓
Calls MCP tools
        ↓
Collects evidence
        ↓
Generates competing hypotheses
        ↓
Tests hypotheses
        ↓
Compares against baselines
        ↓
Identifies likely root cause
        ↓
Produces evidence-backed report
        ↓
Recommends safe remediation
        ↓
Requests human approval for actions
```

The final system should feel less like:

**"ChatGPT for Data Engineering"**

and more like:

**"An AI incident investigator for Data Engineers."**
