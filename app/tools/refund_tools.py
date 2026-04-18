from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from app.schemas.order import Order
from app.services.data_loader import DataLoader, DataLoaderError
from app.tools.order_tools import OrderTools
from config.settings import AppSettings, settings


class RefundTools:
	def __init__(
		self,
		app_settings: AppSettings | None = None,
		data_loader: DataLoader | None = None,
		order_tools: OrderTools | None = None,
	) -> None:
		self.settings = app_settings or settings
		self.data_loader = data_loader or DataLoader(self.settings)
		self.order_tools = order_tools or OrderTools(self.settings, self.data_loader)

	def check_refund_eligibility(
		self,
		order_id: str,
		*,
		reason: str,
		photo_evidence: bool = False,
		requested_amount: float | None = None,
		reference_date: str | None = None,
	) -> dict[str, object]:
		order_result = self.order_tools.get_order(order_id)
		if not order_result.get("success"):
			return {
				"success": False,
				"eligible": False,
				"order_id": order_id,
				"reason": order_result.get("error", "Order not found"),
				"requires_escalation": True,
			}

		order = order_result["order"]
		normalized_reason = reason.strip().lower()
		effective_amount = requested_amount if requested_amount is not None else float(order["amount"])
		evaluation_date = self._resolve_reference_date(reference_date)

		customer_result = self.order_tools.get_customer(customer_id=order["customer_id"])
		customer = customer_result.get("customer", {}) if customer_result.get("success") else {}
		customer_tier = str(customer.get("tier", "standard")).strip().lower()
		customer_notes = str(customer.get("notes", "")).lower()

		product_result = self.order_tools.get_product(order["product_id"])
		product = product_result.get("product", {}) if product_result.get("success") else {}
		product_notes = str(product.get("notes", "")).lower()
		product_return_days = self._safe_int(product.get("return_window_days"))

		is_damaged_or_defective = any(
			token in normalized_reason
			for token in ("damaged", "defective", "broken", "cracked", "manufacturing defect")
		)
		is_wrong_item = any(
			token in normalized_reason
			for token in ("wrong item", "wrong colour", "wrong color", "wrong size")
		)

		if order.get("refund_status") == "refunded":
			return self._ineligible(order_id, "Refund already completed for this order.")

		if "warranty" in normalized_reason:
			return self._ineligible(
				order_id,
				"Warranty claims require escalation to warranty team.",
				requires_escalation=True,
			)

		if effective_amount > 200:
			return self._ineligible(
				order_id,
				"Refund requests above $200 require escalation approval.",
				requires_escalation=True,
			)

		if order["status"] != "delivered":
			if order["status"] == "processing":
				return self._ineligible(order_id, "Order is processing. Use cancellation flow instead.")
			return self._ineligible(
				order_id,
				f"Order status is '{order['status']}', refund is not available yet.",
			)

		if is_damaged_or_defective and not photo_evidence:
			return self._ineligible(
				order_id,
				"Photo evidence is required for damaged or defective-on-arrival claims.",
			)

		if is_damaged_or_defective and photo_evidence:
			return {
				"success": True,
				"eligible": True,
				"order_id": order_id,
				"evaluation_date": evaluation_date.isoformat(),
				"reason": "Damaged/defective-on-arrival claim is eligible with photo evidence.",
				"requires_escalation": False,
				"approved_amount": round(effective_amount, 2),
				"customer_tier": customer_tier,
			}

		if is_wrong_item:
			return {
				"success": True,
				"eligible": True,
				"order_id": order_id,
				"evaluation_date": evaluation_date.isoformat(),
				"reason": "Wrong item delivered is eligible regardless of standard return window.",
				"requires_escalation": False,
				"approved_amount": round(effective_amount, 2),
				"customer_tier": customer_tier,
			}

		if "registered online" in product_notes and not is_damaged_or_defective and not is_wrong_item:
			return self._ineligible(
				order_id,
				"This item is registered online and is non-returnable under policy.",
			)

		if any(token in product_notes for token in ("final sale", "non-returnable", "non returnable")):
			return self._ineligible(order_id, "This item is non-returnable under policy.")

		return_deadline = order.get("return_deadline")
		delivery_date_raw = order.get("delivery_date")
		delivery_date = datetime.fromisoformat(delivery_date_raw).date() if delivery_date_raw else None

		deadline_date = None
		if delivery_date and product_return_days is not None:
			deadline_date = delivery_date + timedelta(days=product_return_days)
		elif return_deadline:
			deadline_date = datetime.fromisoformat(return_deadline).date()

		if deadline_date is None:
			return self._ineligible(
				order_id,
				"Missing return deadline. Escalate for manual review.",
				requires_escalation=True,
			)

		if evaluation_date > deadline_date:
			days_outside = (evaluation_date - deadline_date).days
			vip_exception = (
				customer_tier == "vip"
				and any(token in customer_notes for token in ("pre-approved", "pre approved", "exception", "leniency"))
				and days_outside <= 30
			)
			premium_borderline = customer_tier == "premium" and 1 <= days_outside <= 3

			if premium_borderline:
				return self._ineligible(
					order_id,
					"Premium borderline case requires supervisor approval note.",
					requires_escalation=True,
				)

			if not vip_exception:
				return self._ineligible(
					order_id,
					"Return window has expired for this order.",
				)

		return {
			"success": True,
			"eligible": True,
			"order_id": order_id,
			"evaluation_date": evaluation_date.isoformat(),
			"reason": "Order meets refund eligibility requirements.",
			"requires_escalation": False,
			"approved_amount": round(effective_amount, 2),
			"customer_tier": customer_tier,
		}

	def issue_refund(
		self,
		order_id: str,
		*,
		reason: str,
		amount: float | None = None,
		photo_evidence: bool = False,
		reference_date: str | None = None,
	) -> dict[str, object]:
		eligibility = self.check_refund_eligibility(
			order_id,
			reason=reason,
			photo_evidence=photo_evidence,
			requested_amount=amount,
			reference_date=reference_date,
		)

		if not eligibility.get("success") or not eligibility.get("eligible"):
			return {
				"success": False,
				"order_id": order_id,
				"error": "Refund denied: eligibility check failed.",
				"eligibility": eligibility,
			}

		try:
			orders = self.data_loader.load_orders()
		except DataLoaderError as exc:
			return {"success": False, "order_id": order_id, "error": str(exc)}

		refunded_order: Order | None = None
		approved_amount = float(eligibility["approved_amount"])

		for order in orders:
			if order.order_id == order_id:
				order.refund_status = "refunded"
				order.notes = f"{order.notes} Refund issued for ${approved_amount:.2f}. Reason: {reason}".strip()
				refunded_order = order
				break

		if not refunded_order:
			return {"success": False, "order_id": order_id, "error": "Order not found during refund update."}

		if self.settings.persist_tool_mutations:
			self._save_orders(orders)

		return {
			"success": True,
			"order_id": order_id,
			"eligibility_checked": True,
			"refund_status": "refunded",
			"persisted": self.settings.persist_tool_mutations,
			"amount": round(approved_amount, 2),
			"refund_processing_time": "5-7 business days",
			"order": refunded_order.model_dump(mode="json"),
		}

	def issue_refund_for_email(
		self,
		email: str,
		*,
		reason: str,
		photo_evidence: bool = False,
		reference_date: str | None = None,
	) -> dict[str, object]:
		orders_by_email = self.order_tools.get_customer_orders_by_email(email)
		if not orders_by_email.get("success"):
			return {
				"success": False,
				"email": email,
				"error": str(orders_by_email.get("error", "Order lookup failed for email.")),
				"requires_escalation": False,
			}

		orders = orders_by_email.get("orders", [])
		if not isinstance(orders, list):
			return {
				"success": False,
				"email": email,
				"error": "Order lookup returned invalid payload.",
				"requires_escalation": True,
			}

		candidates: list[dict[str, object]] = []
		ineligible_reasons: list[str] = []
		for order in orders:
			if not isinstance(order, dict):
				continue
			if str(order.get("status", "")).strip().lower() != "delivered":
				continue
			if str(order.get("refund_status", "")).strip().lower() == "refunded":
				continue

			order_id = str(order.get("order_id", "")).strip()
			if not order_id:
				continue

			eligibility = self.check_refund_eligibility(
				order_id,
				reason=reason,
				photo_evidence=photo_evidence,
				reference_date=reference_date,
			)

			if bool(eligibility.get("success")) and bool(eligibility.get("eligible")):
				candidates.append({"order_id": order_id, "eligibility": eligibility})
			elif bool(eligibility.get("success")) and eligibility.get("eligible") is False:
				ineligible_reasons.append(str(eligibility.get("reason", "Refund eligibility checks did not pass.")))

		if not candidates:
			primary_reason = (
				ineligible_reasons[0]
				if ineligible_reasons
				else "No eligible delivered order was found for this customer email."
			)
			return {
				"success": True,
				"email": email,
				"policy_blocked": True,
				"eligible": False,
				"eligibility_checked": True,
				"reason": primary_reason,
				"requires_escalation": False,
			}

		if len(candidates) > 1:
			return {
				"success": False,
				"email": email,
				"error": "Multiple eligible orders found. Order confirmation is required before refund.",
				"requires_escalation": True,
				"candidate_order_ids": [item["order_id"] for item in candidates],
			}

		target_order_id = str(candidates[0]["order_id"])
		refund_result = self.issue_refund(
			target_order_id,
			reason=reason,
			photo_evidence=photo_evidence,
			reference_date=reference_date,
		)

		if not refund_result.get("success"):
			return {
				"success": False,
				"email": email,
				"order_id": target_order_id,
				"error": str(refund_result.get("error", "Refund failed.")),
				"requires_escalation": False,
			}

		return {
			"success": True,
			"email": email,
			"order_id": target_order_id,
			"eligibility_checked": True,
			"refund_status": refund_result.get("refund_status"),
			"amount": refund_result.get("amount"),
			"refund_processing_time": refund_result.get("refund_processing_time"),
			"persisted": refund_result.get("persisted", False),
			"order": refund_result.get("order"),
		}

	@staticmethod
	def _resolve_reference_date(reference_date: str | None) -> date:
		if not reference_date:
			return datetime.now(tz=UTC).date()

		candidate = reference_date.strip()
		if not candidate:
			return datetime.now(tz=UTC).date()

		candidate = candidate.replace("Z", "+00:00")
		try:
			parsed = datetime.fromisoformat(candidate)
			if parsed.tzinfo is None:
				return parsed.date()
			return parsed.astimezone(UTC).date()
		except ValueError:
			pass

		try:
			return date.fromisoformat(candidate)
		except ValueError:
			return datetime.now(tz=UTC).date()

	@staticmethod
	def _ineligible(order_id: str, reason: str, *, requires_escalation: bool = False) -> dict[str, object]:
		return {
			"success": True,
			"eligible": False,
			"order_id": order_id,
			"reason": reason,
			"requires_escalation": requires_escalation,
		}

	@staticmethod
	def _safe_int(value: object) -> int | None:
		if isinstance(value, int):
			return value
		if isinstance(value, float):
			return int(value)
		if isinstance(value, str):
			try:
				return int(value.strip())
			except ValueError:
				return None
		return None

	def _save_orders(self, orders: list[Order]) -> None:
		serializable_orders = [order.model_dump(mode="json") for order in orders]
		payload = json.dumps(serializable_orders, indent=2)
		self.settings.orders_file.write_text(payload, encoding="utf-8")

