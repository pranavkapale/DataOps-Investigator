from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel, Field, model_validator

class ChunkMetadata(BaseModel):
    doc_id: str
    source: str
    page: Optional[int] = None
    chunk_id: int

class IndexedChunk(BaseModel):
    text: str
    metadata: ChunkMetadata

class AskRequest(BaseModel):
    question: str

class AskResponse(BaseModel):
    answer: str
    sources: List[ChunkMetadata]


class InvestigationType(str, Enum):
    SPARK_PERFORMANCE = "SPARK_PERFORMANCE"
    PIPELINE_FAILURE = "PIPELINE_FAILURE"
    DATA_QUALITY = "DATA_QUALITY"


class InvestigationStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    FAILED = "FAILED"


class PlanStepStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class EvidenceKind(str, Enum):
    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"


class HypothesisStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AuditEventType(str, Enum):
    INVESTIGATION_STARTED = "INVESTIGATION_STARTED"
    PLAN_CREATED = "PLAN_CREATED"
    JOB_RETRIEVED = "JOB_RETRIEVED"
    STAGES_RETRIEVED = "STAGES_RETRIEVED"
    PARTITION_STATISTICS_RETRIEVED = "PARTITION_STATISTICS_RETRIEVED"
    CONFIGURATION_RETRIEVED = "CONFIGURATION_RETRIEVED"
    BASELINE_RETRIEVED = "BASELINE_RETRIEVED"
    TOOL_CALLED = "TOOL_CALLED"
    EVIDENCE_COLLECTED = "EVIDENCE_COLLECTED"
    ANALYSIS_COMPLETED = "ANALYSIS_COMPLETED"
    HYPOTHESIS_EVALUATED = "HYPOTHESIS_EVALUATED"
    INVESTIGATION_COMPLETED = "INVESTIGATION_COMPLETED"
    REPORT_COMPLETED = "REPORT_COMPLETED"


class SourceReference(BaseModel):
    """Identifies the origin of an observation without embedding its contents."""

    source: str = Field(..., min_length=1)
    location: Optional[str] = None
    captured_at: Optional[datetime] = None


class Incident(BaseModel):
    incident_id: str = Field(..., min_length=1)
    investigation_type: InvestigationType
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_reference: Optional[SourceReference] = None


class InvestigationStep(BaseModel):
    step_id: str = Field(..., min_length=1)
    order: int = Field(..., ge=1)
    description: str = Field(..., min_length=1)
    status: PlanStepStatus = PlanStepStatus.PENDING


class InvestigationPlan(BaseModel):
    plan_id: str = Field(..., min_length=1)
    steps: List[InvestigationStep] = Field(default_factory=list)
    max_steps: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def validate_steps(self) -> "InvestigationPlan":
        steps = self.steps
        max_steps = self.max_steps
        orders = [step.order for step in steps]
        if len(steps) > max_steps:
            raise ValueError("Investigation plan exceeds its maximum step count.")
        if len(orders) != len(set(orders)):
            raise ValueError("Investigation plan step order values must be unique.")
        return self


EvidenceValue = Union[float, int, str, bool]


class Evidence(BaseModel):
    evidence_id: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    observation: str = Field(..., min_length=1)
    kind: EvidenceKind
    observed_at: Optional[datetime] = None
    observed_value: Optional[EvidenceValue] = None
    baseline_value: Optional[EvidenceValue] = None
    derived_metric_name: Optional[str] = None
    derived_metric_value: Optional[EvidenceValue] = None
    source_reference: Optional[SourceReference] = None


class Hypothesis(BaseModel):
    hypothesis_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    status: HypothesisStatus = HypothesisStatus.INCONCLUSIVE
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    contradicting_evidence_ids: List[str] = Field(default_factory=list)
    heuristic_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    rationale: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_evidence_lists(self) -> "Hypothesis":
        supporting = set(self.supporting_evidence_ids)
        contradicting = set(self.contradicting_evidence_ids)
        if supporting & contradicting:
            raise ValueError("Evidence cannot both support and contradict the same hypothesis.")
        return self


class Recommendation(BaseModel):
    recommendation_id: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    risk_level: RiskLevel
    evidence_ids: List[str] = Field(default_factory=list)
    requires_human_approval: bool = False
    action_id: Optional[str] = None


class AuditRecord(BaseModel):
    record_id: str = Field(..., min_length=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: AuditEventType
    actor: str = Field(..., min_length=1)
    investigation_id: Optional[str] = None
    tool_name: Optional[str] = None
    success: Optional[bool] = None
    details: Optional[str] = None


class InvestigationReport(BaseModel):
    incident: Incident
    status: InvestigationStatus
    plan: InvestigationPlan
    hypotheses: List[Hypothesis] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)
    leading_hypothesis_id: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    rejected_hypothesis_ids: List[str] = Field(default_factory=list)
    inconclusive_hypothesis_ids: List[str] = Field(default_factory=list)
    recommendations: List[Recommendation] = Field(default_factory=list)
    audit_records: List[AuditRecord] = Field(default_factory=list)
    sources: List[SourceReference] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "InvestigationReport":
        evidence_ids = {evidence.evidence_id for evidence in self.evidence}
        hypothesis_by_id = {
            hypothesis.hypothesis_id: hypothesis
            for hypothesis in self.hypotheses
        }

        if len(evidence_ids) != len(self.evidence):
            raise ValueError("Evidence IDs must be unique within a report.")
        if len(hypothesis_by_id) != len(self.hypotheses):
            raise ValueError("Hypothesis IDs must be unique within a report.")

        for hypothesis in hypothesis_by_id.values():
            referenced_ids = (
                hypothesis.supporting_evidence_ids
                + hypothesis.contradicting_evidence_ids
            )
            unknown_ids = set(referenced_ids) - evidence_ids
            if unknown_ids:
                raise ValueError(
                    f"Hypothesis '{hypothesis.hypothesis_id}' references unknown evidence IDs: "
                    f"{sorted(unknown_ids)}"
                )

        for recommendation in self.recommendations:
            unknown_ids = set(recommendation.evidence_ids) - evidence_ids
            if unknown_ids:
                raise ValueError(
                    f"Recommendation '{recommendation.recommendation_id}' references "
                    f"unknown evidence IDs: {sorted(unknown_ids)}"
                )

        leading_id = self.leading_hypothesis_id
        if leading_id is not None and leading_id not in hypothesis_by_id:
            raise ValueError("Leading hypothesis ID must reference a report hypothesis.")

        for field_name, expected_status in (
            ("rejected_hypothesis_ids", HypothesisStatus.REJECTED),
            ("inconclusive_hypothesis_ids", HypothesisStatus.INCONCLUSIVE),
        ):
            for hypothesis_id in getattr(self, field_name):
                hypothesis = hypothesis_by_id.get(hypothesis_id)
                if hypothesis is None:
                    raise ValueError(f"Unknown hypothesis ID in {field_name}: {hypothesis_id}")
                if hypothesis.status != expected_status:
                    raise ValueError(
                        f"Hypothesis '{hypothesis_id}' must have status {expected_status.value} "
                        f"to appear in {field_name}."
                    )
        return self
