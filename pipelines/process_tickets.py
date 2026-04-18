from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any

from app.core.orchestrator import TicketOrchestrator
from app.schemas.ticket import Ticket
from app.services.data_loader import DataLoader
from config.settings import AppSettings, settings


async def process_tickets_concurrently(
	tickets: list[Ticket | dict[str, Any]],
	*,
	orchestrator: TicketOrchestrator | None = None,
) -> dict[str, Any]:
	active_orchestrator = orchestrator or TicketOrchestrator()
	results: list[dict[str, Any]] = []
	for ticket in tickets:
		results.append(await active_orchestrator.process_ticket(ticket))

	decision_counter = Counter(result.get("final_decision", "unknown") for result in results)
	return {
		"summary": {
			"total_tickets": len(results),
			"resolved": decision_counter.get("approve", 0),
			"escalated": decision_counter.get("escalate", 0),
			"retry": decision_counter.get("retry", 0),
			"unknown": decision_counter.get("unknown", 0),
			"concurrency_limit": 1,
			"backend": active_orchestrator.settings.orchestration_mode,
		},
		"results": results,
	}


async def run_pipeline(
	*,
	limit: int | None = None,
	reset_audit: bool = False,
	app_settings: AppSettings | None = None,
	tickets_override: list[Ticket | dict[str, Any]] | None = None,
) -> dict[str, Any]:
	active_settings = app_settings or settings

	if tickets_override is not None:
		ticket_payloads = [
			item.model_dump(mode="json") if isinstance(item, Ticket) else item
			for item in tickets_override
		]
		if limit is not None and limit > 0:
			ticket_payloads = ticket_payloads[:limit]
	else:
		data_loader = DataLoader(active_settings)
		tickets = data_loader.load_tickets()
		if limit is not None and limit > 0:
			tickets = tickets[:limit]
		ticket_payloads = [ticket.model_dump(mode="json") for ticket in tickets]

	orchestrator = TicketOrchestrator(app_settings=active_settings)
	if reset_audit:
		orchestrator.audit_logger.clear_records()

	return await process_tickets_concurrently(
		ticket_payloads,
		orchestrator=orchestrator,
	)


def run_pipeline_sync(
	*,
	limit: int | None = None,
	reset_audit: bool = False,
	app_settings: AppSettings | None = None,
	tickets_override: list[Ticket | dict[str, Any]] | None = None,
) -> dict[str, Any]:
	return asyncio.run(
		run_pipeline(
			limit=limit,
			reset_audit=reset_audit,
			app_settings=app_settings,
			tickets_override=tickets_override,
		)
	)

