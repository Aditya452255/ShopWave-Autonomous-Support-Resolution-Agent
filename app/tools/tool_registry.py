from __future__ import annotations

from typing import Any, Callable

from app.tools.communication_tools import CommunicationTools
from app.tools.failure_simulator import FailureSimulator, ToolTimeoutError
from app.tools.knowledge_tools import KnowledgeTools
from app.tools.order_tools import OrderTools
from app.tools.refund_tools import RefundTools
from config.settings import AppSettings, settings

ToolHandler = Callable[..., dict[str, object] | str]


class ToolRegistry:
	def __init__(
		self,
		*,
		app_settings: AppSettings | None = None,
		knowledge_tools: KnowledgeTools | None = None,
		order_tools: OrderTools | None = None,
		refund_tools: RefundTools | None = None,
		communication_tools: CommunicationTools | None = None,
		failure_simulator: FailureSimulator | None = None,
	) -> None:
		self.settings = app_settings or settings
		self.knowledge_tools = knowledge_tools or KnowledgeTools(self.settings)
		self.order_tools = order_tools or OrderTools(self.settings)
		self.refund_tools = refund_tools or RefundTools(
			app_settings=self.settings,
			order_tools=self.order_tools,
		)
		self.communication_tools = communication_tools or CommunicationTools()
		self.failure_simulator = failure_simulator or FailureSimulator()
		self._tools: dict[str, ToolHandler] = {}
		self._register_defaults()

	def register_tool(self, name: str, handler: ToolHandler) -> None:
		normalized_name = name.strip().lower()
		if not normalized_name:
			raise ValueError("Tool name cannot be empty")
		self._tools[normalized_name] = handler

	def get_tool(self, name: str) -> ToolHandler:
		normalized_name = name.strip().lower()
		if normalized_name not in self._tools:
			raise KeyError(f"Tool '{name}' is not registered")
		return self._tools[normalized_name]

	def has_tool(self, name: str) -> bool:
		return name.strip().lower() in self._tools

	def list_tools(self) -> list[str]:
		return sorted(self._tools.keys())

	def call_tool(self, name: str, **kwargs: Any) -> dict[str, object]:
		try:
			handler = self.get_tool(name)
		except KeyError as exc:
			return {
				"success": False,
				"tool": name,
				"error": str(exc),
				"error_type": "tool_not_found",
			}

		try:
			raw_result = handler(**kwargs)
		except ToolTimeoutError as exc:
			return {
				"success": False,
				"tool": name,
				"error": str(exc),
				"error_type": "timeout",
			}
		except Exception as exc:  # noqa: BLE001
			return {
				"success": False,
				"tool": name,
				"error": str(exc),
				"error_type": "runtime_error",
			}

		if isinstance(raw_result, dict):
			return {"tool": name, **raw_result}

		return {
			"success": True,
			"tool": name,
			"result": raw_result,
		}

	def _register_defaults(self) -> None:
		self.register_tool("search_knowledge_base", self.knowledge_tools.search_knowledge_base)
		self.register_tool("searchknowledgebase", self.knowledge_tools.search_knowledge_base)

		self.register_tool("get_order", self.order_tools.get_order)
		self.register_tool("getorder", self.order_tools.get_order)
		self.register_tool("get_customer", self.order_tools.get_customer)
		self.register_tool("getcustomer", self.order_tools.get_customer)
		self.register_tool("get_product", self.order_tools.get_product)
		self.register_tool("getproduct", self.order_tools.get_product)
		self.register_tool("can_cancel_order", self.order_tools.can_cancel_order)
		self.register_tool("cancel_order", self.order_tools.cancel_order)
		self.register_tool("get_order_with_product", self.order_tools.get_order_with_product)
		self.register_tool("get_customer_orders", self.order_tools.get_customer_orders)
		self.register_tool("get_customer_orders_by_email", self.order_tools.get_customer_orders_by_email)
		self.register_tool("cancel_latest_processing_order_for_email", self.order_tools.cancel_latest_processing_order_for_email)

		self.register_tool("check_refund_eligibility", self.refund_tools.check_refund_eligibility)
		self.register_tool("checkrefundeligibility", self.refund_tools.check_refund_eligibility)
		self.register_tool("issue_refund", self.refund_tools.issue_refund)
		self.register_tool("issuerefund", self.refund_tools.issue_refund)
		self.register_tool("issue_refund_for_email", self.refund_tools.issue_refund_for_email)

		self.register_tool("send_reply", self.communication_tools.send_reply)
		self.register_tool("sendreply", self.communication_tools.send_reply)
		self.register_tool("escalate", self.communication_tools.escalate)

		self.register_tool("simulate_failure", self.failure_simulator.inject_failure)

