from typing import Set

from pydantic import BaseModel, Field

from app.models import InvestigationType


class InvestigationScenarioConfig(BaseModel):
    investigation_type: InvestigationType
    allowed_tools: Set[str] = Field(default_factory=set)
    required_tools: Set[str] = Field(default_factory=set)
    scenario_instructions: str


SCENARIO_CONFIGS = {
    InvestigationType.SPARK_PERFORMANCE: InvestigationScenarioConfig(
        investigation_type=InvestigationType.SPARK_PERFORMANCE,
        allowed_tools={
            "spark_get_job",
            "spark_get_stages",
            "spark_get_partition_statistics",
            "spark_get_configuration",
            "spark_get_baseline",
        },
        required_tools={
            "spark_get_job",
            "spark_get_stages",
            "spark_get_partition_statistics",
            "spark_get_configuration",
            "spark_get_baseline",
        },
        scenario_instructions=(
            "You are a DataOps Investigation Planner. Your ONLY job is to create a structured "
            "investigation plan to collect evidence for a data engineering incident.\n\n"
            "This incident is a Spark performance regression.\n"
            "Collect necessary metrics to identify issues like data skew, inefficient execution plans, "
            "or performance regressions."
        ),
    ),
    InvestigationType.PIPELINE_FAILURE: InvestigationScenarioConfig(
        investigation_type=InvestigationType.PIPELINE_FAILURE,
        allowed_tools={
            "pipeline_get_run",
            "pipeline_get_logs",
            "pipeline_get_current_schema",
            "pipeline_get_baseline_schema",
        },
        required_tools={
            "pipeline_get_run",
            "pipeline_get_logs",
            "pipeline_get_current_schema",
            "pipeline_get_baseline_schema",
        },
        scenario_instructions=(
            "You are a DataOps Investigation Planner. Your ONLY job is to create a structured "
            "investigation plan to collect evidence for a data engineering incident.\n\n"
            "This incident is a data pipeline failure.\n"
            "You may need to retrieve run metadata, failure logs, and compare current and "
            "baseline schemas to identify issues."
        ),
    ),
}
