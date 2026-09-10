from typing import List, Literal

from pydantic import BaseModel, Field

from app.llm_client import LLMClient

ALLOWED_SPARK_TOOLS = {
    "spark_get_job",
    "spark_get_stages",
    "spark_get_partition_statistics",
    "spark_get_configuration",
    "spark_get_baseline"
}

class PlannedStep(BaseModel):
    tool: str
    reason: str

class InvestigationPlanProposal(BaseModel):
    investigation_type: Literal["SPARK_PERFORMANCE"]
    steps: List[PlannedStep] = Field(max_length=5)

class InvestigationPlannerError(RuntimeError):
    """Raised when the LLM generates an invalid investigation plan."""

class InvestigationPlanner:
    """Bounded LLM Investigation Planner for Scenario 1."""
    
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def plan_investigation(self, incident_description: str) -> InvestigationPlanProposal:
        """
        Creates a structured investigation plan for a Spark performance incident using an LLM.
        """
        system_prompt = (
            "You are a DataOps Investigation Planner. Your ONLY job is to create a structured "
            "investigation plan to collect evidence for a data engineering incident.\n\n"
            "Rules:\n"
            "1. You MUST NOT diagnose the root cause.\n"
            "2. You MUST NOT suggest remediation.\n"
            "3. You MUST output exactly 'SPARK_PERFORMANCE' as the investigation_type.\n"
            "4. You MUST create a plan with a maximum of 5 steps.\n"
            "5. You MUST NOT include duplicate tools in your plan.\n"
            "6. You MUST select tools ONLY from this exact allowlist:\n"
            f"{', '.join(ALLOWED_SPARK_TOOLS)}\n\n"
            "Output the plan strictly as JSON matching the requested schema."
        )
        
        user_prompt = f"Create an investigation plan for the following incident:\n\n{incident_description}"
        
        try:
            proposal = self.llm_client.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=InvestigationPlanProposal
            )
        except Exception as e:
            raise InvestigationPlannerError(f"Failed to generate plan: {e}") from e

        self._validate_proposal(proposal)
        return proposal

    def _validate_proposal(self, proposal: InvestigationPlanProposal) -> None:
        if len(proposal.steps) > 5:
            raise InvestigationPlannerError("Plan exceeds the maximum limit of 5 steps.")
            
        seen_tools = set()
        for step in proposal.steps:
            if step.tool not in ALLOWED_SPARK_TOOLS:
                raise InvestigationPlannerError(f"Plan includes unauthorized tool: '{step.tool}'")
            if step.tool in seen_tools:
                raise InvestigationPlannerError(f"Plan includes duplicate tool: '{step.tool}'")
            seen_tools.add(step.tool)
