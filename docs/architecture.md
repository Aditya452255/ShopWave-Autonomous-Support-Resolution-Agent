# Architecture

## 1. System Intent

ShopWave is designed as a safe-by-default decision engine for support tickets.
It combines deterministic policy enforcement with optional LLM assistance.

Core principles:

1. Deterministic policy is authoritative.
2. LLM output is advisory, never final authority.
3. Uncertainty trends toward safe escalation.
4. Every ticket produces explainable evidence and audit traces.

## 2. Layered Design

### Entry Layer

- `main.py`: command-line processing.
- `run_demo.py`: demo-oriented runner.
- `ui_app.py`: Gradio dashboard.

### Pipeline Layer

- `pipelines/process_tickets.py` orchestrates batch execution.
- Current implementation processes tickets sequentially.
- Summary payload includes total/resolved/escalated/retry/unknown and backend mode.

### Orchestration Layer

- `app/core/orchestrator.py` (`TicketOrchestrator`) is the central coordinator.
- Lifecycle per ticket:
	- Planner
	- Executor
	- Critic
	- Confidence service
	- Final decision explanation
- Writes full decision audit records via `AuditLogger`.

### Agent Layer

- `app/agents/planner.py`
	- case classification,
	- tool-call planning,
	- escalation intent hints.
- `app/agents/executor.py`
	- tool execution,
	- step-by-step outcome capture,
	- guard-block logic.
- `app/agents/critic.py`
	- policy compliance checks,
	- mandatory escalation reasoning,
	- confidence and execution-risk synthesis.

### Tool Layer

- `app/tools/tool_registry.py`: dispatch entrypoint.
- Domain tools:
	- customer/order/product lookup,
	- refund/cancellation eligibility and action tools,
	- knowledge base search,
	- communication helpers.

### Service Layer

- `app/services/autogen_client.py`: role-aware AutoGen integration.
- `app/services/confidence.py`: confidence and escalation recommendation.
- `app/services/retry_handler.py`: bounded retry wrapper.
- `app/services/data_loader.py`: dataset loading and validation.
- `app/services/audit_logger.py`: append/read/clear audit records.
- `app/services/ui_data_adapter.py`: UI upload-to-temp-workspace adapter.

### Data Layer

- Inputs: `data/customers.json`, `data/orders.json`, `data/products.json`, `data/tickets.json`.
- Policy KB: `data/knowledge_base/policies.txt`.
- Output: `artifacts/audit_log.json` (or temp workspace equivalent in UI mode).

## 3. Runtime Modes

### Deterministic Mode

- All decisions are deterministic.
- Fastest path.
- Recommended baseline for tests and demos.

### AutoGen Mode

- Deterministic logic remains primary.
- LLM assistance is role-gated by `AUTOGEN_ROLES`.
- Current default: planner role enabled only.
- Executor/critic remain deterministic unless explicitly enabled.

## 4. End-to-End Flow

Per ticket:

1. Ticket normalized and correlation id assigned.
2. Planner creates case-specific tool plan.
3. Executor runs planned tools with guard conditions.
4. Critic evaluates policy compliance and escalation necessity.
5. Confidence service adds threshold-based risk signal.
6. Orchestrator generates final decision payload:
	 - short reason,
	 - detailed reason,
	 - reason codes,
	 - evidence list,
	 - policy/system status.
7. Audit log record is written.

## 5. Decision Policy Mechanics

Mandatory escalation categories include:

- warranty manual review,
- refund amount above threshold,
- damaged-item replacement handoff,
- fraud/legal risk,
- premium borderline supervisor review,
- ambiguous order linkage,
- wrong-item decision handoff,
- exchange fulfillment handoff,
- confidence-triggered risk escalation.

Policy-blocked but non-escalation outcomes are supported for cases such as:

- return window expired,
- cancellation not allowed for current order status,
- photo evidence required for damaged-item refund flow.

## 6. UI Architecture Notes

- Dashboard is dark-only.
- Backend selector supports `autogen` and `deterministic` modes.
- Summary metrics are card-based (not raw JSON).
- Technical metadata is tucked in accordion form.
- Detailed per-ticket investigation remains in tabbed panel:
	- Overview,
	- Agent Trace,
	- Audit,
	- Escalation.

## 7. Safety and Reliability Guarantees

1. Refund issuance requires eligibility checks.
2. Policy-denied actions do not bypass deterministic guards.
3. Missing critical evidence can force escalation or retry.
4. Runtime exceptions degrade to explicit safe escalation payloads.
5. Audit evidence is retained for post-run explainability.

## 8. Configuration Control Points

Key settings in `config/settings.py`:

- `orchestration_mode`
- `enable_autogen`
- `autogen_roles`
- `confidence_escalation_threshold`
- `groq_model`, `groq_fallback_models`, `groq_base_url`
- `autogen_max_tokens`, `autogen_payload_char_limit`
- `persist_tool_mutations`

## 9. Related Docs

- `docs/project_guide.md`: full project documentation.
- `docs/failure_modes.md`: failure and recovery runbooks.

