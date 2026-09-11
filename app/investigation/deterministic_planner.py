from app.investigation.planner import (
    InvestigationPlanProposal,
    InvestigationPlannerProtocol,
    PlannedStep,
)


class DeterministicMockPlanner:
    """A deterministic planner for offline agentic investigation testing."""

    def plan_investigation(self, incident_description: str) -> InvestigationPlanProposal:
        return InvestigationPlanProposal(
            investigation_type="SPARK_PERFORMANCE",
            steps=[
                PlannedStep(tool="spark_get_job", reason="Deterministic offline execution"),
                PlannedStep(tool="spark_get_stages", reason="Deterministic offline execution"),
                PlannedStep(tool="spark_get_partition_statistics", reason="Deterministic offline execution"),
                PlannedStep(tool="spark_get_configuration", reason="Deterministic offline execution"),
                PlannedStep(tool="spark_get_baseline", reason="Deterministic offline execution"),
            ],
        )
