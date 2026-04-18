from __future__ import annotations

import json
from typing import Any

from app.schemas.order import Order
from app.services.data_loader import DataLoader, DataLoaderError
from config.settings import AppSettings, settings


class OrderTools:
	def __init__(self, app_settings: AppSettings | None = None, data_loader: DataLoader | None = None) -> None:
		self.settings = app_settings or settings
		self.data_loader = data_loader or DataLoader(self.settings)

	def get_order(self, order_id: str) -> dict[str, object]:
		try:
			orders = self.data_loader.load_orders()
		except DataLoaderError as exc:
			return {"success": False, "error": str(exc)}

		order = next((item for item in orders if item.order_id == order_id), None)
		if not order:
			return {"success": False, "error": f"Order {order_id} not found"}

		return {"success": True, "order": order.model_dump(mode="json")}

	def get_customer(self, *, customer_id: str | None = None, email: str | None = None) -> dict[str, object]:
		if not customer_id and not email:
			return {"success": False, "error": "Provide customer_id or email"}

		try:
			customers = self.data_loader.load_customers()
		except DataLoaderError as exc:
			return {"success": False, "error": str(exc)}

		normalized_email = email.lower() if email else None
		customer = next(
			(
				item
				for item in customers
				if (customer_id and item.customer_id == customer_id)
				or (normalized_email and item.email.lower() == normalized_email)
			),
			None,
		)

		if not customer:
			return {"success": False, "error": "Customer not found"}

		return {"success": True, "customer": customer.model_dump(mode="json")}

	def get_product(self, product_id: str) -> dict[str, object]:
		products = self._load_products()
		product = next((item for item in products if str(item.get("product_id")) == product_id), None)

		if not product:
			return {"success": False, "error": f"Product {product_id} not found"}

		return {"success": True, "product": product}

	def get_customer_orders(self, customer_id: str) -> dict[str, object]:
		try:
			orders = self.data_loader.load_orders()
		except DataLoaderError as exc:
			return {"success": False, "error": str(exc)}

		matched = [order.model_dump(mode="json") for order in orders if order.customer_id == customer_id]
		return {"success": True, "orders": matched, "count": len(matched)}

	def get_customer_orders_by_email(self, email: str) -> dict[str, object]:
		customer_result = self.get_customer(email=email)
		if not customer_result.get("success"):
			return {
				"success": False,
				"error": "Customer not found for provided email.",
				"email": email,
			}

		customer = customer_result["customer"]
		orders_result = self.get_customer_orders(customer["customer_id"])
		if not orders_result.get("success"):
			return orders_result

		return {
			"success": True,
			"email": email,
			"customer": customer,
			"orders": orders_result.get("orders", []),
			"count": orders_result.get("count", 0),
		}

	def cancel_latest_processing_order_for_email(
		self,
		email: str,
		*,
		reason: str = "Customer requested cancellation",
	) -> dict[str, object]:
		orders_by_email = self.get_customer_orders_by_email(email)
		if not orders_by_email.get("success"):
			return orders_by_email

		orders = orders_by_email.get("orders", [])
		if not isinstance(orders, list):
			return {
				"success": False,
				"email": email,
				"error": "Order lookup returned invalid payload.",
			}

		processing = [
			order
			for order in orders
			if isinstance(order, dict) and str(order.get("status", "")).strip().lower() == "processing"
		]
		processing.sort(key=lambda item: str(item.get("order_date", "")), reverse=True)

		if not processing:
			return {
				"success": True,
				"email": email,
				"policy_blocked": True,
				"cancellable": False,
				"reason": "No processing order found for this customer email.",
				"requires_escalation": False,
			}

		if len(processing) > 1:
			candidates = [str(item.get("order_id", "")) for item in processing[:5]]
			return {
				"success": False,
				"email": email,
				"error": "Multiple processing orders found. Confirmation of target order is required.",
				"requires_escalation": True,
				"candidate_order_ids": candidates,
			}

		target_order_id = str(processing[0].get("order_id", "")).strip()
		if not target_order_id:
			return {
				"success": False,
				"email": email,
				"error": "Resolved processing order has no order_id.",
				"requires_escalation": True,
			}

		cancel_result = self.cancel_order(target_order_id, reason=reason)
		if not cancel_result.get("success"):
			return {
				"success": False,
				"email": email,
				"order_id": target_order_id,
				"error": str(cancel_result.get("error", "Cancellation failed.")),
				"requires_escalation": False,
			}

		return {
			"success": True,
			"email": email,
			"order_id": target_order_id,
			"message": "Latest processing order was cancelled successfully via email lookup.",
			"order": cancel_result.get("order"),
			"persisted": cancel_result.get("persisted", False),
		}

	def can_cancel_order(self, order_id: str) -> dict[str, object]:
		result = self.get_order(order_id)
		if not result.get("success"):
			return result

		order = result["order"]
		if order["status"] == "processing":
			return {
				"success": True,
				"order_id": order_id,
				"cancellable": True,
				"reason": "Order is in processing status and can be cancelled.",
			}

		return {
			"success": True,
			"order_id": order_id,
			"cancellable": False,
			"reason": f"Order with status '{order['status']}' cannot be cancelled.",
		}

	def cancel_order(self, order_id: str, *, reason: str = "Customer requested cancellation") -> dict[str, object]:
		cancellation_check = self.can_cancel_order(order_id)
		if not cancellation_check.get("success"):
			return cancellation_check
		if not cancellation_check.get("cancellable"):
			return {
				"success": False,
				"error": cancellation_check["reason"],
				"order_id": order_id,
			}

		try:
			orders = self.data_loader.load_orders()
		except DataLoaderError as exc:
			return {"success": False, "error": str(exc)}

		updated_order: Order | None = None
		for order in orders:
			if order.order_id == order_id:
				order.status = "cancelled"
				order.notes = f"{order.notes} Cancellation reason: {reason}".strip()
				updated_order = order
				break

		if not updated_order:
			return {"success": False, "error": f"Order {order_id} not found"}

		if self.settings.persist_tool_mutations:
			self._save_orders(orders)
		return {
			"success": True,
			"order_id": order_id,
			"persisted": self.settings.persist_tool_mutations,
			"order": updated_order.model_dump(mode="json"),
			"message": "Order cancelled successfully.",
		}

	def get_order_with_product(self, order_id: str) -> dict[str, object]:
		order_result = self.get_order(order_id)
		if not order_result.get("success"):
			return order_result

		order = order_result["order"]
		product_result = self.get_product(order["product_id"])
		if not product_result.get("success"):
			return {
				"success": False,
				"error": product_result["error"],
				"order": order,
			}

		return {
			"success": True,
			"order": order,
			"product": product_result["product"],
		}

	def _load_products(self) -> list[dict[str, Any]]:
		products_file = self.settings.products_file
		if not products_file.exists():
			raise DataLoaderError(f"Data file not found: {products_file}")

		raw = json.loads(products_file.read_text(encoding="utf-8-sig"))
		if not isinstance(raw, list):
			raise DataLoaderError(f"Expected a JSON array in {products_file}")
		return [item for item in raw if isinstance(item, dict)]

	def _save_orders(self, orders: list[Order]) -> None:
		serializable_orders = [order.model_dump(mode="json") for order in orders]
		payload = json.dumps(serializable_orders, indent=2)
		self.settings.orders_file.write_text(payload, encoding="utf-8")

