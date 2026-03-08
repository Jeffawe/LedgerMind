from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class UserRequestContext(BaseModel):
    timezone: str = "UTC"
    policy_profile: str = "default_v1"


class UserRequest(BaseModel):
    request_id: str
    user_id: str
    message: str = Field(min_length=1)
    context: UserRequestContext = Field(default_factory=UserRequestContext)


class DateRange(BaseModel):
    start: date = Field(description="Start date in YYYY-MM-DD format, e.g. 2026-01-31.")
    end: date = Field(description="End date in YYYY-MM-DD format, e.g. 2026-01-31.")

    @field_validator("start", "end", mode="before")
    @classmethod
    def coerce_date(cls, value: Any) -> Any:
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            return value

        text = value.strip()
        if not text:
            return value

        # Canonical format first.
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m-%d-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return value

    @model_validator(mode="after")
    def validate_order(self) -> "DateRange":
        if self.start > self.end:
            raise ValueError("date_range.start must be <= date_range.end")
        return self


class TransactionQuery(BaseModel):
    """
    Canonical cross-provider transaction query.

    Required:
      - date_range (YYYY-MM-DD dates)
    Optional:
      - source/providers/provider_names
      - accounts/categories/currency
      - txn_type or positive
      - min/max amount, query
      - exclude_transfers
    """

    date_range: DateRange
    source: Optional[str] = None
    providers: List[str] = Field(default_factory=list)
    provider_names: List[str] = Field(default_factory=list)
    accounts: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)
    currency: Optional[str] = None
    txn_type: Optional[Literal["debit", "credit"]] = None
    positive: Optional[bool] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    query: Optional[str] = None
    exclude_transfers: Optional[bool] = None

    @model_validator(mode="after")
    def validate_amounts_and_filters(self) -> "TransactionQuery":
        if self.min_amount is not None and self.max_amount is not None and self.min_amount > self.max_amount:
            raise ValueError("min_amount must be <= max_amount")
        if self.txn_type is not None and self.positive is not None:
            expected_positive = self.txn_type == "debit"
            if self.positive != expected_positive:
                raise ValueError("txn_type and positive filters conflict")
        return self


class ToolFilters(BaseModel):
    accounts: List[str] = Field(default_factory=list)
    exclude_transfers: bool = True


class ToolArgs(BaseModel):
    date_range: Optional[DateRange] = None
    group_by: Optional[str] = None
    filters: ToolFilters = Field(default_factory=ToolFilters)
    currency: str = "USD"
    extra: Dict[str, Any] = Field(default_factory=dict)


class ToolContext(BaseModel):
    user_id: str
    ledger_id: str
    timezone: str = "UTC"
    policy_profile: str = "default_v1"


class ToolRequest(BaseModel):
    request_id: str
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)
    filters: Optional[TransactionQuery] = Field(
        default=None,
        description=(
            "Canonical normalized transaction filters computed by the planner/router for the tool call. "
            "Use this for provider-level filtering (especially date_range) instead of raw args when available. "
            "Some tools require a populated date_range and may fail or return broad results without it; other tools "
            "may ignore unused fields. Includes optional account/category/currency/amount/text filters for tools "
            "that operate on transaction sets."
        ),
    )
    context: ToolContext


class ToolResponse(BaseModel):
    request_id: str
    tool: str
    ok: bool = True
    result: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    context: ToolContext


class PlanAssumptions(BaseModel):
    date_range: Optional[DateRange] = Field(
        default=None,
        description="Assumed analysis date range used when planning tool calls.",
    )
    currency: Optional[str] = Field(
        default=None,
        description="Assumed reporting currency for tool arguments and answer framing (for example, USD).",
    )


class PlanCall(BaseModel):
    id: str = Field(description="Stable step id for this call (for example, s1, s2).")
    tool: str = Field(description="Exact tool name to execute from the registered tool catalog.")
    args: Dict[str, Any] = Field(
        default_factory=dict,
        description="JSON-serializable arguments for the selected tool.",
    )
    purpose: str = Field(description="One-line reason this tool call is needed.")


class PlanOutputTarget(BaseModel):
    response_schema: str = Field(
        description="Identifier of the downstream response schema to target.",
    )
    focus: List[str] = Field(
        default_factory=list,
        description="Priority themes to emphasize in the answer stage (for example, spend_reduction, cash_buffer).",
    )


class LedgerMindPlan(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_version: str = Field(
        default="ledgermind.plan.v1",
        alias="schema",
        description="Plan schema identifier; must remain ledgermind.plan.v1.",
    )
    objective: str = Field(description="Plain-language objective for the plan.")
    assumptions: PlanAssumptions = Field(
        default_factory=PlanAssumptions,
        description="Explicit assumptions the planner used when constructing calls.",
    )
    calls: List[PlanCall] = Field(
        default_factory=list,
        description="Ordered tool calls to execute for collecting evidence.",
    )
    output: PlanOutputTarget = Field(description="Target answer contract and focus areas.")


class EvidenceRef(BaseModel):
    citation_id: str
    path: str


class NumericEvidence(BaseModel):
    id: str
    label: str
    value: float
    unit: str
    type: Literal["evidence", "assumption"]
    evidence_ref: Optional[EvidenceRef] = None
    assumption: Optional[str] = None


class AnswerOption(BaseModel):
    id: str
    title: str
    why: str
    steps: List[str] = Field(default_factory=list)
    impact: List[NumericEvidence] = Field(default_factory=list)
    tradeoffs: List[str] = Field(default_factory=list)


class PolicyAlignmentCheck(BaseModel):
    rule: str
    status: Literal["pass", "fail", "warning"]
    details: str


class RecommendedAction(BaseModel):
    title: str
    next_7_days: List[str] = Field(default_factory=list)
    next_30_days: List[str] = Field(default_factory=list)
    policy_alignment: List[PolicyAlignmentCheck] = Field(default_factory=list)


class AssumptionsConfidence(BaseModel):
    assumptions: List[str] = Field(default_factory=list)
    confidence: float
    confidence_reasoning: List[str] = Field(default_factory=list)


class AnswerTrace(BaseModel):
    plan_id: str
    tool_calls_used: List[str] = Field(default_factory=list)
    validation_targets: List[str] = Field(default_factory=list)


class MemoryItem(BaseModel):
    text: str
    kind: Literal["preference", "goal", "constraint", "fact", "context", "other"] = "other"
    source_request_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class LLMAnswerDraft(BaseModel):
    answer: str = Field(description="Primary direct answer to the user request.")
    bullets: List[str] = Field(
        default_factory=list,
        description="Short supporting bullet points grounded in tool evidence.",
    )
    options: List[AnswerOption] = Field(
        default_factory=list,
        description="Actionable alternatives the user can choose from.",
    )
    recommended_action: Optional[RecommendedAction] = Field(
        default=None,
        description="Best next action given evidence and policy profile, or null if not applicable.",
    )
    risks_and_tradeoffs: List[str] = Field(
        default_factory=list,
        description="Key risks, caveats, or tradeoffs the user should consider.",
    )
    assumptions_and_confidence: Optional[AssumptionsConfidence] = Field(
        default=None,
        description="Assumptions and confidence score for uncertainty transparency.",
    )
    memory: List[MemoryItem] = Field(
        default_factory=list,
        description="Durable preference/constraint/context items to persist for future requests.",
    )
    used_tool_calls: List[str] = Field(
        default_factory=list,
        description="Tool names from evidence that the model actively used for reasoning.",
    )


class EngineAnswer(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_version: str = Field(default="ledgermind.answer.v1", alias="schema")
    answer: str
    bullets: List[str] = Field(default_factory=list)
    supporting_numbers: List[NumericEvidence] = Field(default_factory=list)
    options: List[AnswerOption] = Field(default_factory=list)
    recommended_action: Optional[RecommendedAction] = None
    risks_and_tradeoffs: List[str] = Field(default_factory=list)
    assumptions_and_confidence: Optional[AssumptionsConfidence] = None
    trace: Optional[AnswerTrace] = None
    memory: List[MemoryItem] = Field(
        default_factory=list,
        description=(
            "Durable memory entries worth keeping for future answers. Keep concise and only include facts/preferences/"
            "constraints that should persist across requests."
        ),
    )
