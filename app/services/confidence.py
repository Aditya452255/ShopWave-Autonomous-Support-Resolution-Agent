from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config.settings import AppSettings, settings


@dataclass(slots=True)
class ConfidenceAssessment:
	score: float
	escalation_recommended: bool
	reasons: list[str]
	threshold: float
	below_threshold: bool

	def to_dict(self) -> dict[str, Any]:
		return {
			"score": self.score,
			"escalation_recommended": self.escalation_recommended,
			"reasons": self.reasons,
			"threshold": self.threshold,
			"below_threshold": self.below_threshold,
		}


class ConfidenceService:
	def __init__(self, app_settings: AppSettings | None = None) -> None:
		self.settings = app_settings or settings

	def assess(
		self,
		*,
		plan: dict[str, Any],
		execution: dict[str, Any],
		critic_review: dict[str, Any],
	) -> dict[str, Any]:
		score = float(plan.get("confidence_hint", 0.5))
		reasons: list[str] = []

		execution_status = str(execution.get("execution_status", "failed"))
		if execution_status == "completed":
			score += 0.08
			reasons.append("execution_completed")
		elif execution_status == "partial":
			score -= 0.18
			reasons.append("execution_partial")
		else:
			score -= 0.28
			reasons.append("execution_failed")

		failure_count = len(execution.get("tool_failures", []))
		if failure_count:
			score -= min(0.25, failure_count * 0.06)
			reasons.append("tool_failures_present")

		if bool(critic_review.get("violations")):
			score -= 0.22
			reasons.append("policy_violations_present")

		if bool(plan.get("requires_escalation")):
			score -= 0.08
			reasons.append("planner_requested_escalation")

		case_type = str(plan.get("case_type", "unknown"))
		if case_type in {"warranty", "wrong_item", "exchange"}:
			score -= 0.07
			reasons.append("complex_case_type")

		score = max(0.05, min(0.99, round(score, 2)))
		threshold = float(self.settings.confidence_escalation_threshold)
		escalate = score < threshold

		if escalate and "below_threshold" not in reasons:
			reasons.append("score_below_threshold")

		assessment = ConfidenceAssessment(
			score=score,
			escalation_recommended=escalate,
			reasons=reasons,
			threshold=threshold,
			below_threshold=escalate,
		)
		return assessment.to_dict()

