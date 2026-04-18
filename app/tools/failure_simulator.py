from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

FailureMode = Literal["none", "timeout", "malformed", "partial"]


class ToolTimeoutError(Exception):
	pass


class MalformedResponseError(Exception):
	pass


class PartialDataError(Exception):
	pass


class FailureSimulator:
	def simulate_timeout(self, operation_name: str, *, timeout_seconds: float = 2.0) -> None:
		raise ToolTimeoutError(
			f"Simulated timeout for operation '{operation_name}' after {timeout_seconds:.2f}s"
		)

	def simulate_malformed_response(self, operation_name: str) -> str:
		return f"<<MALFORMED_RESPONSE::{operation_name}>>"

	def simulate_partial_data(
		self,
		payload: dict[str, Any],
		*,
		missing_fields: list[str] | None = None,
	) -> dict[str, Any]:
		if not payload:
			raise PartialDataError("Cannot simulate partial data for an empty payload")

		copy_payload = deepcopy(payload)
		fields_to_remove = missing_fields or [next(iter(copy_payload.keys()))]
		for field in fields_to_remove:
			copy_payload.pop(field, None)

		return copy_payload

	def inject_failure(
		self,
		*,
		mode: FailureMode,
		operation_name: str,
		payload: dict[str, Any] | None = None,
		missing_fields: list[str] | None = None,
	) -> dict[str, Any] | str:
		if mode == "none":
			return payload or {}
		if mode == "timeout":
			self.simulate_timeout(operation_name)
		if mode == "malformed":
			return self.simulate_malformed_response(operation_name)
		if mode == "partial":
			return self.simulate_partial_data(payload or {}, missing_fields=missing_fields)

		raise ValueError(f"Unsupported failure mode: {mode}")

