from __future__ import annotations

import json
import re
from typing import Any

from config.settings import AppSettings, settings


class AutoGenGroqClient:
	def __init__(self, app_settings: AppSettings | None = None) -> None:
		self.settings = app_settings or settings
		self._autogen: Any | None = None
		self._import_error: str | None = None

		if self.settings.autogen_active and self.settings.groq_api_key:
			try:
				import autogen  # type: ignore

				self._autogen = autogen
			except Exception as exc:  # noqa: BLE001
				self._import_error = str(exc)

	def is_ready(self, *, role: str | None = None) -> bool:
		base_ready = bool(self._autogen) and bool(self.settings.groq_api_key) and self.settings.autogen_active
		if not base_ready:
			return False
		if role is None:
			return True
		return role.strip().lower() in self.settings.enabled_autogen_roles

	def generate_structured(
		self,
		*,
		role: str,
		system_prompt: str,
		payload: dict[str, Any],
	) -> dict[str, Any]:
		if not self.is_ready(role=role):
			role_enabled = role.strip().lower() in self.settings.enabled_autogen_roles
			disabled_reason = "AutoGen disabled for this role." if role_enabled is False else "AutoGen is disabled or unavailable."
			return {
				"success": False,
				"role": role,
				"error": self._import_error or disabled_reason,
			}

		assert self._autogen is not None

		trimmed_payload = self._trim_payload_for_role(role=role, payload=payload)
		user_message = (
			"Use the role instructions and return only valid JSON.\n"
			f"Payload:\n{json.dumps(trimmed_payload, ensure_ascii=True)}"
		)

		last_error = "Unknown AutoGen error"
		for model_name in self._candidate_models():
			try:
				assistant = self._autogen.AssistantAgent(
					name=f"{role}_assistant",
					system_message=system_prompt,
					llm_config={
						"config_list": [
							{
								"model": model_name,
								"api_key": self.settings.groq_api_key,
								"base_url": self.settings.groq_base_url,
								"price": [0.0, 0.0],
							}
						],
						"temperature": self.settings.autogen_temperature,
						"max_tokens": self.settings.autogen_max_tokens,
						"timeout": 25,
					},
				)

				raw_reply = assistant.generate_reply(messages=[{"role": "user", "content": user_message}])
				text_reply = self._coerce_reply_text(raw_reply)
				structured = self._extract_json(text_reply)
				return {
					"success": True,
					"role": role,
					"model": model_name,
					"raw": text_reply,
					"structured": structured,
				}
			except Exception as exc:  # noqa: BLE001
				last_error = str(exc)
				continue

		return {
			"success": False,
			"role": role,
			"error": last_error,
		}

	def _candidate_models(self) -> list[str]:
		primary = self.settings.groq_model.strip()
		fallback_raw = self.settings.groq_fallback_models
		fallbacks = [item.strip() for item in fallback_raw.split(",") if item.strip()]
		ordered: list[str] = []
		for model in [primary, *fallbacks]:
			if model and model not in ordered:
				ordered.append(model)
		return ordered

	def _trim_payload_for_role(self, *, role: str, payload: dict[str, Any]) -> dict[str, Any]:
		role_name = role.strip().lower()

		if role_name == "planner":
			ticket = payload.get("ticket", {}) if isinstance(payload.get("ticket"), dict) else {}
			trimmed = {
				"ticket": {
					"ticket_id": ticket.get("ticket_id"),
					"customer_email": ticket.get("customer_email"),
					"subject": ticket.get("subject"),
					"body": ticket.get("body"),
					"source": ticket.get("source"),
					"tier": ticket.get("tier"),
				},
				"deterministic_case_type": payload.get("deterministic_case_type"),
			}
			return self._truncate_payload(trimmed)

		if role_name == "executor":
			plan = payload.get("plan", {}) if isinstance(payload.get("plan"), dict) else {}
			trimmed = {
				"plan": {
					"ticket_id": plan.get("ticket_id"),
					"case_type": plan.get("case_type"),
					"order_id": plan.get("order_id"),
					"required_checks": plan.get("required_checks"),
					"proposed_action": plan.get("proposed_action"),
					"requires_escalation": plan.get("requires_escalation"),
					"escalation_reasons": plan.get("escalation_reasons"),
					"tool_calls": plan.get("tool_calls"),
				},
			}
			return self._truncate_payload(trimmed)

		if role_name == "critic":
			ticket = payload.get("ticket", {}) if isinstance(payload.get("ticket"), dict) else {}
			plan = payload.get("plan", {}) if isinstance(payload.get("plan"), dict) else {}
			execution = payload.get("execution", {}) if isinstance(payload.get("execution"), dict) else {}
			steps = execution.get("steps", []) if isinstance(execution.get("steps"), list) else []

			step_summaries: list[dict[str, Any]] = []
			for step in steps:
				if not isinstance(step, dict):
					continue
				result = step.get("result", {}) if isinstance(step.get("result"), dict) else {}
				step_summaries.append(
					{
						"tool": step.get("tool"),
						"success": step.get("success"),
						"skipped": step.get("skipped"),
						"result": {
							"success": result.get("success"),
							"eligible": result.get("eligible"),
							"reason": result.get("reason"),
							"cancellable": result.get("cancellable"),
							"amount": result.get("amount"),
							"refund_status": result.get("refund_status"),
							"error": result.get("error"),
							"error_type": result.get("error_type"),
						},
					}
				)

			trimmed = {
				"ticket": {
					"ticket_id": ticket.get("ticket_id"),
					"subject": ticket.get("subject"),
					"body": ticket.get("body"),
					"tier": ticket.get("tier"),
				},
				"plan": {
					"case_type": plan.get("case_type"),
					"order_id": plan.get("order_id"),
					"requires_escalation": plan.get("requires_escalation"),
					"escalation_reasons": plan.get("escalation_reasons"),
					"proposed_action": plan.get("proposed_action"),
				},
				"execution": {
					"execution_status": execution.get("execution_status"),
					"tool_failures": execution.get("tool_failures"),
					"steps": step_summaries,
				},
			}
			return self._truncate_payload(trimmed)

		return self._truncate_payload(payload)

	def _truncate_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
		limit = max(600, int(self.settings.autogen_payload_char_limit))
		encoded = json.dumps(payload, ensure_ascii=True)
		if len(encoded) <= limit:
			return payload

		def _trim(value: Any) -> Any:
			if isinstance(value, dict):
				return {key: _trim(item) for key, item in value.items()}
			if isinstance(value, list):
				trimmed_list = [_trim(item) for item in value[:12]]
				return trimmed_list
			if isinstance(value, str) and len(value) > 320:
				return f"{value[:317]}..."
			return value

		trimmed = _trim(payload)
		encoded_trimmed = json.dumps(trimmed, ensure_ascii=True)
		if len(encoded_trimmed) <= limit:
			return trimmed

		return {
			"summary": "Payload truncated for token safety.",
			"keys": list(payload.keys()),
		}

	@staticmethod
	def _coerce_reply_text(reply: Any) -> str:
		if isinstance(reply, str):
			return reply
		if isinstance(reply, dict):
			if isinstance(reply.get("content"), str):
				return reply["content"]
			return json.dumps(reply, ensure_ascii=True)
		return str(reply)

	@staticmethod
	def _extract_json(text: str) -> dict[str, Any]:
		cleaned = text.strip()
		if not cleaned:
			return {}

		try:
			parsed = json.loads(cleaned)
			if isinstance(parsed, dict):
				return parsed
		except json.JSONDecodeError:
			pass

		match = re.search(r"\{[\s\S]*\}", cleaned)
		if not match:
			return {}

		try:
			parsed = json.loads(match.group(0))
			if isinstance(parsed, dict):
				return parsed
		except json.JSONDecodeError:
			return {}

		return {}
