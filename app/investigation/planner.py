from typing import List, Protocol

from pydantic import BaseModel, Field

from app.llm_client import LLMClient
from app.models import InvestigationType
from app.investigation.scenario_config import SCENARIO_CONFIGS, InvestigationScenarioConfig

class PlannedStep(BaseModel):
    tool: str
    reason: str

class InvestigationPlanProposal(BaseModel):
    investigation_type: InvestigationType
    steps: List[PlannedStep] = Field(max_length=5)

class InvestigationPlannerError(RuntimeError):
    """Raised when the LLM generates an invalid investigation plan."""

class InvestigationPlannerProtocol(Protocol):
    """Interface for investigation planners."""

    def plan_investigation(self, incident_description: str, investigation_type: InvestigationType) -> InvestigationPlanProposal:
        """Creates a structured investigation plan."""
        ...

class InvestigationPlanner:
    """Bounded LLM Investigation Planner."""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def plan_investigation(self, incident_description: str, investigation_type: InvestigationType) -> InvestigationPlanProposal:
        """
        Creates a structured investigation plan for an incident using an LLM.
        """
        config = SCENARIO_CONFIGS.get(investigation_type)
        if not config:
            raise InvestigationPlannerError(f"Unsupported investigation type: {investigation_type}")

        system_prompt = (
            f"{config.scenario_instructions}\n\n"
            "Rules:\n"
            "1. You MUST NOT diagnose the root cause.\n"
            "2. You MUST NOT suggest remediation.\n"
            f"3. You MUST output exactly '{investigation_type.value}' as the investigation_type.\n"
            "4. You MUST create a plan with a maximum of 5 steps.\n"
            "5. You MUST NOT include duplicate tools in your plan.\n"
            "6. You MUST select tools ONLY from this exact allowlist:\n"
            f"{', '.join(sorted(config.allowed_tools))}\n\n"
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

        self._validate_proposal(proposal, config)
        return proposal

    def _validate_proposal(self, proposal: InvestigationPlanProposal, config: InvestigationScenarioConfig) -> None:
        if len(proposal.steps) > 5:
            raise InvestigationPlannerError("Plan exceeds the maximum limit of 5 steps.")

        seen_tools = set()
        for step in proposal.steps:
            if step.tool not in config.allowed_tools:
                raise InvestigationPlannerError(f"Plan includes unauthorized tool: '{step.tool}'")
            if step.tool in seen_tools:
                raise InvestigationPlannerError(f"Plan includes duplicate tool: '{step.tool}'")
            seen_tools.add(step.tool)

        missing_tools = config.required_tools - seen_tools
        if missing_tools:
            raise InvestigationPlannerError(
                f"Plan is missing required tools: {', '.join(sorted(missing_tools))}"
            )
