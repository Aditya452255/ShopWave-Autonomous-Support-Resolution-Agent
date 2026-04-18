from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _utc_now_iso() -> str:
	return datetime.now(tz=UTC).isoformat()


@dataclass(slots=True)
class TicketMemory:
	ticket_id: str
	correlation_id: str
	created_at: str = field(default_factory=_utc_now_iso)
	updated_at: str = field(default_factory=_utc_now_iso)
	stage_data: dict[str, Any] = field(default_factory=dict)
	events: list[dict[str, Any]] = field(default_factory=list)

	def set_stage(self, stage: str, payload: Any) -> None:
		self.stage_data[stage] = payload
		self.updated_at = _utc_now_iso()

	def add_event(self, event_type: str, details: dict[str, Any] | None = None) -> None:
		event = {
			"timestamp": _utc_now_iso(),
			"event_type": event_type,
			"details": details or {},
		}
		self.events.append(event)
		self.updated_at = event["timestamp"]

	def to_dict(self) -> dict[str, Any]:
		return {
			"ticket_id": self.ticket_id,
			"correlation_id": self.correlation_id,
			"created_at": self.created_at,
			"updated_at": self.updated_at,
			"stage_data": self.stage_data,
			"events": self.events,
		}


class MemoryStore:
	def __init__(self) -> None:
		self._items: dict[str, TicketMemory] = {}

	def start_ticket(self, ticket_id: str, correlation_id: str) -> TicketMemory:
		memory = TicketMemory(ticket_id=ticket_id, correlation_id=correlation_id)
		self._items[ticket_id] = memory
		return memory

	def get(self, ticket_id: str) -> TicketMemory | None:
		return self._items.get(ticket_id)

	def remove(self, ticket_id: str) -> None:
		self._items.pop(ticket_id, None)

	def snapshot(self, ticket_id: str) -> dict[str, Any] | None:
		item = self.get(ticket_id)
		return item.to_dict() if item else None

