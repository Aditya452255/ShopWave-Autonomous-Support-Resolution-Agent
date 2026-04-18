from __future__ import annotations

from html import escape
import json
import os
from typing import Any

import gradio as gr

from app.services.audit_logger import AuditLogger
from app.services.ui_data_adapter import UIDataAdapter
from config.settings import AppSettings, settings
from pipelines.process_tickets import run_pipeline_sync


UI_CSS = """
:root {
	--bg: #080d18;
	--panel: #121a2b;
	--panel-muted: #0f1626;
	--text: #ecf2ff;
	--text-muted: #a8b6d8;
	--border: #25304a;
	--brand: #4f9bff;
	--success: #2fc27a;
	--warning: #f6ad55;
	--danger: #f87171;
	--neutral: #7eb7ff;
	--shadow: 0 14px 35px rgba(0, 0, 0, 0.35);
}

.gradio-container,
body {
	background: var(--bg) !important;
	color: var(--text) !important;
	font-family: "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif !important;
}

#app-shell {
	max-width: 1240px;
	margin: 0 auto;
	padding: 8px 10px 22px;
}

#hero-card {
	background: linear-gradient(135deg, var(--panel) 0%, var(--panel-muted) 100%);
	border: 1px solid var(--border);
	border-radius: 16px;
	padding: 18px 20px 14px;
	box-shadow: var(--shadow);
}

#hero-subtitle {
	color: var(--text-muted);
	margin-top: -6px;
}

#control-panel,
#policy-card,
#results-card,
#ticket-detail-panel,
#metrics-shell {
	background: var(--panel);
	border: 1px solid var(--border);
	border-radius: 16px;
	padding: 14px;
	box-shadow: var(--shadow);
}

#control-panel {
	margin-top: 12px;
}

#controls-help {
	color: var(--text-muted);
	margin-top: -4px;
}

#run-analysis-btn {
	min-height: 44px;
	font-weight: 700;
	letter-spacing: 0.2px;
	border-radius: 12px;
}

#decision-legend {
	display: flex;
	flex-wrap: wrap;
	gap: 8px;
	margin: 8px 0 4px;
}

.legend-badge {
	padding: 6px 10px;
	border-radius: 999px;
	font-size: 0.8rem;
	font-weight: 700;
	border: 1px solid var(--border);
	background: var(--panel-muted);
	color: var(--text-muted);
}

.legend-badge.approved {
	border-color: color-mix(in srgb, var(--success) 40%, var(--border));
	color: var(--success);
}

.legend-badge.escalated {
	border-color: color-mix(in srgb, var(--warning) 40%, var(--border));
	color: var(--warning);
}

.legend-badge.failed {
	border-color: color-mix(in srgb, var(--danger) 40%, var(--border));
	color: var(--danger);
}

#metrics-shell {
	margin-top: 12px;
	padding-top: 16px;
}

#metrics-grid {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
	gap: 10px;
}

.metric-card {
	background: var(--panel-muted);
	border: 1px solid var(--border);
	border-radius: 14px;
	padding: 12px;
	min-height: 84px;
	display: flex;
	flex-direction: column;
	justify-content: center;
	gap: 4px;
}

.metric-title {
	font-size: 0.78rem;
	font-weight: 700;
	color: var(--text-muted);
	text-transform: uppercase;
	letter-spacing: 0.4px;
}

.metric-value {
	font-size: 1.55rem;
	font-weight: 800;
	color: var(--text);
	line-height: 1.1;
}

.metric-note {
	font-size: 0.76rem;
	color: var(--text-muted);
}

.metric-card.approved {
	border-left: 4px solid var(--success);
}

.metric-card.escalated {
	border-left: 4px solid var(--warning);
}

.metric-card.failed {
	border-left: 4px solid var(--danger);
}

.metric-card.neutral,
.metric-card.backend,
.metric-card.audit {
	border-left: 4px solid var(--neutral);
}

#run-meta-accordion {
	margin-top: 10px;
}

#policy-card {
	margin-top: 12px;
}

#policy-card ul {
	margin-top: 6px;
	padding-left: 18px;
}

#policy-card li {
	margin-bottom: 6px;
	line-height: 1.45;
}

#results-card {
	margin-top: 12px;
}

#results-table {
	border: 1px solid var(--border);
	border-radius: 12px;
	overflow: hidden;
	background: var(--panel-muted);
}

#results-table table {
	font-size: 0.9rem;
}

#results-table table thead th {
	position: sticky;
	top: 0;
	z-index: 3;
	background: var(--panel) !important;
	color: var(--text) !important;
	border-bottom: 1px solid var(--border) !important;
}

#results-table table tbody tr:nth-child(even) {
	background: color-mix(in srgb, var(--panel-muted) 88%, var(--panel));
}

#ticket-detail-panel {
	margin-top: 12px;
	max-height: 700px;
	overflow-y: auto;
	padding: 12px;
}

#overview-scroll,
#handoff-scroll {
	max-height: 280px;
	overflow-y: auto;
}

#agent-trace-scroll {
	max-height: 430px;
	overflow-y: auto;
	padding-right: 6px;
}

#audit-log-view textarea,
#audit-log-view pre {
	max-height: 430px !important;
	min-height: 430px !important;
	overflow-y: auto !important;
}

#ticket-detail-panel button {
	border-radius: 10px !important;
}

.gradio-container input:not([type="radio"]):not([type="checkbox"]),
.gradio-container select,
.gradio-container textarea {
	background: var(--panel-muted) !important;
	color: var(--text) !important;
	border: 1px solid var(--border) !important;
}

#backend-select input[type="radio"] {
	accent-color: var(--brand);
	cursor: pointer;
}

#backend-select label,
#backend-select .wrap,
#backend-select [role="radio"] {
	cursor: pointer !important;
}

.gradio-container .tabs {
	border: 1px solid var(--border);
	border-radius: 12px;
	padding: 4px;
	background: var(--panel-muted);
}

@media (max-width: 900px) {
	#app-shell {
		padding: 6px;
	}

	#hero-card,
	#control-panel,
	#policy-card,
	#results-card,
	#ticket-detail-panel,
	#metrics-shell {
		padding: 12px;
	}
}
"""

DECISION_POLICY_MARKDOWN = """
- Refunds require eligibility checks before approval.
- Refunds above policy limits are escalated for manual review.
- Warranty-related requests are escalated to human specialists.
- Missing or ambiguous customer/order linkage escalates safely.
- Confidence below threshold escalates for human validation.
- Fraud or legal-risk signals always escalate.
- FAQ and policy lookup responses can be auto-approved when policy match is strong.
- Deterministic policy checks override weak LLM guesses.
- Tool failures or partial execution can trigger safe escalation.
"""


def render_metric_cards(summary: dict[str, Any]) -> str:
	total = int(summary.get("total_tickets", 0) or 0)
	resolved = int(summary.get("resolved", 0) or 0)
	escalated = int(summary.get("escalated", 0) or 0)
	failed_safe = int(summary.get("failed_safe", 0) or 0)
	backend = str(summary.get("backend", "n/a") or "n/a").upper()
	audit_log = str(summary.get("audit_log", "")).strip()
	audit_status = "Available" if audit_log else "Unavailable"

	def _card(title: str, value: str, tone: str, note: str = "") -> str:
		note_html = f"<div class='metric-note'>{escape(note)}</div>" if note else ""
		return (
			f"<div class='metric-card {escape(tone)}'>"
			f"<div class='metric-title'>{escape(title)}</div>"
			f"<div class='metric-value'>{escape(value)}</div>"
			f"{note_html}"
			"</div>"
		)

	cards = [
		_card("Total Tickets", str(total), "neutral", "Batch size analyzed"),
		_card("Approved / Resolved", str(resolved), "approved", "Auto-resolved within policy"),
		_card("Escalated", str(escalated), "escalated", "Handed to human review"),
		_card("Failed Safe", str(failed_safe), "failed", "Safety fallback escalations"),
		_card("Backend Type", backend, "backend", "Active orchestration mode"),
		_card("Audit Log Status", audit_status, "audit", "Technical trace captured"),
	]

	return "<div id='metrics-grid'>" + "".join(cards) + "</div>"


def render_run_metadata(summary: dict[str, Any]) -> str:
	workspace = str(summary.get("workspace", "")).strip() or "N/A"
	audit_log = str(summary.get("audit_log", "")).strip() or "N/A"
	backend = str(summary.get("backend", "n/a") or "n/a")

	return "\n".join(
		[
			"### Run Metadata",
			f"- Backend: {backend}",
			f"- Workspace: {workspace}",
			f"- Audit log path: {audit_log}",
		]
	)


def render_rules_panel() -> str:
	return DECISION_POLICY_MARKDOWN


def _to_json_text(value: Any) -> str:
	return json.dumps(value, indent=2, default=str)


def _build_table_rows(results: list[dict[str, Any]]) -> list[list[str]]:
	rows: list[list[str]] = []
	for item in results:
		ticket_id = str(item.get("ticket_id", ""))
		case_type = str(item.get("case_type", ""))
		decision = str(item.get("final_decision", ""))
		confidence = item.get("confidence", {}).get("score", "") if isinstance(item.get("confidence"), dict) else ""
		short_reason = str(item.get("short_reason", "")).strip()
		detailed_reason = str(item.get("detailed_reason", "")).strip()

		if not short_reason:
			reasons = item.get("escalation_reasons", [])
			if isinstance(reasons, list) and reasons:
				short_reason = f"Escalated: {str(reasons[0]).replace('_', ' ')}"
			elif decision == "approve":
				short_reason = "Approved: policy checks passed"
			else:
				short_reason = "Reason unavailable"

		if not detailed_reason:
			detailed_reason = str(item.get("final_reason_summary", "")).strip() or short_reason

		rows.append([ticket_id, case_type, decision, str(confidence), short_reason, detailed_reason])
	return rows


def _build_detail_map(
	results: list[dict[str, Any]],
	audit_records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
	audit_by_ticket: dict[str, dict[str, Any]] = {}
	for record in audit_records:
		ticket_id = str(record.get("ticket_id", "")).strip()
		if ticket_id:
			audit_by_ticket[ticket_id] = record

	detail_map: dict[str, dict[str, Any]] = {}
	for result in results:
		ticket_id = str(result.get("ticket_id", "")).strip()
		if not ticket_id:
			continue
		detail_map[ticket_id] = {
			"planner": result.get("plan", {}),
			"executor": result.get("execution", {}),
			"critic": result.get("review", {}),
			"audit": audit_by_ticket.get(ticket_id, {}),
			"decision": {
				"final_reason_summary": result.get("final_reason_summary", ""),
				"short_reason": result.get("short_reason", ""),
				"detailed_reason": result.get("detailed_reason", ""),
				"approval_reason_text": result.get("approval_reason_text", ""),
				"escalation_reason_text": result.get("escalation_reason_text", ""),
				"primary_reason": result.get("primary_reason", ""),
				"contributing_reasons": result.get("contributing_reasons", []),
			},
			"escalation_summary": {
				"final_decision": result.get("final_decision"),
				"escalation_reasons": result.get("escalation_reasons", []),
				"escalation_reason_codes": result.get("escalation_reason_codes", []),
				"escalation_reason_text": result.get("escalation_reason_text", ""),
				"escalation_summary": result.get("escalation_summary", ""),
				"short_reason": result.get("short_reason", ""),
				"detailed_reason": result.get("detailed_reason", ""),
				"final_reason_summary": result.get("final_reason_summary", ""),
				"confidence": result.get("confidence", {}),
			},
		}
	return detail_map


def _extract_customer_identity(executor_payload: dict[str, Any]) -> str:
	steps = executor_payload.get("steps", [])
	if not isinstance(steps, list):
		return "Unknown"

	for step in steps:
		if not isinstance(step, dict) or step.get("tool") != "get_customer":
			continue
		result = step.get("result", {})
		if not isinstance(result, dict):
			continue
		customer = result.get("customer", {})
		if not isinstance(customer, dict):
			continue

		name = str(customer.get("name", "Unknown")).strip() or "Unknown"
		email = str(customer.get("email", "unknown")).strip() or "unknown"
		tier = str(customer.get("tier", "unknown")).strip() or "unknown"
		return f"{name} ({email}) - {tier}"

	return "Unknown"


def format_ticket_overview(ticket_id: str, details: dict[str, Any]) -> str:
	planner = details.get("planner", {}) if isinstance(details.get("planner"), dict) else {}
	executor = details.get("executor", {}) if isinstance(details.get("executor"), dict) else {}
	escalation = details.get("escalation_summary", {}) if isinstance(details.get("escalation_summary"), dict) else {}
	decision_detail = details.get("decision", {}) if isinstance(details.get("decision"), dict) else {}

	case_type = planner.get("case_type", "unknown")
	decision = escalation.get("final_decision", "unknown")
	summary = (
		str(decision_detail.get("final_reason_summary", "")).strip()
		or str(planner.get("summary", "")).strip()
		or "No summary available."
	)
	customer = _extract_customer_identity(executor)

	confidence_payload = escalation.get("confidence", {})
	confidence_score = (
		confidence_payload.get("score", "n/a")
		if isinstance(confidence_payload, dict)
		else "n/a"
	)

	return (
		"### Overview\n"
		f"- **ticket_id:** {ticket_id}\n"
		f"- **customer:** {customer}\n"
		f"- **category:** {case_type}\n"
		f"- **final decision:** {decision}\n"
		f"- **confidence:** {confidence_score}\n\n"
		"**short summary**\n"
		f"{summary}"
	)


def format_agent_trace(details: dict[str, Any]) -> str:
	planner = details.get("planner", {}) if isinstance(details.get("planner"), dict) else {}
	executor = details.get("executor", {}) if isinstance(details.get("executor"), dict) else {}
	critic = details.get("critic", {}) if isinstance(details.get("critic"), dict) else {}

	return "\n\n".join(
		[
			"### Ticket Understanding\n```json\n" + _to_json_text(planner) + "\n```",
			"### Actions Taken\n```json\n" + _to_json_text(executor) + "\n```",
			"### Safety Review\n```json\n" + _to_json_text(critic) + "\n```",
		]
	)


def format_audit_view(details: dict[str, Any]) -> str:
	audit = details.get("audit", {}) if isinstance(details.get("audit"), dict) else {}
	return _to_json_text(audit)


def format_escalation_view(details: dict[str, Any]) -> str:
	escalation = details.get("escalation_summary", {}) if isinstance(details.get("escalation_summary"), dict) else {}
	decision_detail = details.get("decision", {}) if isinstance(details.get("decision"), dict) else {}
	decision = str(escalation.get("final_decision", "")).strip().lower()
	reasons = escalation.get("escalation_reason_codes", [])
	escalation_text = str(escalation.get("escalation_reason_text", "")).strip()
	primary_reason = str(decision_detail.get("primary_reason", "")).strip()
	contributing = decision_detail.get("contributing_reasons", [])

	if decision != "escalate" and not reasons:
		return "### Human Handoff\nNo escalation required."

	payload = {
		"primary_reason": primary_reason,
		"contributing_reasons": contributing,
		"escalation_reason_codes": reasons,
		"escalation_reason_text": escalation_text,
		"summary": escalation.get("escalation_summary", escalation.get("final_reason_summary", "")),
		"confidence": escalation.get("confidence", {}),
	}

	return "### Human Handoff\n```json\n" + _to_json_text(payload) + "\n```"


def run_ticket_analysis(
	customers_file: str | None,
	orders_file: str | None,
	products_file: str | None,
	tickets_file: str | None,
	ticket_limit: int,
	backend: str = "autogen",
):
	base_settings = AppSettings(**{**settings.model_dump(), "orchestration_mode": backend})
	adapter = UIDataAdapter(base_settings)
	prepared_settings, metadata = adapter.prepare_settings(
		customers_path=customers_file,
		orders_path=orders_file,
		products_path=products_file,
		tickets_path=tickets_file,
		policies_path=None,
	)

	result = run_pipeline_sync(
		limit=ticket_limit,
		reset_audit=True,
		app_settings=prepared_settings,
	)

	results = result.get("results", [])
	audit_logger = AuditLogger(prepared_settings)
	audit_records = audit_logger.read_records()
	detail_map = _build_detail_map(results, audit_records)
	table_rows = _build_table_rows(results)
	ticket_ids = list(detail_map.keys())

	failed_safe = sum(
		1
		for item in results
		if str(item.get("final_decision")) == "escalate"
		and (
			bool(item.get("error"))
			or bool(item.get("review", {}).get("violations", []))
			or bool(item.get("confidence", {}).get("escalation_recommended"))
		)
	)

	summary = {
		"total_tickets": result.get("summary", {}).get("total_tickets", 0),
		"resolved": result.get("summary", {}).get("resolved", 0),
		"escalated": result.get("summary", {}).get("escalated", 0),
		"failed_safe": failed_safe,
		"backend": backend,
		"workspace": metadata.get("workspace_root", ""),
		"audit_log": str(prepared_settings.audit_log_file),
	}

	dropdown_update = gr.update(choices=ticket_ids, value=ticket_ids[0] if ticket_ids else None)
	return (
		render_metric_cards(summary),
		render_run_metadata(summary),
		table_rows,
		dropdown_update,
		_to_json_text(detail_map),
	)


def render_ticket_details(ticket_id: str, detail_map_json: str):
	try:
		detail_map = json.loads(detail_map_json or "{}")
	except json.JSONDecodeError:
		detail_map = {}

	if not isinstance(detail_map, dict) or not ticket_id or ticket_id not in detail_map:
		empty_msg = "Select a ticket to view details."
		return empty_msg, empty_msg, _to_json_text({}), "No escalation required."

	details = detail_map[ticket_id]
	if not isinstance(details, dict):
		empty_msg = "Ticket details are unavailable."
		return empty_msg, empty_msg, _to_json_text({}), "No escalation required."

	return (
		format_ticket_overview(ticket_id, details),
		format_agent_trace(details),
		format_audit_view(details),
		format_escalation_view(details),
	)


def build_ui() -> gr.Blocks:
	with gr.Blocks(title="ShopWave Autonomous Support Resolution - Gradio UI", css=UI_CSS) as demo:
		with gr.Column(elem_id="app-shell"):
			with gr.Row():
				with gr.Column(scale=12, elem_id="hero-card"):
					gr.Markdown("# ShopWave Autonomous Support Resolution Agent")
					gr.Markdown(
						"A policy-first AI operations dashboard for support ticket resolution and safe escalation.",
						elem_id="hero-subtitle",
					)

			with gr.Group(elem_id="control-panel"):
				gr.Markdown("### Control Panel")
				gr.Markdown(
					"Upload your datasets, choose backend behavior, and run analysis batches for live demos.",
					elem_id="controls-help",
				)

				with gr.Row():
					customers_file = gr.File(label="customers.json", type="filepath")
					orders_file = gr.File(label="orders.json", type="filepath")
					products_file = gr.File(label="products.json", type="filepath")
					tickets_file = gr.File(label="tickets.json", type="filepath")

				with gr.Row():
					ticket_limit = gr.Slider(label="Ticket Limit", minimum=1, maximum=50, value=5, step=1)
					backend = gr.Radio(
						label="Backend",
						choices=["autogen", "deterministic"],
						value="autogen",
						interactive=True,
						elem_id="backend-select",
					)
					run_button = gr.Button("Run Ticket Analysis", variant="primary", elem_id="run-analysis-btn")

			gr.HTML(
				"""
				<div id='decision-legend'>
				  <span class='legend-badge approved'>Approved / Resolved</span>
				  <span class='legend-badge escalated'>Escalated</span>
				  <span class='legend-badge failed'>Failed Safe</span>
				  <span class='legend-badge'>Total / Backend</span>
				</div>
				"""
			)

			with gr.Group(elem_id="metrics-shell"):
				gr.Markdown("### Summary Metrics")
				summary_cards = gr.HTML(render_metric_cards({}))

				with gr.Accordion("Technical Run Metadata", open=False, elem_id="run-meta-accordion"):
					summary_meta = gr.Markdown("Run analysis to view technical metadata and audit path.")

			with gr.Group(elem_id="policy-card"):
				gr.Markdown("### Decision Policy")
				gr.Markdown(render_rules_panel())

			with gr.Group(elem_id="results-card"):
				gr.Markdown("### Ticket Results")
				table = gr.Dataframe(
					label="Ticket Results Table",
					headers=["ticket_id", "case_type", "decision", "confidence", "short_reason", "detailed_reason"],
					datatype=["str", "str", "str", "str", "str", "str"],
					elem_id="results-table",
				)

			ticket_selector = gr.Dropdown(label="Select Ticket", choices=[], value=None)
			detail_state = gr.State("{}")

			gr.Markdown("## Selected Ticket Investigation Panel")
			with gr.Group(elem_id="ticket-detail-panel"):
				with gr.Tabs():
					with gr.Tab("Overview"):
						with gr.Group(elem_id="overview-scroll"):
							overview_markdown = gr.Markdown("Select a ticket to view details.")

					with gr.Tab("Agent Trace"):
						with gr.Group(elem_id="agent-trace-scroll"):
							agent_trace_markdown = gr.Markdown("Select a ticket to inspect Ticket Understanding, Actions Taken, and Safety Review.")

					with gr.Tab("Audit"):
						audit_code = gr.Code(
							label="Audit Log",
							language="json",
							value=_to_json_text({}),
							elem_id="audit-log-view",
						)

					with gr.Tab("Escalation"):
						with gr.Group(elem_id="handoff-scroll"):
							escalation_markdown = gr.Markdown("No escalation required.")

		run_button.click(
			fn=run_ticket_analysis,
			inputs=[
				customers_file,
				orders_file,
				products_file,
				tickets_file,
				ticket_limit,
				backend,
			],
			outputs=[summary_cards, summary_meta, table, ticket_selector, detail_state],
		)

		ticket_selector.change(
			fn=render_ticket_details,
			inputs=[ticket_selector, detail_state],
			outputs=[overview_markdown, agent_trace_markdown, audit_code, escalation_markdown],
		)

	return demo


def launch_ui() -> None:
	demo = build_ui()
	port = int(os.getenv("PORT", "7860"))
	running_behind_platform_proxy = "PORT" in os.environ
	server_name = "0.0.0.0" if running_behind_platform_proxy else "127.0.0.1"
	root_path = os.getenv("GRADIO_ROOT_PATH")
	launch_kwargs = {
		"show_error": True,
		"inbrowser": False,
		"server_port": port,
	}
	if root_path:
		launch_kwargs["root_path"] = root_path

	try:
		demo.launch(server_name=server_name, **launch_kwargs)
	except ValueError as exc:
		message = str(exc)
		if "localhost is not accessible" not in message:
			raise

		print("Localhost is not accessible; retrying with server_name=0.0.0.0")
		demo.launch(server_name="0.0.0.0", **launch_kwargs)


if __name__ == "__main__":
	launch_ui()
