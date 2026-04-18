# Project Guide

This document is a complete technical guide for the ShopWave Autonomous Support Resolution Agent.
It is intended for judges, maintainers, and contributors who want a single source of truth.

## 1. Project Purpose

ShopWave automates first-line support decisions while keeping policy safety as the top priority.

Goals:

1. resolve routine tickets automatically,
2. escalate risk-sensitive tickets safely,
3. explain every outcome with evidence and reason codes,
4. keep LLM usage optional and constrained.

## 2. Key Capabilities

- Multi-case ticket handling: refund, cancellation, exchange, wrong item, damaged item, warranty, FAQ.
- Deterministic policy gating for financial and risk-sensitive actions.
- Optional role-based AutoGen assistance with Groq.
- Full per-ticket trace and decision audit output.
- Gradio dashboard for upload, run, inspect, and explain.

## 3. End-to-End Workflow

For each ticket, the system runs:

1. Planner
2. Executor
3. Critic
4. Confidence service
5. Orchestrator decision explanation
6. Audit append

### 3.1 Planner responsibilities

- classify case type,
- construct ordered tool call plan,
- include case-specific required checks,
- mark policy-driven escalation intent where needed.

### 3.2 Executor responsibilities

- execute tools in planned order,
- capture step-by-step success/failure payloads,
- enforce guard conditions:
  - no refund issue before eligibility pass,
  - no cancellation before cancellation eligibility pass,
- return execution status (`completed`, `partial`, `failed`).

### 3.3 Critic responsibilities

- validate policy compliance and evidence completeness,
- evaluate mandatory escalation reasons,
- integrate deterministic and optional LLM reason hints,
- produce final stage recommendation (`approve`, `retry`, `escalate`).

### 3.4 Confidence service responsibilities

- compute confidence score and threshold comparisons,
- provide independent escalation recommendation signal.

### 3.5 Orchestrator responsibilities

- synthesize final decision payload,
- generate short and detailed reasons,
- attach policy/system status and evidence,
- persist audit record.

## 4. Decision Outputs

Each ticket result contains:

- `decision` / `final_decision`
- `short_reason`
- `detailed_reason`
- `final_reason_summary`
- `primary_reason`
- `contributing_reasons`
- `escalation_reason_codes` (when escalated)
- `approval_reason_code` and text (when approved)
- `evidence_used`
- `policy_status`
- `system_status`

This structure supports explainability and judge-facing demos.

## 5. Policy and Escalation Logic

### 5.1 Mandatory escalation examples

- warranty claims requiring manual review,
- refunds above threshold,
- damaged item replacement handoff,
- exchange or wrong-item fulfillment decisions,
- fraud/legal risk signals,
- ambiguous order/customer linkage,
- premium borderline supervisor-required cases,
- low confidence safety trigger.

### 5.2 Policy denials that can remain non-escalation

- return window expired,
- cancellation stage not allowed,
- missing photo evidence for damaged-item refund.

In these cases the system can return a policy-safe approval/denial-style resolution with clear reason text.

## 6. AutoGen Integration

AutoGen is optional and role-gated.

- Provider path: OpenAI-compatible Groq endpoint.
- Default mode: `ORCHESTRATION_MODE=autogen`.
- Default roles: `AUTOGEN_ROLES=planner`.
- If provider/model fails, deterministic logic still continues.

### 6.1 Why role-gating matters

Role-gating reduces latency and API usage while preserving deterministic safety.
Planner-only mode provides useful classification hints with minimal overhead.

## 7. Runtime Execution Model

Current processing model is sequential across tickets.

Benefits:

- more predictable runtime behavior,
- lower provider burst pressure,
- easier traceability during demos.

## 8. Data and Artifacts

### 8.1 Inputs

- `data/customers.json`
- `data/orders.json`
- `data/products.json`
- `data/tickets.json`
- `data/knowledge_base/policies.txt`

### 8.2 Outputs

- `artifacts/audit_log.json`

When running via UI, files may be copied into a temporary workspace for isolated execution.

## 9. Configuration Reference

Primary settings are in `config/settings.py` and environment variables.

Important toggles:

- `ORCHESTRATION_MODE`
- `ENABLE_AUTOGEN`
- `AUTOGEN_ROLES`
- `CONFIDENCE_ESCALATION_THRESHOLD`
- `GROQ_MODEL`
- `GROQ_FALLBACK_MODELS`
- `AUTOGEN_MAX_TOKENS`
- `AUTOGEN_PAYLOAD_CHAR_LIMIT`
- `PERSIST_TOOL_MUTATIONS`

## 10. User Interfaces

### 10.1 CLI

Use `main.py` for full runs and `run_demo.py` for quick demo presets.

### 10.2 Gradio UI

The UI includes:

- control panel (data upload, limit, backend),
- summary metric cards,
- decision policy panel,
- results table,
- selected ticket deep-dive tabs.

The current UI is dark-only.

## 11. Error Handling and Safety

- retry wrapper around stage functions,
- explicit safe escalation fallback on orchestrator exceptions,
- policy guards preventing unauthorized refund/cancel actions,
- detailed audit logging even on failures.

## 12. Performance Notes

- deterministic mode is fastest,
- autogen mode performance depends on provider latency,
- planner-only autogen is the recommended default for demos.

## 13. How to Run

### 13.1 Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 13.2 Configure

Create `.env` with Groq and runtime settings.

### 13.3 Run CLI

```powershell
python main.py --limit 5 --backend deterministic --reset-audit
```

### 13.4 Run UI

```powershell
python ui_app.py
```

## 14. Recommended Demo Flow

1. start in deterministic mode with limit 1,
2. show clear reason outputs and audit trace,
3. switch to autogen mode (planner role) and compare,
4. highlight policy panel and escalation rationale,
5. inspect one escalated and one approved ticket in detail.

## 15. Repository Map

- `app/agents`: planner/executor/critic logic
- `app/core`: orchestration and memory
- `app/services`: autogen, confidence, retries, audit, data adapters
- `app/tools`: operational tools and registry
- `app/schemas`: pydantic models
- `pipelines`: ticket batch processing
- `config`: settings and prompts
- `data`: source datasets and policy KB
- `artifacts`: run outputs
- `docs`: architecture, failures, and this guide

## 16. Related Documents

- `README.md`
- `docs/architecture.md`
- `docs/failure_modes.md`
