from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.orchestrator import TicketOrchestrator
from app.schemas.ticket import Ticket
from app.services.confidence import ConfidenceService
from config.settings import AppSettings, settings


class StubPlanner:
	def __init__(self, plan: dict[str, Any], *, should_raise: bool = False) -> None:
		self.plan = plan
		self.should_raise = should_raise

	def create_action_plan(self, _: Any) -> dict[str, Any]:
		if self.should_raise:
			raise RuntimeError("planner boom")
		return self.plan


class StubExecutor:
	def __init__(self, execution: dict[str, Any]) -> None:
		self.execution = execution

	def execute_plan(self, _: Any) -> dict[str, Any]:
		return self.execution


class StubCritic:
	def __init__(self, review: dict[str, Any]) -> None:
		self.payload = review

	def review(self, *_: Any) -> dict[str, Any]:
		return self.payload


class StubConfidence:
	def __init__(self, payload: dict[str, Any]) -> None:
		self.payload = payload

	def assess(self, **_: Any) -> dict[str, Any]:
		return self.payload


def _ticket() -> Ticket:
	return Ticket(
		ticket_id="T-ORCH-1",
		customer_email="user@example.com",
		subject="Refund request",
		body="Please refund order ORD-9999.",
		source="email",
		created_at=datetime.now(tz=UTC),
		tier=2,
		expected_action="refund",
	)


def _settings_for_temp_dir(temp_dir: str) -> AppSettings:
	payload = {
		**settings.model_dump(),
		"project_root": Path(temp_dir),
		"orchestration_mode": "deterministic",
		"enable_autogen": False,
	}
	return AppSettings(**payload)


class OrchestratorAndConfidenceTests(unittest.IsolatedAsyncioTestCase):
	async def test_orchestrator_returns_approve_when_safe(self) -> None:
		plan = {
			"ticket_id": "T-ORCH-1",
			"plan_id": "PLAN-1",
			"case_type": "refund",
			"summary": "refund case",
			"tool_calls": [
				{"tool": "get_customer", "params": {}},
				{"tool": "check_refund_eligibility", "params": {}},
				{"tool": "issue_refund", "params": {}},
			],
			"proposed_action": "issue_refund",
			"requires_escalation": False,
			"escalation_reasons": [],
		}
		execution = {
			"execution_status": "completed",
			"tool_failures": [],
			"steps": [
				{"tool": "get_customer", "success": True, "result": {"success": True}},
				{"tool": "check_refund_eligibility", "success": True, "result": {"success": True, "eligible": True}},
				{"tool": "issue_refund", "success": True, "result": {"success": True}},
			],
		}
		review = {
			"final_decision": "approve",
			"must_escalate": False,
			"policy_compliant": True,
			"checks": {
				"get_customer_verified": True,
				"refund_chain_ok": True,
				"refund_over_200": False,
				"execution_status": "completed",
			},
			"violations": [],
			"policy_reasons": [],
			"system_reasons": [],
		}
		confidence = {
			"score": 0.92,
			"escalation_recommended": False,
			"threshold": 0.6,
			"below_threshold": False,
		}

		with tempfile.TemporaryDirectory() as temp_dir:
			orchestrator = TicketOrchestrator(
				app_settings=_settings_for_temp_dir(temp_dir),
				planner=StubPlanner(plan),
				executor=StubExecutor(execution),
				critic=StubCritic(review),
				confidence_service=StubConfidence(confidence),
			)
			result = await orchestrator.process_ticket(_ticket())

		self.assertEqual(result["final_decision"], "approve")
		self.assertTrue(bool(result.get("approval_reason_code")))
		self.assertTrue(bool(result.get("approval_summary")))

	async def test_orchestrator_escalates_for_mandatory_policy_reason(self) -> None:
		plan = {
			"ticket_id": "T-ORCH-1",
			"plan_id": "PLAN-2",
			"case_type": "warranty",
			"summary": "warranty case",
			"tool_calls": [{"tool": "get_customer", "params": {}}],
			"proposed_action": "escalate",
			"requires_escalation": False,
			"escalation_reasons": [],
		}
		execution = {
			"execution_status": "completed",
			"tool_failures": [],
			"steps": [{"tool": "get_customer", "success": True, "result": {"success": True}}],
		}
		review = {
			"final_decision": "approve",
			"must_escalate": False,
			"policy_compliant": True,
			"checks": {"get_customer_verified": True, "execution_status": "completed"},
			"violations": [],
			"policy_reasons": ["warranty_claim_requires_manual_review"],
			"system_reasons": [],
		}
		confidence = {
			"score": 0.84,
			"escalation_recommended": False,
			"threshold": 0.6,
			"below_threshold": False,
		}

		with tempfile.TemporaryDirectory() as temp_dir:
			orchestrator = TicketOrchestrator(
				app_settings=_settings_for_temp_dir(temp_dir),
				planner=StubPlanner(plan),
				executor=StubExecutor(execution),
				critic=StubCritic(review),
				confidence_service=StubConfidence(confidence),
			)
			result = await orchestrator.process_ticket(_ticket())

		self.assertEqual(result["final_decision"], "escalate")
		self.assertEqual(result["primary_reason"], "warranty_claim_requires_manual_review")

	async def test_orchestrator_falls_back_to_safe_escalation_on_exception(self) -> None:
		with tempfile.TemporaryDirectory() as temp_dir:
			orchestrator = TicketOrchestrator(
				app_settings=_settings_for_temp_dir(temp_dir),
				planner=StubPlanner({}, should_raise=True),
				executor=StubExecutor({}),
				critic=StubCritic({}),
				confidence_service=StubConfidence({}),
			)
			result = await orchestrator.process_ticket(_ticket())

		self.assertEqual(result["final_decision"], "escalate")
		self.assertIn("planner boom", result.get("error", ""))
		self.assertIn("tool_execution_failed", result.get("escalation_reason_codes", []))

	def test_confidence_service_recommends_escalation_when_score_low(self) -> None:
		service = ConfidenceService()
		assessment = service.assess(
			plan={"confidence_hint": 0.2, "case_type": "exchange", "requires_escalation": True},
			execution={"execution_status": "failed", "tool_failures": [{"error": "x"}]},
			critic_review={"violations": ["policy_violation"]},
		)

		self.assertTrue(assessment["escalation_recommended"])
		self.assertTrue(assessment["below_threshold"])
		self.assertLess(assessment["score"], assessment["threshold"])


if __name__ == "__main__":
	unittest.main()
