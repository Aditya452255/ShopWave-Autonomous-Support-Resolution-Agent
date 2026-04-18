from __future__ import annotations

import re
from typing import Any

from app.schemas.ticket import Ticket
from app.services.autogen_client import AutoGenGroqClient
from config.prompts import get_prompt
from config.settings import AppSettings, settings


GENERIC_REASON_CODES = {
	"tool_execution_failed",
	"tool_execution_partial",
	"confidence_below_threshold",
	"confidence_service_recommended_escalation",
	"autogen_force_escalation",
}

REASON_ALIASES = {
	"warranty_claims_must_escalate": "warranty_claim_requires_manual_review",
	"warranty_claims_must_go_to_warranty_team": "warranty_claim_requires_manual_review",
	"refund_amount_above_200_requires_escalation": "refund_amount_above_200_requires_escalation",
	"replacement_request_for_damaged_item": "damaged_item_replacement_needs_manual_review",
	"replacement_requested_for_damaged_item": "damaged_item_replacement_needs_manual_review",
	"return_window_has_expired_for_this_order": "return_window_expired",
	"return_window_has_expired": "return_window_expired",
	"refund_eligibility_not_confirmed_before_issuing_refund": "refund_requires_eligibility_before_issuance",
}

ALLOWED_POLICY_REASON_CODES = {
	"missing_order_id_for_refund",
	"missing_order_id_for_cancellation",
	"return_window_expired",
	"fraud_or_legal_risk_signal",
	"high_priority_ticket_tier",
	"warranty_claim_requires_manual_review",
	"exchange_requires_fulfillment_handoff",
	"customer_tier_must_be_verified_from_get_customer",
	"wrong_item_needs_replacement_or_refund_decision",
	"refund_requires_eligibility_before_issuance",
	"refund_amount_above_200_requires_escalation",
	"damaged_item_replacement_needs_manual_review",
	"damaged_item_requires_photo_evidence",
	"unable_to_classify_case",
	"refund_eligibility_failed",
	"cancellation_not_permitted_for_order_status",
	"missing_return_deadline_requires_manual_review",
	"order_linkage_ambiguous_or_missing",
	"insufficient_tool_chain_evidence",
	"premium_borderline_case_requires_supervisor_review",
}

MANDATORY_ESCALATION_POLICY_REASON_CODES = {
	"warranty_claim_requires_manual_review",
	"refund_amount_above_200_requires_escalation",
	"damaged_item_replacement_needs_manual_review",
	"fraud_or_legal_risk_signal",
	"premium_borderline_case_requires_supervisor_review",
	"order_linkage_ambiguous_or_missing",
	"wrong_item_needs_replacement_or_refund_decision",
	"exchange_requires_fulfillment_handoff",
}

MANDATORY_ESCALATION_SYSTEM_REASON_CODES = {
	"confidence_below_threshold",
	"confidence_service_recommended_escalation",
	"autogen_force_escalation",
}


class CriticAgent:
	def __init__(
		self,
		app_settings: AppSettings | None = None,
		autogen_client: AutoGenGroqClient | None = None,
	) -> None:
		self.settings = app_settings or settings
		self.autogen_client = autogen_client or AutoGenGroqClient(self.settings)

	def review(
		self,
		ticket_input: Ticket | dict[str, Any],
		plan: dict[str, Any],
		execution: dict[str, Any],
	) -> dict[str, object]:
		ticket = ticket_input if isinstance(ticket_input, Ticket) else Ticket.model_validate(ticket_input)
		steps = execution.get("steps", [])
		case_type = str(plan.get("case_type", "unknown"))

		violations: list[str] = []
		policy_reasons: list[str] = []
		system_reasons: list[str] = []

		check_get_customer_ok = self._has_successful_tool(steps, "get_customer")
		if not check_get_customer_ok:
			violations.append("customer_verification_missing")
			policy_reasons.append("customer_tier_must_be_verified_from_get_customer")

		order_context_ok = self._has_order_context(steps, case_type)
		if self._case_requires_order_context(case_type) and not order_context_ok:
			violations.append("order_linkage_missing_or_ambiguous")
			policy_reasons.append("order_linkage_ambiguous_or_missing")

		minimum_required_tools = self._minimum_successful_tools_required(
			case_type=case_type,
			proposed_action=str(plan.get("proposed_action", "")),
		)
		minimum_tool_chain_ok = self._has_minimum_successful_tools(steps, minimum=minimum_required_tools)
		if minimum_required_tools > 0 and not minimum_tool_chain_ok:
			violations.append("insufficient_tool_chain_evidence")
			policy_reasons.append("insufficient_tool_chain_evidence")

		refund_chain_ok = self._validate_refund_chain(steps)
		if not refund_chain_ok:
			violations.append("refund_chain_policy_violation")
			policy_reasons.append("refund_requires_eligibility_before_issuance")

		warranty_ok = True
		if case_type == "warranty" and not bool(plan.get("requires_escalation")):
			warranty_ok = False
			violations.append("warranty_must_escalate")
			policy_reasons.append("warranty_claim_requires_manual_review")

		refund_over_limit = self._refund_amount_over_limit(steps, limit=200.0)
		if refund_over_limit:
			policy_reasons.append("refund_amount_above_200_requires_escalation")

		if bool(plan.get("requires_escalation")):
			for reason in plan.get("escalation_reasons", []):
				normalized = self._normalize_reason_code(str(reason))
				if not normalized:
					continue
				if self._is_generic_reason(normalized):
					system_reasons.append(normalized)
				elif self._is_allowed_policy_reason(normalized):
					policy_reasons.append(normalized)

		if bool(plan.get("requires_escalation")) and not policy_reasons:
			fallback_case_reason = self._default_case_specific_reason(case_type)
			if fallback_case_reason:
				policy_reasons.append(fallback_case_reason)

		text = f"{ticket.subject} {ticket.body}".lower()
		if any(token in text for token in ("fraud", "scam", "lawyer", "chargeback", "legal")):
			policy_reasons.append("fraud_or_legal_risk_signal")

		if case_type == "damaged_item" and any(token in text for token in ("replace", "replacement")):
			policy_reasons.append("damaged_item_replacement_needs_manual_review")

		if self._declared_tier_mismatch(text, steps):
			policy_reasons.append("fraud_or_legal_risk_signal")

		autogen_result: dict[str, Any]
		autogen_structured: dict[str, Any]
		if self.autogen_client.is_ready(role="critic"):
			autogen_result = self.autogen_client.generate_structured(
				role="critic",
				system_prompt=get_prompt("critic"),
				payload={
					"ticket": ticket.model_dump(mode="json"),
					"plan": plan,
					"execution": execution,
				},
			)
			autogen_structured = autogen_result.get("structured", {}) if autogen_result.get("success") else {}
		else:
			autogen_result = {
				"success": False,
				"role": "critic",
				"error": "AutoGen disabled for critic role.",
			}
			autogen_structured = {}

		llm_policy_reasons = autogen_structured.get("policy_reasons")
		if isinstance(llm_policy_reasons, list):
			for reason in llm_policy_reasons:
				normalized = self._normalize_reason_code(str(reason))
				if normalized and not self._is_generic_reason(normalized) and self._is_allowed_policy_reason(normalized):
					policy_reasons.append(normalized)

		llm_system_reasons = autogen_structured.get("system_reasons")
		if isinstance(llm_system_reasons, list):
			for reason in llm_system_reasons:
				normalized = self._normalize_reason_code(str(reason))
				if normalized and self._is_generic_reason(normalized):
					system_reasons.append(normalized)

		llm_reasons = autogen_structured.get("additional_escalation_reasons")
		if isinstance(llm_reasons, list):
			for reason in llm_reasons:
				normalized = self._normalize_reason_code(str(reason))
				if not normalized:
					continue
				if self._is_generic_reason(normalized):
					system_reasons.append(normalized)
				elif self._is_allowed_policy_reason(normalized):
					policy_reasons.append(normalized)

		execution_status = str(execution.get("execution_status", "failed"))
		if execution_status == "failed":
			system_reasons.append("tool_execution_failed")
		has_required_tool_issue = execution_status == "partial" and self._has_required_tool_issue(plan=plan, execution=execution)
		if has_required_tool_issue:
			system_reasons.append("tool_execution_partial")

		has_order_reference = bool(plan.get("order_id")) or str(plan.get("proposed_action", "")).strip().lower() in {
			"issue_refund_by_email",
			"cancel_order_by_email",
		}

		confidence_score = self._calculate_confidence(
			case_type=case_type,
			has_order_id=has_order_reference,
			has_order_context=order_context_ok,
			has_minimum_tool_evidence=minimum_tool_chain_ok,
			has_policy_violations=bool(violations),
			execution_status=execution_status,
			failure_count=len(execution.get("tool_failures", [])),
			requires_escalation=bool(plan.get("requires_escalation")),
		)

		if confidence_score < self.settings.confidence_escalation_threshold:
			system_reasons.append("confidence_below_threshold")

		policy_reasons = self._dedupe_reasons(policy_reasons)
		system_reasons = self._dedupe_reasons(system_reasons)

		mandatory_policy_reasons = [
			reason
			for reason in policy_reasons
			if reason in MANDATORY_ESCALATION_POLICY_REASON_CODES
		]
		mandatory_system_reasons = [
			reason
			for reason in system_reasons
			if reason in MANDATORY_ESCALATION_SYSTEM_REASON_CODES
		]
		escalation_reasons = self._dedupe_reasons([*mandatory_policy_reasons, *mandatory_system_reasons])
		escalate = len(escalation_reasons) > 0
		policy_compliant = len(violations) == 0 and warranty_ok and refund_chain_ok

		if escalate:
			final_decision = "escalate"
		elif execution_status == "failed":
			final_decision = "retry"
		elif execution_status == "partial" and has_required_tool_issue:
			final_decision = "retry"
		else:
			final_decision = "approve"

		ranked_reasons = self._rank_reasons(policy_reasons, system_reasons)
		primary_reason_hint = str(autogen_structured.get("primary_reason", "")).strip()
		if not primary_reason_hint:
			primary_reason_hint = ranked_reasons[0] if ranked_reasons else ""
		approval_reasoning_hint = str(autogen_structured.get("approval_reasoning", "")).strip()

		return {
			"agent": "critic",
			"ticket_id": ticket.ticket_id,
			"plan_id": plan.get("plan_id"),
			"case_type": case_type,
			"autogen": {
				"enabled": self.autogen_client.is_ready(role="critic"),
				"success": bool(autogen_result.get("success")),
				"structured": autogen_structured,
				"error": autogen_result.get("error"),
			},
			"policy_compliant": policy_compliant,
			"confidence_score": confidence_score,
			"must_escalate": escalate,
			"escalate": escalate,
			"escalation_reasons": escalation_reasons,
			"policy_reasons": policy_reasons,
			"system_reasons": system_reasons,
			"ranked_reasons": ranked_reasons,
			"primary_reason_hint": primary_reason_hint,
			"approval_reasoning_hint": approval_reasoning_hint,
			"violations": violations,
			"checks": {
				"get_customer_verified": check_get_customer_ok,
				"order_context_ok": order_context_ok,
				"minimum_tool_chain_ok": minimum_tool_chain_ok,
				"minimum_required_tools": minimum_required_tools,
				"refund_chain_ok": refund_chain_ok,
				"warranty_escalation_ok": warranty_ok,
				"refund_over_200": refund_over_limit,
				"execution_status": execution_status,
			},
			"final_decision": final_decision,
			"notes": str(autogen_structured.get("notes", "")),
		}

	@staticmethod
	def _normalize_reason_code(raw_reason: str) -> str:
		normalized = raw_reason.strip().lower()
		normalized = normalized.replace(" ", "_").replace("-", "_")
		normalized = re.sub(r"[^a-z0-9_]", "", normalized)
		normalized = re.sub(r"_+", "_", normalized).strip("_")
		if not normalized:
			return ""
		return REASON_ALIASES.get(normalized, normalized)

	@staticmethod
	def _is_generic_reason(reason_code: str) -> bool:
		return reason_code in GENERIC_REASON_CODES

	@staticmethod
	def _is_allowed_policy_reason(reason_code: str) -> bool:
		return reason_code in ALLOWED_POLICY_REASON_CODES

	@staticmethod
	def _dedupe_reasons(reasons: list[str]) -> list[str]:
		seen: set[str] = set()
		ordered: list[str] = []
		for reason in reasons:
			if not reason or reason in seen:
				continue
			seen.add(reason)
			ordered.append(reason)
		return ordered

	@staticmethod
	def _rank_reasons(policy_reasons: list[str], system_reasons: list[str]) -> list[str]:
		return [*policy_reasons, *[item for item in system_reasons if item not in policy_reasons]]

	@staticmethod
	def _default_case_specific_reason(case_type: str) -> str:
		mapping = {
			"warranty": "warranty_claim_requires_manual_review",
			"exchange": "exchange_requires_fulfillment_handoff",
			"wrong_item": "wrong_item_needs_replacement_or_refund_decision",
			"unknown": "unable_to_classify_case",
		}
		return mapping.get(case_type, "")

	@staticmethod
	def _case_requires_order_context(case_type: str) -> bool:
		return case_type in {"refund", "cancellation", "exchange", "wrong_item", "damaged_item", "warranty"}

	@staticmethod
	def _minimum_successful_tools_required(*, case_type: str, proposed_action: str) -> int:
		normalized_action = proposed_action.strip().lower()
		if case_type in {"refund", "damaged_item", "wrong_item", "exchange", "warranty"}:
			if normalized_action == "issue_refund_by_email":
				return 2
			return 3
		if case_type == "cancellation":
			if normalized_action in {"cancel_order", "cancel_order_by_email"}:
				return 2
			return 1
		if case_type == "faq":
			return 2
		return 1

	@staticmethod
	def _has_order_context(steps: list[dict[str, Any]], case_type: str) -> bool:
		if not CriticAgent._case_requires_order_context(case_type):
			return True

		order_tools = {
			"get_order",
			"get_order_with_product",
			"get_customer_orders",
			"get_customer_orders_by_email",
			"check_refund_eligibility",
			"can_cancel_order",
			"cancel_order",
			"issue_refund",
			"issue_refund_for_email",
			"cancel_latest_processing_order_for_email",
		}
		for step in steps:
			tool_name = str(step.get("tool", "")).strip().lower()
			if tool_name in order_tools and bool(step.get("success")):
				return True
		return False

	@staticmethod
	def _has_minimum_successful_tools(steps: list[dict[str, Any]], *, minimum: int) -> bool:
		success_count = sum(1 for step in steps if bool(step.get("success")))
		return success_count >= minimum

	@staticmethod
	def _has_required_tool_issue(*, plan: dict[str, Any], execution: dict[str, Any]) -> bool:
		steps = execution.get("steps", [])
		if not isinstance(steps, list):
			return True

		required_checks = plan.get("required_checks", [])
		required_tool_set: set[str] = set()
		for check in required_checks:
			check_name = str(check).strip().lower()
			if check_name == "verify_customer":
				required_tool_set.add("get_customer")
			elif check_name == "verify_order":
				required_tool_set.update({"get_order", "get_order_with_product"})
			elif check_name == "refund_eligibility":
				required_tool_set.add("check_refund_eligibility")
			elif check_name == "cancellation_allowed":
				required_tool_set.add("can_cancel_order")

		action = str(plan.get("proposed_action", "")).strip().lower()
		action_tool_map = {
			"issue_refund": "issue_refund",
			"issue_refund_by_email": "issue_refund_for_email",
			"cancel_order": "cancel_order",
			"cancel_order_by_email": "cancel_latest_processing_order_for_email",
			"send_reply": "send_reply",
			"escalate": "escalate",
		}
		target_tool = action_tool_map.get(action)
		if target_tool:
			required_tool_set.add(target_tool)

		if not required_tool_set:
			return bool(execution.get("tool_failures"))

		def _tool_success(name: str) -> bool:
			return any(
				str(step.get("tool", "")).strip().lower() == name and bool(step.get("success"))
				for step in steps
			)

		if "get_order" in required_tool_set or "get_order_with_product" in required_tool_set:
			order_ok = _tool_success("get_order") or _tool_success("get_order_with_product")
			if not order_ok:
				return True

		for tool_name in required_tool_set:
			if tool_name in {"get_order", "get_order_with_product"}:
				continue
			if not _tool_success(tool_name):
				return True

		return False

	@staticmethod
	def _has_successful_tool(steps: list[dict[str, Any]], tool_name: str) -> bool:
		normalized_tool = tool_name.strip().lower()
		for step in steps:
			if str(step.get("tool", "")).strip().lower() == normalized_tool and bool(step.get("success")):
				return True
		return False

	@staticmethod
	def _validate_refund_chain(steps: list[dict[str, Any]]) -> bool:
		eligibility_indices: list[int] = []
		eligible_true_indices: list[int] = []

		for idx, step in enumerate(steps):
			tool = str(step.get("tool", "")).strip().lower()
			if tool == "check_refund_eligibility":
				eligibility_indices.append(idx)
				result = step.get("result", {})
				if isinstance(result, dict) and bool(result.get("success")) and bool(result.get("eligible")):
					eligible_true_indices.append(idx)

		for idx, step in enumerate(steps):
			tool = str(step.get("tool", "")).strip().lower()
			if tool == "issue_refund" and bool(step.get("success")):
				result = step.get("result", {}) if isinstance(step.get("result"), dict) else {}
				if bool(step.get("skipped")) or bool(result.get("policy_blocked")):
					continue

				has_prior_eligibility = any(elig_idx < idx for elig_idx in eligibility_indices)
				has_prior_positive = any(elig_idx < idx for elig_idx in eligible_true_indices)
				if not (has_prior_eligibility and has_prior_positive):
					return False

			if tool == "issue_refund_for_email" and bool(step.get("success")):
				result = step.get("result", {}) if isinstance(step.get("result"), dict) else {}
				if not bool(result.get("eligibility_checked")):
					return False

		return True

	@staticmethod
	def _refund_amount_over_limit(steps: list[dict[str, Any]], *, limit: float) -> bool:
		for step in steps:
			if str(step.get("tool", "")).strip().lower() not in {"issue_refund", "issue_refund_for_email"}:
				continue
			if not bool(step.get("success")):
				continue

			result = step.get("result", {})
			if isinstance(result, dict):
				amount = result.get("amount")
				if isinstance(amount, (int, float)) and float(amount) > limit:
					return True
		return False

	@staticmethod
	def _declared_tier_mismatch(ticket_text: str, steps: list[dict[str, Any]]) -> bool:
		declares_premium = any(token in ticket_text for token in ("premium member", "i am premium", "as a premium"))
		declares_vip = any(token in ticket_text for token in ("vip", "i am vip", "as a vip"))
		if not declares_premium and not declares_vip:
			return False

		actual_tier = ""
		for step in steps:
			if str(step.get("tool", "")).strip().lower() != "get_customer" or not bool(step.get("success")):
				continue
			result = step.get("result", {}) if isinstance(step.get("result"), dict) else {}
			customer = result.get("customer", {}) if isinstance(result.get("customer"), dict) else {}
			actual_tier = str(customer.get("tier", "")).strip().lower()
			break

		if not actual_tier:
			return False

		if declares_vip and actual_tier != "vip":
			return True
		if declares_premium and actual_tier not in {"premium", "vip"}:
			return True
		return False

	@staticmethod
	def _calculate_confidence(
		*,
		case_type: str,
		has_order_id: bool,
		has_order_context: bool,
		has_minimum_tool_evidence: bool,
		has_policy_violations: bool,
		execution_status: str,
		failure_count: int,
		requires_escalation: bool,
	) -> float:
		score = 0.9

		if execution_status == "partial":
			score -= 0.2
		elif execution_status == "failed":
			score -= 0.35

		if failure_count > 0:
			score -= min(0.3, failure_count * 0.08)

		if has_policy_violations:
			score -= 0.25

		if case_type in {"warranty", "wrong_item", "exchange"}:
			score -= 0.08

		if not has_order_id and case_type in {"refund", "cancellation", "exchange", "wrong_item", "damaged_item", "warranty"}:
			score -= 0.18

		if not has_order_context and case_type in {"refund", "cancellation", "exchange", "wrong_item", "damaged_item", "warranty"}:
			score -= 0.2

		if not has_minimum_tool_evidence:
			score -= 0.22

		if requires_escalation:
			score -= 0.08

		return max(0.05, min(0.99, round(score, 2)))

