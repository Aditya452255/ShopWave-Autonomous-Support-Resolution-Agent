from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from app.agents.critic import CriticAgent
from app.agents.executor import ExecutorAgent
from app.agents.planner import PlannerAgent
from app.core.memory import MemoryStore
from app.schemas.decision import DecisionExplanation
from app.schemas.ticket import Ticket
from app.services.audit_logger import AuditLogger
from app.services.confidence import ConfidenceService
from app.services.retry_handler import RetryHandler
from config.settings import AppSettings, settings


GENERIC_REASON_CODES = {
	"tool_execution_partial",
	"tool_execution_failed",
	"confidence_below_threshold",
	"confidence_service_recommended_escalation",
	"autogen_force_escalation",
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

REASON_TEXT_MAP = {
	"missing_order_id_for_refund": "Missing order ID required for refund validation.",
	"missing_order_id_for_cancellation": "Missing order ID required for cancellation validation.",
	"return_window_expired": "Return window has expired for this order.",
	"fraud_or_legal_risk_signal": "Potential fraud or legal risk requires manual investigation.",
	"high_priority_ticket_tier": "High-priority customer tier requires human review.",
	"warranty_claim_requires_manual_review": "Warranty claim requires specialized manual review.",
	"exchange_requires_fulfillment_handoff": "Exchange request requires fulfillment team handoff.",
	"customer_tier_must_be_verified_from_get_customer": "Customer identity/tier could not be verified safely.",
	"order_linkage_ambiguous_or_missing": "Order linkage is missing or ambiguous and requires manual verification.",
	"insufficient_tool_chain_evidence": "Decision lacks minimum verified tool evidence and requires human review.",
	"wrong_item_needs_replacement_or_refund_decision": "Wrong-item claim needs manual replacement/refund decision.",
	"refund_requires_eligibility_before_issuance": "Refund action failed policy chain eligibility checks.",
	"refund_amount_above_200_requires_escalation": "Refund amount exceeds automatic approval limit.",
	"damaged_item_replacement_needs_manual_review": "Damaged-item replacement request needs human review.",
	"damaged_item_requires_photo_evidence": "Damaged-item claim requires photo evidence for safe approval.",
	"tool_execution_partial": "Required system actions partially failed.",
	"tool_execution_failed": "Required system actions failed.",
	"confidence_below_threshold": "Confidence score is below safe automation threshold.",
	"confidence_service_recommended_escalation": "Confidence service requested conservative human review.",
	"unable_to_classify_case": "Case could not be confidently classified.",
	"refund_eligibility_failed": "Refund eligibility checks did not pass.",
	"premium_borderline_case_requires_supervisor_review": "Premium borderline case requires supervisor approval.",
	"cancellation_not_permitted_for_order_status": "Order status does not allow automatic cancellation.",
	"missing_return_deadline_requires_manual_review": "Return-deadline metadata is missing and requires manual review.",
}

REASON_SHORT_MAP = {
	"missing_order_id_for_refund": "Refund blocked: missing order ID",
	"return_window_expired": "Escalated: return window expired",
	"fraud_or_legal_risk_signal": "Escalated: fraud/legal risk",
	"high_priority_ticket_tier": "Escalated: high-priority tier",
	"warranty_claim_requires_manual_review": "Escalated: warranty needs manual review",
	"exchange_requires_fulfillment_handoff": "Escalated: fulfillment handoff needed",
	"wrong_item_needs_replacement_or_refund_decision": "Escalated: wrong-item decision required",
	"customer_tier_must_be_verified_from_get_customer": "Escalated: customer verification missing",
	"order_linkage_ambiguous_or_missing": "Escalated: order linkage missing or ambiguous",
	"insufficient_tool_chain_evidence": "Escalated: insufficient verified evidence",
	"refund_requires_eligibility_before_issuance": "Escalated: refund chain policy failed",
	"refund_amount_above_200_requires_escalation": "Escalated: refund amount above policy limit",
	"damaged_item_replacement_needs_manual_review": "Escalated: damaged-item replacement review",
	"damaged_item_requires_photo_evidence": "Escalated: photo evidence required",
	"premium_borderline_case_requires_supervisor_review": "Escalated: premium borderline case needs supervisor",
	"tool_execution_partial": "Escalated: execution partially failed",
	"confidence_below_threshold": "Escalated: low confidence",
	"unable_to_classify_case": "Escalated: unable to classify case",
}

REASON_CANONICAL_ALIASES = {
	"return_window_has_expired_for_this_order": "return_window_expired",
	"return_window_has_expired": "return_window_expired",
	"refund_eligibility_not_confirmed_before_issuing_refund": "refund_requires_eligibility_before_issuance",
	"warranty_claims_must_go_to_warranty_team": "warranty_claim_requires_manual_review",
	"warranty_claims_must_escalate": "warranty_claim_requires_manual_review",
	"replacement_requested_for_damaged_item": "damaged_item_replacement_needs_manual_review",
}


class TicketOrchestrator:
	def __init__(
		self,
		app_settings: AppSettings | None = None,
		planner: PlannerAgent | None = None,
		executor: ExecutorAgent | None = None,
		critic: CriticAgent | None = None,
		retry_handler: RetryHandler | None = None,
		confidence_service: ConfidenceService | None = None,
		audit_logger: AuditLogger | None = None,
		memory_store: MemoryStore | None = None,
	) -> None:
		self.settings = app_settings or settings
		self.planner = planner or PlannerAgent(self.settings)
		self.executor = executor or ExecutorAgent(self.settings)
		self.critic = critic or CriticAgent(self.settings)
		self.retry_handler = retry_handler or RetryHandler()
		self.confidence_service = confidence_service or ConfidenceService(self.settings)
		self.audit_logger = audit_logger or AuditLogger(self.settings)
		self.memory_store = memory_store or MemoryStore()

	async def process_ticket(self, ticket_input: Ticket | dict[str, Any]) -> dict[str, Any]:
		started_at = datetime.now(tz=UTC).isoformat()
		ticket = ticket_input if isinstance(ticket_input, Ticket) else Ticket.model_validate(ticket_input)
		correlation_id = f"CORR-{uuid.uuid4().hex[:12].upper()}"
		memory = self.memory_store.start_ticket(ticket.ticket_id, correlation_id)

		try:
			memory.set_stage("ticket", ticket.model_dump(mode="json"))
			memory.add_event("ticket_received", {"source": ticket.source})

			plan = self.retry_handler.run(self.planner.create_action_plan, ticket)
			memory.set_stage("plan", plan)
			memory.add_event("planner_completed", {"case_type": plan.get("case_type")})

			execution = self.retry_handler.run(self.executor.execute_plan, plan)
			memory.set_stage("execution", execution)
			memory.add_event("executor_completed", {"status": execution.get("execution_status")})

			review = self.retry_handler.run(self.critic.review, ticket, plan, execution)
			memory.set_stage("critic", review)
			memory.add_event("critic_completed", {"decision": review.get("final_decision")})

			confidence = self.confidence_service.assess(
				plan=plan,
				execution=execution,
				critic_review=review,
			)
			memory.set_stage("confidence", confidence)
			memory.add_event(
				"confidence_scored",
				{
					"score": confidence.get("score"),
					"escalation_recommended": confidence.get("escalation_recommended"),
				},
			)

			decision_payload = self._build_decision_explanation(
				ticket=ticket,
				plan=plan,
				execution=execution,
				review=review,
				confidence=confidence,
			)

			final_decision = str(decision_payload.get("decision", "escalate"))
			escalation_reasons = list(decision_payload.get("escalation_reason_codes", []))

			outcome = {
				"agent": "orchestrator",
				"backend": self.settings.orchestration_mode,
				"ticket_id": ticket.ticket_id,
				"correlation_id": correlation_id,
				"started_at": started_at,
				"finished_at": datetime.now(tz=UTC).isoformat(),
				"case_type": plan.get("case_type"),
				"plan": plan,
				"execution": execution,
				"review": review,
				"confidence": confidence,
				"decision": final_decision,
				"final_decision": final_decision,
				"escalation_reasons": escalation_reasons,
				"final_reason_summary": decision_payload.get("final_reason_summary"),
				"evidence_used": decision_payload.get("evidence_used", []),
				"policy_status": decision_payload.get("policy_status", {}),
				"system_status": decision_payload.get("system_status", {}),
				"audit_explanation": decision_payload.get("audit_explanation"),
				"short_reason": decision_payload.get("short_reason"),
				"detailed_reason": decision_payload.get("detailed_reason"),
				"approval_reason_code": decision_payload.get("approval_reason_code"),
				"approval_reason_text": decision_payload.get("approval_reason_text"),
				"approval_summary": decision_payload.get("approval_summary"),
				"policy_checks_passed": decision_payload.get("policy_checks_passed", []),
				"escalation_reason_codes": decision_payload.get("escalation_reason_codes", []),
				"escalation_reason_text": decision_payload.get("escalation_reason_text"),
				"escalation_summary": decision_payload.get("escalation_summary"),
				"primary_reason": decision_payload.get("primary_reason"),
				"contributing_reasons": decision_payload.get("contributing_reasons", []),
				"memory": memory.to_dict(),
			}

			self.audit_logger.append_record(
				{
					"ticket_id": ticket.ticket_id,
					"correlation_id": correlation_id,
					"agent": "orchestrator",
					"decision": final_decision,
					"confidence": confidence.get("score"),
					"tool_calls": plan.get("tool_calls", []),
					"tool_outputs": execution.get("steps", []),
					"reasoning_chain": {
						"planner_summary": plan.get("summary"),
						"critic_checks": review.get("checks", {}),
						"escalation_reasons": escalation_reasons,
						"final_reason_summary": decision_payload.get("final_reason_summary"),
						"short_reason": decision_payload.get("short_reason"),
						"audit_explanation": decision_payload.get("audit_explanation"),
					},
					"final_status": "escalated" if final_decision == "escalate" else "resolved",
				}
			)

			return outcome
		except Exception as exc:  # noqa: BLE001
			fallback_explanation = DecisionExplanation(
				decision="escalate",
				confidence=0.0,
				final_reason_summary="Escalated due to orchestrator runtime exception.",
				evidence_used=[],
				policy_status={"compliant": False, "violations": ["orchestrator_runtime_exception"], "checks": {}},
				system_status={"execution_status": "failed", "tool_failure_count": 0, "system_reasons": ["tool_execution_failed"]},
				audit_explanation=f"Escalated because runtime exception occurred: {exc}",
				short_reason="Escalated: system runtime exception",
				detailed_reason=f"Escalated because a runtime exception occurred during orchestration: {exc}",
				escalation_reason_codes=["tool_execution_failed"],
				escalation_reason_text="Required system actions failed due to runtime exception.",
				escalation_summary="Escalated: orchestration runtime failure.",
				primary_reason="tool_execution_failed",
				contributing_reasons=[],
			).model_dump(mode="json")

			failure = {
				"agent": "orchestrator",
				"backend": self.settings.orchestration_mode,
				"ticket_id": ticket.ticket_id,
				"correlation_id": correlation_id,
				"started_at": started_at,
				"finished_at": datetime.now(tz=UTC).isoformat(),
				"decision": "escalate",
				"final_decision": "escalate",
				"escalation_reasons": ["tool_execution_failed"],
				"final_reason_summary": fallback_explanation["final_reason_summary"],
				"evidence_used": fallback_explanation["evidence_used"],
				"policy_status": fallback_explanation["policy_status"],
				"system_status": fallback_explanation["system_status"],
				"audit_explanation": fallback_explanation["audit_explanation"],
				"short_reason": fallback_explanation["short_reason"],
				"detailed_reason": fallback_explanation["detailed_reason"],
				"escalation_reason_codes": fallback_explanation["escalation_reason_codes"],
				"escalation_reason_text": fallback_explanation["escalation_reason_text"],
				"escalation_summary": fallback_explanation["escalation_summary"],
				"primary_reason": fallback_explanation["primary_reason"],
				"contributing_reasons": fallback_explanation["contributing_reasons"],
				"error": str(exc),
				"memory": memory.to_dict(),
			}
			self.audit_logger.append_record(
				{
					"ticket_id": ticket.ticket_id,
					"correlation_id": correlation_id,
					"agent": "orchestrator",
					"decision": "escalate",
					"confidence": 0.0,
					"tool_calls": [],
					"tool_outputs": [],
					"reasoning_chain": {"error": str(exc)},
					"final_status": "failed",
				}
			)
			return failure

	def _build_decision_explanation(
		self,
		*,
		ticket: Ticket,
		plan: dict[str, Any],
		execution: dict[str, Any],
		review: dict[str, Any],
		confidence: dict[str, Any],
	) -> dict[str, Any]:
		confidence_score = float(confidence.get("score", 0.0))
		confidence_recommended = bool(confidence.get("escalation_recommended"))
		base_decision = str(review.get("final_decision", "escalate")).strip().lower()
		must_escalate = bool(review.get("must_escalate", False))

		evidence_used = self._collect_evidence_used(plan=plan, execution=execution)
		policy_checks_passed = self._collect_policy_checks_passed(review=review)

		policy_reason_codes = self._collect_policy_reason_codes(plan=plan, execution=execution, review=review)
		system_reason_codes = self._collect_system_reason_codes(execution=execution, review=review, confidence=confidence)

		if confidence_recommended and "confidence_service_recommended_escalation" not in system_reason_codes:
			system_reason_codes.append("confidence_service_recommended_escalation")

		if any(code in MANDATORY_ESCALATION_POLICY_REASON_CODES for code in policy_reason_codes):
			must_escalate = True
		if confidence_recommended:
			must_escalate = True

		if must_escalate:
			decision = "escalate"
		elif base_decision == "retry":
			decision = "retry"
		else:
			decision = "approve"

		policy_status = {
			"compliant": bool(review.get("policy_compliant", False)),
			"checks": review.get("checks", {}),
			"violations": review.get("violations", []),
			"policy_reasons": policy_reason_codes,
		}
		system_status = {
			"execution_status": str(execution.get("execution_status", "failed")),
			"tool_failure_count": len(execution.get("tool_failures", [])),
			"system_reasons": system_reason_codes,
			"confidence_threshold": float(confidence.get("threshold", self.settings.confidence_escalation_threshold)),
			"below_threshold": bool(confidence.get("below_threshold", False)),
		}

		if decision == "approve":
			approval_payload = self._build_approval_reasoning(
				plan=plan,
				review=review,
				policy_reason_codes=policy_reason_codes,
				evidence_used=evidence_used,
				policy_checks_passed=policy_checks_passed,
			)

			final_reason_summary = approval_payload["approval_summary"]
			audit_explanation = (
				f"Approved. {approval_payload['approval_reason_text']} "
				f"Evidence: {', '.join(evidence_used) if evidence_used else 'none'}"
			)

			validated = DecisionExplanation(
				decision="approve",
				confidence=confidence_score,
				final_reason_summary=final_reason_summary,
				evidence_used=evidence_used,
				policy_status=policy_status,
				system_status=system_status,
				audit_explanation=audit_explanation,
				short_reason=f"Approved: {approval_payload['approval_summary']}",
				detailed_reason=approval_payload["approval_reason_text"],
				approval_reason_code=approval_payload["approval_reason_code"],
				approval_reason_text=approval_payload["approval_reason_text"],
				approval_summary=approval_payload["approval_summary"],
				policy_checks_passed=policy_checks_passed,
			).model_dump(mode="json")
			return validated

		if decision == "retry":
			retry_summary = "Retry required because execution completed incompletely without a decisive policy block."
			validated = DecisionExplanation(
				decision="retry",
				confidence=confidence_score,
				final_reason_summary=retry_summary,
				evidence_used=evidence_used,
				policy_status=policy_status,
				system_status=system_status,
				audit_explanation=retry_summary,
				short_reason="Retry: execution incomplete",
				detailed_reason=retry_summary,
			).model_dump(mode="json")
			return validated

		escalation_payload = self._build_escalation_reasoning(
			policy_reason_codes=policy_reason_codes,
			system_reason_codes=system_reason_codes,
		)

		audit_explanation = (
			f"Escalated. Primary reason: {self._reason_to_text(escalation_payload['primary_reason'])} "
			f"Contributing reasons: {', '.join(escalation_payload['contributing_reasons']) if escalation_payload['contributing_reasons'] else 'none'}. "
			f"Evidence: {', '.join(evidence_used) if evidence_used else 'none'}"
		)

		validated = DecisionExplanation(
			decision="escalate",
			confidence=confidence_score,
			final_reason_summary=escalation_payload["escalation_summary"],
			evidence_used=evidence_used,
			policy_status=policy_status,
			system_status=system_status,
			audit_explanation=audit_explanation,
			short_reason=escalation_payload["short_reason"],
			detailed_reason=escalation_payload["escalation_reason_text"],
			escalation_reason_codes=escalation_payload["escalation_reason_codes"],
			escalation_reason_text=escalation_payload["escalation_reason_text"],
			escalation_summary=escalation_payload["escalation_summary"],
			primary_reason=escalation_payload["primary_reason"],
			contributing_reasons=escalation_payload["contributing_reasons"],
		).model_dump(mode="json")
		return validated

	@staticmethod
	def _dedupe(values: list[str]) -> list[str]:
		seen: set[str] = set()
		result: list[str] = []
		for value in values:
			item = str(value).strip()
			if not item or item in seen:
				continue
			seen.add(item)
			result.append(item)
		return result

	def _collect_policy_reason_codes(self, *, plan: dict[str, Any], execution: dict[str, Any], review: dict[str, Any]) -> list[str]:
		reasons: list[str] = []

		for source in (review.get("policy_reasons", []), review.get("escalation_reasons", [])):
			if not isinstance(source, list):
				continue
			for item in source:
				reason_code = self._normalize_reason_code(str(item))
				if not reason_code or reason_code in GENERIC_REASON_CODES:
					continue
				reasons.append(reason_code)

		reasons.extend(self._derive_reasons_from_execution(execution=execution, case_type=str(plan.get("case_type", "unknown"))))
		return self._dedupe(reasons)

	def _collect_system_reason_codes(self, *, execution: dict[str, Any], review: dict[str, Any], confidence: dict[str, Any]) -> list[str]:
		reasons: list[str] = []

		for source in (review.get("system_reasons", []), review.get("escalation_reasons", [])):
			if not isinstance(source, list):
				continue
			for item in source:
				reason_code = self._normalize_reason_code(str(item))
				if reason_code in GENERIC_REASON_CODES:
					reasons.append(reason_code)

		if bool(confidence.get("below_threshold")):
			reasons.append("confidence_below_threshold")

		status = str(execution.get("execution_status", "failed")).strip().lower()
		if status == "failed":
			reasons.append("tool_execution_failed")
		elif status == "partial" and len(execution.get("tool_failures", [])) > 0:
			reasons.append("tool_execution_partial")

		return self._dedupe(reasons)

	def _derive_reasons_from_execution(self, *, execution: dict[str, Any], case_type: str) -> list[str]:
		reasons: list[str] = []
		steps = execution.get("steps", [])
		if not isinstance(steps, list):
			return reasons

		for step in steps:
			if not isinstance(step, dict):
				continue
			tool = str(step.get("tool", "")).strip().lower()
			result = step.get("result", {})
			if not isinstance(result, dict):
				continue

			if tool == "check_refund_eligibility":
				if result.get("success") and result.get("eligible") is False:
					reason_text = str(result.get("reason", "")).lower()
					if "return window has expired" in reason_text:
						reasons.append("return_window_expired")
					elif "photo evidence is required" in reason_text:
						reasons.append("damaged_item_requires_photo_evidence")
					elif "above $200" in reason_text:
						reasons.append("refund_amount_above_200_requires_escalation")
					elif "warranty claims require escalation" in reason_text:
						reasons.append("warranty_claim_requires_manual_review")
					elif "missing return deadline" in reason_text:
						reasons.append("missing_return_deadline_requires_manual_review")
					elif "premium borderline case requires supervisor approval" in reason_text:
						reasons.append("premium_borderline_case_requires_supervisor_review")
					else:
						reasons.append("refund_eligibility_failed")

			if tool == "issue_refund_for_email":
				if bool(step.get("success")) and bool(result.get("policy_blocked")):
					reason_text = str(result.get("reason", "")).lower()
					if "return window" in reason_text:
						reasons.append("return_window_expired")
					elif "photo" in reason_text and "required" in reason_text:
						reasons.append("damaged_item_requires_photo_evidence")
					else:
						reasons.append("refund_eligibility_failed")
				elif not bool(step.get("success")):
					error_text = str(result.get("error", "")).lower()
					if "multiple eligible orders found" in error_text:
						reasons.append("order_linkage_ambiguous_or_missing")
					elif "no eligible delivered order" in error_text:
						reasons.append("refund_eligibility_failed")

			if tool == "cancel_latest_processing_order_for_email":
				if bool(step.get("success")) and bool(result.get("policy_blocked")):
					reasons.append("cancellation_not_permitted_for_order_status")
				elif not bool(step.get("success")):
					error_text = str(result.get("error", "")).lower()
					if "multiple processing orders found" in error_text:
						reasons.append("order_linkage_ambiguous_or_missing")
					elif "no processing order found" in error_text:
						reasons.append("cancellation_not_permitted_for_order_status")

			if tool == "can_cancel_order" and result.get("success") and result.get("cancellable") is False:
				reasons.append("cancellation_not_permitted_for_order_status")

		if case_type == "warranty":
			reasons.append("warranty_claim_requires_manual_review")

		return self._dedupe(reasons)

	def _collect_evidence_used(self, *, plan: dict[str, Any], execution: dict[str, Any]) -> list[str]:
		evidence: list[str] = []
		steps = execution.get("steps", [])
		if not isinstance(steps, list):
			return evidence

		for step in steps:
			if not isinstance(step, dict) or not bool(step.get("success")):
				continue

			tool = str(step.get("tool", "")).strip().lower()
			result = step.get("result", {}) if isinstance(step.get("result"), dict) else {}

			if tool == "get_customer":
				evidence.append("customer_verified")
			elif tool in {"get_order", "get_order_with_product"}:
				evidence.append("order_verified")
			elif tool == "search_knowledge_base":
				evidence.append("knowledge_lookup_completed")
			elif tool == "check_refund_eligibility":
				if bool(result.get("eligible")):
					evidence.append("refund_eligibility_passed")
				else:
					evidence.append("refund_eligibility_checked_ineligible")
			elif tool == "issue_refund":
				evidence.append("refund_issued")
			elif tool == "issue_refund_for_email":
				if bool(result.get("policy_blocked")):
					evidence.append("refund_eligibility_checked_ineligible")
				else:
					evidence.append("refund_issued")
					evidence.append("order_verified")
			elif tool == "can_cancel_order":
				if bool(result.get("cancellable")):
					evidence.append("cancellation_eligibility_passed")
				else:
					evidence.append("cancellation_eligibility_checked_not_allowed")
			elif tool == "cancel_order":
				evidence.append("order_cancelled")
			elif tool == "cancel_latest_processing_order_for_email":
				if bool(result.get("policy_blocked")):
					evidence.append("cancellation_eligibility_checked_not_allowed")
				else:
					evidence.append("order_cancelled")
					evidence.append("order_verified")
			elif tool == "send_reply":
				evidence.append("customer_reply_sent")
			elif tool == "escalate":
				evidence.append("human_handoff_created")

		if str(plan.get("case_type", "")).strip().lower() == "faq" and "customer_reply_sent" in evidence:
			evidence.append("faq_response_prepared")

		return self._dedupe(evidence)

	@staticmethod
	def _collect_policy_checks_passed(*, review: dict[str, Any]) -> list[str]:
		checks = review.get("checks", {}) if isinstance(review.get("checks"), dict) else {}
		passed: list[str] = []

		if bool(checks.get("get_customer_verified")):
			passed.append("identity_verified")
		if bool(checks.get("refund_chain_ok")):
			passed.append("refund_chain_ok")
		if not bool(checks.get("refund_over_200")):
			passed.append("amount_within_limit")
		if bool(checks.get("warranty_escalation_ok")):
			passed.append("warranty_policy_ok")
		if str(checks.get("execution_status", "")) == "completed":
			passed.append("execution_completed")

		seen: set[str] = set()
		result: list[str] = []
		for item in passed:
			if item in seen:
				continue
			seen.add(item)
			result.append(item)
		return result

	def _build_approval_reasoning(
		self,
		*,
		plan: dict[str, Any],
		review: dict[str, Any],
		policy_reason_codes: list[str],
		evidence_used: list[str],
		policy_checks_passed: list[str],
	) -> dict[str, str]:
		case_type = str(plan.get("case_type", "unknown"))
		llm_hint = str(review.get("approval_reasoning_hint", "")).strip()

		non_escalation_reason = next(
			(
				reason
				for reason in policy_reason_codes
				if reason not in MANDATORY_ESCALATION_POLICY_REASON_CODES
			),
			"",
		)

		if non_escalation_reason == "return_window_expired":
			code = "policy_denial_return_window_expired"
			text = "Resolved without escalation: the return/refund window has expired based on policy and order timeline."
			summary = "Return/refund not eligible after policy window."
		elif non_escalation_reason == "cancellation_not_permitted_for_order_status":
			code = "policy_denial_cancellation_window_closed"
			text = "Resolved without escalation: order status is beyond cancellation stage according to policy."
			summary = "Cancellation not allowed at current order status."
		elif non_escalation_reason == "damaged_item_requires_photo_evidence":
			code = "policy_requires_photo_evidence"
			text = "Resolved without escalation: photo evidence is required for damaged-item refund processing."
			summary = "Photo evidence required to continue damaged-item claim."
		elif non_escalation_reason == "refund_eligibility_failed":
			code = "policy_denial_refund_ineligible"
			text = "Resolved without escalation: refund eligibility checks did not pass under current policy conditions."
			summary = "Refund not eligible under current policy checks."
		elif non_escalation_reason == "missing_order_id_for_refund":
			code = "policy_needs_order_reference_for_refund"
			text = "Resolved without escalation: a valid order reference is required before refund validation can proceed."
			summary = "Order reference required to process refund request."
		elif non_escalation_reason == "missing_order_id_for_cancellation":
			code = "policy_needs_order_reference_for_cancellation"
			text = "Resolved without escalation: a valid order reference is required before cancellation can be evaluated."
			summary = "Order reference required to process cancellation request."

		elif (
			case_type == "refund"
			and "customer_verified" in evidence_used
			and "order_verified" in evidence_used
			and "refund_eligibility_passed" in evidence_used
		):
			code = "refund_eligible_with_verified_order"
			text = (
				"Approved because the customer was verified, the order was found, "
				"refund eligibility passed, and no escalation policy was triggered."
			)
			summary = "Verified refund case within policy."
		elif case_type == "faq" and "knowledge_lookup_completed" in evidence_used and "customer_reply_sent" in evidence_used:
			code = "faq_response_with_policy_lookup"
			text = "Approved because policy knowledge lookup succeeded and a compliant response was sent to the customer."
			summary = "Verified FAQ response."
		elif case_type == "cancellation" and "order_cancelled" in evidence_used:
			code = "cancellation_allowed_and_completed"
			text = "Approved because cancellation eligibility was validated and the order cancellation completed successfully."
			summary = "Verified cancellation case within policy."
		else:
			code = "policy_safe_resolution"
			text = llm_hint or "Approved because deterministic policy checks passed and required evidence was successfully collected."
			summary = "Approved after deterministic safety checks passed."

		if not policy_checks_passed:
			policy_checks_passed.extend(["execution_completed"])

		return {
			"approval_reason_code": code,
			"approval_reason_text": text,
			"approval_summary": summary,
		}

	def _build_escalation_reasoning(self, *, policy_reason_codes: list[str], system_reason_codes: list[str]) -> dict[str, Any]:
		ranked: list[str] = []
		mandatory_policy = [
			code
			for code in policy_reason_codes
			if code in MANDATORY_ESCALATION_POLICY_REASON_CODES
		]
		non_mandatory_policy = [
			code
			for code in policy_reason_codes
			if code not in MANDATORY_ESCALATION_POLICY_REASON_CODES
		]

		for code in mandatory_policy:
			if code not in ranked:
				ranked.append(code)
		for code in non_mandatory_policy:
			if code not in ranked:
				ranked.append(code)
		for code in system_reason_codes:
			if code not in ranked:
				ranked.append(code)

		if not ranked:
			ranked = ["confidence_below_threshold"]

		primary_reason = ranked[0]
		contributing = ranked[1:]
		primary_text = self._reason_to_text(primary_reason)

		if contributing:
			contributing_text = ", ".join(self._reason_to_text(code) for code in contributing)
			reason_text = f"Escalated because {primary_text} Contributing factors: {contributing_text}"
		else:
			reason_text = f"Escalated because {primary_text}"

		summary = f"Escalated: {primary_text}"
		short_reason = REASON_SHORT_MAP.get(primary_reason, summary)

		return {
			"escalation_reason_codes": ranked,
			"primary_reason": primary_reason,
			"contributing_reasons": contributing,
			"escalation_reason_text": reason_text,
			"escalation_summary": summary,
			"short_reason": short_reason,
		}

	@staticmethod
	def _reason_to_text(reason_code: str) -> str:
		return REASON_TEXT_MAP.get(reason_code, reason_code.replace("_", " "))

	@staticmethod
	def _normalize_reason_code(raw_reason: str) -> str:
		normalized = raw_reason.strip().lower()
		normalized = normalized.replace(" ", "_").replace("-", "_")
		normalized = re.sub(r"[^a-z0-9_]", "", normalized)
		normalized = re.sub(r"_+", "_", normalized).strip("_")
		if not normalized:
			return ""
		return REASON_CANONICAL_ALIASES.get(normalized, normalized)

