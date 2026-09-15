from app.investigation.planner import (
    InvestigationPlanProposal,
    InvestigationPlannerProtocol,
    PlannedStep,
)
from app.models import InvestigationType


class DeterministicMockPlanner:
    """A deterministic planner for offline agentic investigation testing."""

    def plan_investigation(self, incident_description: str, investigation_type: InvestigationType) -> InvestigationPlanProposal:
        if investigation_type == InvestigationType.SPARK_PERFORMANCE:
            return InvestigationPlanProposal(
                investigation_type=investigation_type,
                steps=[
                    PlannedStep(tool="spark_get_job", reason="Deterministic offline execution"),
                    PlannedStep(tool="spark_get_stages", reason="Deterministic offline execution"),
                    PlannedStep(tool="spark_get_partition_statistics", reason="Deterministic offline execution"),
                    PlannedStep(tool="spark_get_configuration", reason="Deterministic offline execution"),
                    PlannedStep(tool="spark_get_baseline", reason="Deterministic offline execution"),
                ],
            )
        elif investigation_type == InvestigationType.PIPELINE_FAILURE:
            return InvestigationPlanProposal(
                investigation_type=investigation_type,
                steps=[
                    PlannedStep(tool="pipeline_get_run", reason="Deterministic offline execution"),
                    PlannedStep(tool="pipeline_get_logs", reason="Deterministic offline execution"),
                    PlannedStep(tool="pipeline_get_current_schema", reason="Deterministic offline execution"),
                    PlannedStep(tool="pipeline_get_baseline_schema", reason="Deterministic offline execution"),
                ],
            )
        else:
            raise ValueError(f"Unsupported investigation type for mock planner: {investigation_type}")
