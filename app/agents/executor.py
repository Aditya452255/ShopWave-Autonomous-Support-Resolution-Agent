from __future__ import annotations

from typing import Any

from app.services.autogen_client import AutoGenGroqClient
from app.tools.tool_registry import ToolRegistry
from config.prompts import get_prompt
from config.settings import AppSettings, settings


class ExecutorAgent:
	def __init__(
		self,
		app_settings: AppSettings | None = None,
		tool_registry: ToolRegistry | None = None,
		autogen_client: AutoGenGroqClient | None = None,
	) -> None:
		self.settings = app_settings or settings
		self.tool_registry = tool_registry or ToolRegistry(app_settings=self.settings)
		self.autogen_client = autogen_client or AutoGenGroqClient(self.settings)

	def execute_plan(self, plan: dict[str, Any]) -> dict[str, object]:
		autogen_result: dict[str, Any]
		autogen_structured: dict[str, Any]
		if self.autogen_client.is_ready(role="executor"):
			autogen_result = self.autogen_client.generate_structured(
				role="executor",
				system_prompt=get_prompt("executor"),
				payload={"plan": plan},
			)
			autogen_structured = autogen_result.get("structured", {}) if autogen_result.get("success") else {}
		else:
			autogen_result = {
				"success": False,
				"role": "executor",
				"error": "AutoGen disabled for executor role.",
			}
			autogen_structured = {}

		tool_calls = plan.get("tool_calls", [])
		steps: list[dict[str, object]] = []
		tool_failures: list[dict[str, object]] = []
		results_by_tool: dict[str, dict[str, object]] = {}

		for index, call in enumerate(tool_calls, start=1):
			tool_name = str(call.get("tool", "")).strip()
			params = call.get("params", {})
			if not isinstance(params, dict):
				params = {}

			skip_reason = self._get_skip_reason(tool_name=tool_name, results_by_tool=results_by_tool)
			if skip_reason:
				if skip_reason.startswith("policy_ineligible:"):
					policy_reason = skip_reason.split(":", maxsplit=1)[1].strip()
					step_result = {
						"step": index,
						"tool": tool_name,
						"params": params,
						"success": True,
						"skipped": True,
						"result": {
							"success": True,
							"policy_blocked": True,
							"eligible": False,
							"reason": policy_reason,
						},
					}
					steps.append(step_result)
					results_by_tool[tool_name] = step_result["result"]
					continue

				step_result = {
					"step": index,
					"tool": tool_name,
					"params": params,
					"success": False,
					"skipped": True,
					"result": {"success": False, "error": skip_reason, "error_type": "guard_block"},
				}
				steps.append(step_result)
				tool_failures.append(
					{
						"step": index,
						"tool": tool_name,
						"error": skip_reason,
						"error_type": "guard_block",
					}
				)
				continue

			result = self.tool_registry.call_tool(tool_name, **params)
			success = bool(result.get("success"))

			step_result = {
				"step": index,
				"tool": tool_name,
				"params": params,
				"success": success,
				"skipped": False,
				"result": result,
			}
			steps.append(step_result)

			if success:
				results_by_tool[tool_name] = result
			else:
				tool_failures.append(
					{
						"step": index,
						"tool": tool_name,
						"error": str(result.get("error", "Unknown tool failure")),
						"error_type": str(result.get("error_type", "unknown")),
					}
				)

		execution_status = self._resolve_status(steps=steps, failures=tool_failures)
		action_outcome = self._resolve_action_outcome(plan=plan, steps=steps)

		return {
			"agent": "executor",
			"ticket_id": plan.get("ticket_id"),
			"plan_id": plan.get("plan_id"),
			"case_type": plan.get("case_type"),
			"autogen": {
				"enabled": self.autogen_client.is_ready(role="executor"),
				"success": bool(autogen_result.get("success")),
				"structured": autogen_structured,
				"error": autogen_result.get("error"),
			},
			"execution_status": execution_status,
			"proposed_action": plan.get("proposed_action"),
			"steps": steps,
			"tool_failures": tool_failures,
			"action_outcome": action_outcome,
		}

	@staticmethod
	def _get_skip_reason(tool_name: str, results_by_tool: dict[str, dict[str, object]]) -> str | None:
		normalized_tool = tool_name.strip().lower()
		if normalized_tool == "issue_refund":
			eligibility = results_by_tool.get("check_refund_eligibility")
			if not eligibility:
				return "Cannot issue refund before refund eligibility check."
			if not bool(eligibility.get("eligible")):
				reason = str(eligibility.get("reason", "Refund eligibility check returned ineligible."))
				return f"policy_ineligible:{reason}"

		if normalized_tool == "cancel_order":
			cancel_check = results_by_tool.get("can_cancel_order")
			if not cancel_check:
				return "Cannot cancel order before cancellation eligibility check."
			if not bool(cancel_check.get("cancellable")):
				reason = str(cancel_check.get("reason", "Cancellation check returned not cancellable."))
				return f"policy_ineligible:{reason}"

		return None

	@staticmethod
	def _resolve_status(steps: list[dict[str, object]], failures: list[dict[str, object]]) -> str:
		if not steps:
			return "failed"
		if not failures:
			return "completed"

		success_count = sum(1 for step in steps if bool(step.get("success")))
		if success_count == 0:
			return "failed"
		return "partial"

	@staticmethod
	def _resolve_action_outcome(plan: dict[str, Any], steps: list[dict[str, object]]) -> dict[str, object]:
		action_to_tool = {
			"issue_refund": "issue_refund",
			"issue_refund_by_email": "issue_refund_for_email",
			"cancel_order": "cancel_order",
			"cancel_order_by_email": "cancel_latest_processing_order_for_email",
			"send_reply": "send_reply",
			"escalate": "escalate",
		}
		proposed_action = str(plan.get("proposed_action", "")).strip().lower()
		target_tool = action_to_tool.get(proposed_action)

		if not target_tool:
			return {
				"resolved": False,
				"reason": f"No action outcome mapping for proposed action '{proposed_action}'.",
			}

		matching_steps = [step for step in steps if str(step.get("tool", "")).lower() == target_tool]
		if not matching_steps:
			return {
				"resolved": False,
				"reason": f"Action tool '{target_tool}' was not executed.",
			}

		last = matching_steps[-1]
		return {
			"resolved": bool(last.get("success")),
			"tool": target_tool,
			"step": last.get("step"),
			"result": last.get("result"),
		}

