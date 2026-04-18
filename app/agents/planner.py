from __future__ import annotations

import re
import uuid
from typing import Any

from app.schemas.ticket import Ticket
from app.services.autogen_client import AutoGenGroqClient
from config.prompts import SUPPORTED_CASE_TYPES, get_prompt
from config.settings import AppSettings, settings


GENERIC_PLANNER_REASONS = {
	"tool_execution_partial",
	"tool_execution_failed",
	"confidence_below_threshold",
	"confidence_service_recommended_escalation",
	"autogen_force_escalation",
}

ALLOWED_PLANNER_ESCALATION_REASONS = {
	"missing_order_id_for_refund",
	"missing_order_id_for_cancellation",
	"return_window_expired",
	"fraud_or_legal_risk_signal",
	"warranty_claim_requires_manual_review",
	"exchange_requires_fulfillment_handoff",
	"customer_tier_must_be_verified_from_get_customer",
	"wrong_item_needs_replacement_or_refund_decision",
	"refund_requires_eligibility_before_issuance",
	"refund_amount_above_200_requires_escalation",
	"damaged_item_replacement_needs_manual_review",
	"replacement_requested_for_damaged_item",
	"damaged_item_requires_photo_evidence",
	"unable_to_classify_case",
	"refund_eligibility_failed",
	"cancellation_not_permitted_for_order_status",
	"missing_return_deadline_requires_manual_review",
	"order_linkage_ambiguous_or_missing",
	"insufficient_tool_chain_evidence",
	"premium_borderline_case_requires_supervisor_review",
}


class PlannerAgent:
	def __init__(
		self,
		app_settings: AppSettings | None = None,
		autogen_client: AutoGenGroqClient | None = None,
	) -> None:
		self.settings = app_settings or settings
		self.autogen_client = autogen_client or AutoGenGroqClient(self.settings)

	def create_action_plan(self, ticket_input: Ticket | dict[str, Any]) -> dict[str, object]:
		ticket = ticket_input if isinstance(ticket_input, Ticket) else Ticket.model_validate(ticket_input)
		reference_date = ticket.created_at.date().isoformat()

		text = f"{ticket.subject} {ticket.body}".lower()
		case_type = self._classify_case(text)
		autogen_result = self.autogen_client.generate_structured(
			role="planner",
			system_prompt=get_prompt("planner"),
			payload={
				"ticket": ticket.model_dump(mode="json"),
				"deterministic_case_type": case_type,
			},
		)
		if autogen_result.get("success"):
			structured = autogen_result.get("structured", {})
			llm_case_type = str(structured.get("case_type", "")).strip().lower()
			if llm_case_type in SUPPORTED_CASE_TYPES:
				case_type = llm_case_type
		else:
			structured = {}

		order_id = self._extract_order_id(text)
		photo_evidence = any(token in text for token in ("photo", "photos", "attached", "evidence"))
		wants_replacement = any(token in text for token in ("replacement", "replace", "exchange"))

		tool_calls: list[dict[str, Any]] = [
			{"tool": "get_customer", "params": {"email": ticket.customer_email}}
		]
		if order_id:
			tool_calls.append({"tool": "get_order", "params": {"order_id": order_id}})

		requires_escalation = False
		escalation_reasons: list[str] = []
		required_checks: list[str] = ["verify_customer"]
		proposed_action = "send_reply"

		if case_type == "refund":
			required_checks.append("refund_eligibility")
			if order_id:
				required_checks.append("verify_order")
				tool_calls.append(
					{
						"tool": "check_refund_eligibility",
						"params": {
							"order_id": order_id,
							"reason": self._short_reason(ticket.body),
							"photo_evidence": photo_evidence,
							"reference_date": reference_date,
						},
					}
				)
				tool_calls.append(
					{
						"tool": "issue_refund",
						"params": {
							"order_id": order_id,
							"reason": self._short_reason(ticket.body),
							"photo_evidence": photo_evidence,
							"reference_date": reference_date,
						},
					}
				)
				proposed_action = "issue_refund"
			else:
				tool_calls.append(
					{
						"tool": "issue_refund_for_email",
						"params": {
							"email": ticket.customer_email,
							"reason": self._short_reason(ticket.body),
							"photo_evidence": photo_evidence,
							"reference_date": reference_date,
						},
					}
				)
				proposed_action = "issue_refund_by_email"

		elif case_type == "cancellation":
			required_checks.append("cancellation_allowed")
			if order_id:
				required_checks.append("verify_order")
				tool_calls.append({"tool": "can_cancel_order", "params": {"order_id": order_id}})
				tool_calls.append(
					{
						"tool": "cancel_order",
						"params": {
							"order_id": order_id,
							"reason": "Customer requested cancellation",
						},
					}
				)
				proposed_action = "cancel_order"
			else:
				tool_calls.append(
					{
						"tool": "cancel_latest_processing_order_for_email",
						"params": {
							"email": ticket.customer_email,
							"reason": "Customer requested cancellation",
						},
					}
				)
				proposed_action = "cancel_order_by_email"

		elif case_type == "exchange":
			required_checks.extend(["verify_order", "exchange_policy_check"])
			if order_id:
				tool_calls.append({"tool": "get_order_with_product", "params": {"order_id": order_id}})
			tool_calls.append(
				{
					"tool": "search_knowledge_base",
					"params": {
						"query": "exchange wrong size wrong colour wrong item policy",
					}
				}
			)
			requires_escalation = True
			escalation_reasons.append("exchange_requires_fulfillment_handoff")
			proposed_action = "escalate"

		elif case_type == "wrong_item":
			required_checks.extend(["verify_order", "wrong_item_policy_check"])
			if order_id:
				tool_calls.append({"tool": "get_order_with_product", "params": {"order_id": order_id}})
			tool_calls.append(
				{
					"tool": "search_knowledge_base",
					"params": {
						"query": "wrong item delivered pickup replacement refund out of stock",
					}
				}
			)
			requires_escalation = True
			escalation_reasons.append("wrong_item_needs_replacement_or_refund_decision")
			proposed_action = "escalate"

		elif case_type == "damaged_item":
			required_checks.extend(["damage_evidence_check", "refund_eligibility"])
			if order_id:
				required_checks.append("verify_order")
			if wants_replacement:
				requires_escalation = True
				escalation_reasons.append("replacement_requested_for_damaged_item")
				if order_id:
					tool_calls.append({"tool": "get_order_with_product", "params": {"order_id": order_id}})
				tool_calls.append(
					{
						"tool": "search_knowledge_base",
						"params": {"query": "damaged item replacement policy escalation"},
					}
				)
				proposed_action = "escalate"
			elif not photo_evidence:
				tool_calls.append(
					{
						"tool": "send_reply",
						"params": {
							"customer_email": ticket.customer_email,
							"message": "Thanks for reporting the damage. Please share clear photos of the item and packaging so we can process your refund quickly.",
							"subject": "Photo evidence needed for damaged item claim",
						},
					}
				)
				proposed_action = "send_reply"
			else:
				if order_id:
					tool_calls.append({"tool": "get_order_with_product", "params": {"order_id": order_id}})
					tool_calls.append(
						{
							"tool": "check_refund_eligibility",
							"params": {
								"order_id": order_id,
								"reason": "damaged or defective on arrival",
								"photo_evidence": photo_evidence,
								"reference_date": reference_date,
							},
						}
					)
					tool_calls.append(
						{
							"tool": "issue_refund",
							"params": {
								"order_id": order_id,
								"reason": "damaged or defective on arrival",
								"photo_evidence": photo_evidence,
								"reference_date": reference_date,
							},
						}
					)
					proposed_action = "issue_refund"
				else:
					tool_calls.append(
						{
							"tool": "issue_refund_for_email",
							"params": {
								"email": ticket.customer_email,
								"reason": "damaged or defective on arrival",
								"photo_evidence": photo_evidence,
								"reference_date": reference_date,
							},
						}
					)
					proposed_action = "issue_refund_by_email"

		elif case_type == "warranty":
			required_checks.extend(["verify_order", "warranty_policy_check"])
			if order_id:
				tool_calls.append({"tool": "get_order_with_product", "params": {"order_id": order_id}})
			tool_calls.append(
				{
					"tool": "search_knowledge_base",
					"params": {"query": "warranty claims escalation policy"},
				}
			)
			requires_escalation = True
			escalation_reasons.append("warranty_claim_requires_manual_review")
			proposed_action = "escalate"

		elif case_type == "faq":
			required_checks.append("policy_lookup")
			tool_calls.append(
				{
					"tool": "search_knowledge_base",
					"params": {"query": f"{ticket.subject} {ticket.body}"},
				}
			)
			tool_calls.append(
				{
					"tool": "send_reply",
					"params": {
						"customer_email": ticket.customer_email,
						"message": "Thanks for your question. I looked up our policy details and shared the key guidance.",
						"subject": "ShopWave policy information",
					},
				}
			)
			proposed_action = "send_reply"

		else:
			requires_escalation = True
			escalation_reasons.append("unable_to_classify_case")
			tool_calls.append(
				{
					"tool": "search_knowledge_base",
					"params": {"query": "general support policy and escalation"},
				}
			)
			proposed_action = "escalate"

		llm_added_reason = False
		llm_escalation_reasons = structured.get("escalation_reasons")
		if isinstance(llm_escalation_reasons, list):
			for item in llm_escalation_reasons:
				reason = str(item).strip().lower().replace(" ", "_")
				if not reason or reason in GENERIC_PLANNER_REASONS:
					continue
				if reason not in ALLOWED_PLANNER_ESCALATION_REASONS:
					continue
				escalation_reasons.append(reason)
				llm_added_reason = True

		if autogen_result.get("success") and isinstance(structured.get("requires_escalation"), bool):
			if bool(structured.get("requires_escalation")) and llm_added_reason:
				requires_escalation = True

		confidence_hint = self._estimate_plan_confidence(case_type, bool(order_id), requires_escalation)

		return {
			"agent": "planner",
			"plan_id": f"PLAN-{uuid.uuid4().hex[:10].upper()}",
			"ticket_id": ticket.ticket_id,
			"case_type": case_type,
			"order_id": order_id,
			"summary": self._summarize_ticket(ticket),
			"required_checks": required_checks,
			"tool_calls": tool_calls,
			"proposed_action": proposed_action,
			"requires_escalation": requires_escalation,
			"escalation_reasons": sorted(set(escalation_reasons)),
			"confidence_hint": confidence_hint,
			"autogen": {
				"enabled": self.autogen_client.is_ready(role="planner"),
				"success": bool(autogen_result.get("success")),
				"structured": structured,
				"error": autogen_result.get("error"),
			},
		}

	@staticmethod
	def _extract_order_id(text: str) -> str | None:
		match = re.search(r"ord-\d{4,}", text, flags=re.IGNORECASE)
		return match.group(0).upper() if match else None

	@staticmethod
	def _classify_case(text: str) -> str:
		has_order_id = bool(re.search(r"ord-\d{4,}", text, flags=re.IGNORECASE))
		looks_like_faq = any(token in text for token in ("what is", "how", "policy", "faq", "process", "can i", "do you"))
		explicit_action = any(token in text for token in ("refund", "money back", "cancel", "exchange", "replacement", "wrong item", "damaged", "defective"))
		if looks_like_faq and (not has_order_id or not explicit_action):
			return "faq"

		if any(token in text for token in ("warranty", "guarantee claim")):
			return "warranty"
		if any(token in text for token in ("wrong item", "wrong colour", "wrong color", "wrong size")):
			if "exchange" in text or "replace" in text:
				return "exchange"
			return "wrong_item"
		if any(token in text for token in ("damaged", "defective", "broken", "cracked")):
			return "damaged_item"
		if any(token in text for token in ("cancel", "cancellation")):
			return "cancellation"
		if any(token in text for token in ("refund", "money back", "return")):
			return "refund"
		if any(token in text for token in ("exchange", "replace", "replacement")):
			return "exchange"
		if any(token in text for token in ("policy", "question", "faq", "where is my order", "tracking")):
			return "faq"
		return "unknown"

	@staticmethod
	def _short_reason(body: str, max_length: int = 180) -> str:
		sanitized = " ".join(body.split())
		if len(sanitized) <= max_length:
			return sanitized
		return f"{sanitized[:max_length - 3]}..."

	@staticmethod
	def _summarize_ticket(ticket: Ticket) -> str:
		return f"{ticket.subject} | source={ticket.source} | tier={ticket.tier}"

	@staticmethod
	def _estimate_plan_confidence(case_type: str, has_order_id: bool, requires_escalation: bool) -> float:
		score = 0.88
		if not has_order_id and case_type in {"refund", "cancellation", "exchange", "wrong_item", "damaged_item", "warranty"}:
			score -= 0.25
		if case_type in {"unknown", "warranty", "exchange", "wrong_item"}:
			score -= 0.12
		if requires_escalation:
			score -= 0.08
		return max(0.1, min(0.99, round(score, 2)))

