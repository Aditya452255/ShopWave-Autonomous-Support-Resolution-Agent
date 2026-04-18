from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any


class CommunicationTools:
	def send_reply(
		self,
		*,
		customer_email: str,
		message: str,
		subject: str | None = None,
		customer_name: str | None = None,
		channels: list[str] | None = None,
	) -> dict[str, object]:
		first_name = self._resolve_first_name(customer_email, customer_name)
		selected_channels = channels or ["email"]
		reply_subject = subject or "ShopWave Support Update"
		final_message = f"Hi {first_name},\n\n{message}\n\nBest,\nShopWave Support"

		return {
			"success": True,
			"message_id": f"MSG-{uuid.uuid4().hex[:10].upper()}",
			"customer_email": customer_email,
			"subject": reply_subject,
			"message": final_message,
			"channels": selected_channels,
			"sent_at": datetime.now(tz=UTC).isoformat(),
		}

	def escalate(
		self,
		*,
		ticket_id: str,
		reason: str,
		summary: str,
		priority: str = "normal",
		context: dict[str, Any] | None = None,
	) -> dict[str, object]:
		escalation_id = f"ESC-{uuid.uuid4().hex[:10].upper()}"
		return {
			"success": True,
			"escalation_id": escalation_id,
			"ticket_id": ticket_id,
			"reason": reason,
			"summary": summary,
			"priority": priority,
			"context": context or {},
			"created_at": datetime.now(tz=UTC).isoformat(),
			"status": "queued_for_human_review",
		}

	@staticmethod
	def _resolve_first_name(customer_email: str, customer_name: str | None) -> str:
		if customer_name and customer_name.strip():
			return customer_name.strip().split()[0]

		local_part = customer_email.split("@", maxsplit=1)[0]
		token = local_part.replace("_", ".").split(".")[0]
		if not token:
			return "there"
		return token.capitalize()

