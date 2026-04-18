from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


DecisionLabel = Literal["approve", "escalate", "retry", "unknown"]


class DecisionExplanation(BaseModel):
	model_config = ConfigDict(extra="forbid")

	decision: DecisionLabel
	confidence: float = Field(ge=0.0, le=1.0)
	final_reason_summary: str = Field(min_length=3)
	evidence_used: list[str] = Field(default_factory=list)
	policy_status: dict[str, Any] = Field(default_factory=dict)
	system_status: dict[str, Any] = Field(default_factory=dict)
	audit_explanation: str = Field(min_length=3)
	short_reason: str = Field(min_length=3)
	detailed_reason: str = Field(min_length=3)

	approval_reason_code: str | None = None
	approval_reason_text: str | None = None
	approval_summary: str | None = None
	policy_checks_passed: list[str] = Field(default_factory=list)

	escalation_reason_codes: list[str] = Field(default_factory=list)
	escalation_reason_text: str | None = None
	escalation_summary: str | None = None
	primary_reason: str | None = None
	contributing_reasons: list[str] = Field(default_factory=list)

	@model_validator(mode="after")
	def _validate_decision_specific_fields(self) -> "DecisionExplanation":
		if self.decision == "approve":
			if not self.approval_reason_code:
				raise ValueError("approval_reason_code is required when decision=approve")
			if not self.approval_reason_text:
				raise ValueError("approval_reason_text is required when decision=approve")
			if not self.approval_summary:
				raise ValueError("approval_summary is required when decision=approve")
			if not self.policy_checks_passed:
				raise ValueError("policy_checks_passed is required when decision=approve")

		if self.decision == "escalate":
			if not self.escalation_reason_codes:
				raise ValueError("escalation_reason_codes is required when decision=escalate")
			if not self.primary_reason:
				raise ValueError("primary_reason is required when decision=escalate")
			if not self.escalation_reason_text:
				raise ValueError("escalation_reason_text is required when decision=escalate")
			if not self.escalation_summary:
				raise ValueError("escalation_summary is required when decision=escalate")

		return self
