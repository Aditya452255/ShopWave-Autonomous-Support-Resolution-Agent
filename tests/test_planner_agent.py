from __future__ import annotations

import unittest
from datetime import UTC, datetime
from typing import Any

from app.agents.planner import PlannerAgent
from app.schemas.ticket import Ticket


class StubAutoGenClient:
	def __init__(self, *, success: bool, structured: dict[str, Any] | None = None, enabled: bool = False) -> None:
		self._success = success
		self._structured = structured or {}
		self._enabled = enabled

	def generate_structured(self, **_: Any) -> dict[str, Any]:
		if self._success:
			return {"success": True, "structured": self._structured}
		return {"success": False, "error": "disabled"}

	def is_ready(self, *, role: str | None = None) -> bool:
		return self._enabled if role else self._enabled


def _ticket(subject: str, body: str, expected_action: str = "auto") -> Ticket:
	return Ticket(
		ticket_id="TICK-1001",
		customer_email="jane@example.com",
		subject=subject,
		body=body,
		source="email",
		created_at=datetime.now(tz=UTC),
		tier=2,
		expected_action=expected_action,
	)


class PlannerAgentTests(unittest.TestCase):
	def test_refund_with_order_adds_refund_chain(self) -> None:
		agent = PlannerAgent(autogen_client=StubAutoGenClient(success=False))
		plan = agent.create_action_plan(
			_ticket(
				subject="Refund request",
				body="Please refund order ORD-12345. I no longer need this item.",
			)
		)

		self.assertEqual(plan["case_type"], "refund")
		self.assertEqual(plan["proposed_action"], "issue_refund")
		tools = [item["tool"] for item in plan["tool_calls"]]
		self.assertIn("check_refund_eligibility", tools)
		self.assertIn("issue_refund", tools)
		self.assertFalse(plan["requires_escalation"])

	def test_damaged_item_without_photos_requests_evidence(self) -> None:
		agent = PlannerAgent(autogen_client=StubAutoGenClient(success=False))
		plan = agent.create_action_plan(
			_ticket(
				subject="Damaged delivery",
				body="My order ORD-7788 arrived damaged and cracked.",
			)
		)

		self.assertEqual(plan["case_type"], "damaged_item")
		self.assertEqual(plan["proposed_action"], "send_reply")
		self.assertFalse(plan["requires_escalation"])
		tools = [item["tool"] for item in plan["tool_calls"]]
		self.assertIn("send_reply", tools)

	def test_warranty_case_forces_escalation(self) -> None:
		agent = PlannerAgent(autogen_client=StubAutoGenClient(success=False))
		plan = agent.create_action_plan(
			_ticket(
				subject="Warranty claim",
				body="I need warranty support for order ORD-1000.",
			)
		)

		self.assertEqual(plan["case_type"], "warranty")
		self.assertTrue(plan["requires_escalation"])
		self.assertIn("warranty_claim_requires_manual_review", plan["escalation_reasons"])

	def test_llm_reason_allowlist_filters_invalid_reasons(self) -> None:
		autogen = StubAutoGenClient(
			success=True,
			enabled=True,
			structured={
				"requires_escalation": True,
				"escalation_reasons": [
					"tool_execution_failed",
					"fraud_or_legal_risk_signal",
					"totally_new_reason",
				],
			},
		)
		agent = PlannerAgent(autogen_client=autogen)
		plan = agent.create_action_plan(
			_ticket(
				subject="General question",
				body="Can I get policy details for delayed order updates?",
			)
		)

		self.assertTrue(plan["requires_escalation"])
		self.assertIn("fraud_or_legal_risk_signal", plan["escalation_reasons"])
		self.assertNotIn("tool_execution_failed", plan["escalation_reasons"])
		self.assertNotIn("totally_new_reason", plan["escalation_reasons"])


if __name__ == "__main__":
	unittest.main()
