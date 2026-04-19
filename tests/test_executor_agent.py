from __future__ import annotations

import unittest
from typing import Any

from app.agents.executor import ExecutorAgent


class StubAutoGenClient:
	def is_ready(self, *, role: str | None = None) -> bool:
		return False

	def generate_structured(self, **_: Any) -> dict[str, Any]:
		return {"success": False, "error": "disabled"}


class StubToolRegistry:
	def __init__(self) -> None:
		self.calls: list[str] = []

	def call_tool(self, tool_name: str, **_: Any) -> dict[str, Any]:
		self.calls.append(tool_name)
		if tool_name == "check_refund_eligibility":
			return {
				"success": True,
				"eligible": False,
				"reason": "Return window has expired for this order.",
			}
		if tool_name == "can_cancel_order":
			return {"success": True, "cancellable": False, "reason": "Order already shipped."}
		return {"success": True}


class ExecutorAgentTests(unittest.TestCase):
	def test_issue_refund_is_skipped_when_eligibility_fails(self) -> None:
		registry = StubToolRegistry()
		agent = ExecutorAgent(tool_registry=registry, autogen_client=StubAutoGenClient())
		plan = {
			"ticket_id": "T1",
			"plan_id": "P1",
			"case_type": "refund",
			"proposed_action": "issue_refund",
			"tool_calls": [
				{"tool": "check_refund_eligibility", "params": {"order_id": "ORD-1"}},
				{"tool": "issue_refund", "params": {"order_id": "ORD-1"}},
			],
		}

		result = agent.execute_plan(plan)
		steps = result["steps"]

		self.assertEqual(result["execution_status"], "completed")
		self.assertEqual(registry.calls, ["check_refund_eligibility"])
		self.assertTrue(steps[1]["skipped"])
		self.assertTrue(steps[1]["result"]["policy_blocked"])
		self.assertFalse(steps[1]["result"]["eligible"])

	def test_cancel_order_without_precheck_fails_guard_block(self) -> None:
		registry = StubToolRegistry()
		agent = ExecutorAgent(tool_registry=registry, autogen_client=StubAutoGenClient())
		plan = {
			"ticket_id": "T2",
			"plan_id": "P2",
			"case_type": "cancellation",
			"proposed_action": "cancel_order",
			"tool_calls": [{"tool": "cancel_order", "params": {"order_id": "ORD-2"}}],
		}

		result = agent.execute_plan(plan)
		self.assertEqual(result["execution_status"], "failed")
		self.assertEqual(registry.calls, [])
		self.assertEqual(result["tool_failures"][0]["error_type"], "guard_block")


if __name__ == "__main__":
	unittest.main()
