# ShopWave Autonomous Support Resolution Agent

ShopWave is a policy-first autonomous support resolution system for hackathon demos and practical experimentation.
It combines deterministic guardrails with optional LLM assistance to process customer tickets safely.

## Live Links

- Render Deploy: https://shopwave-autonomous-support-resolution.onrender.com/
- Project Walkthrough Video: https://drive.google.com/file/d/1y5gLNW4vCWZ8hlHW1xrxNyvB4G76MLU7/view

## Required Submission Files

- [Setup, run instructions, and tech stack](README.md)
- [Architecture diagram](docs/architecture.png)
- [Failure modes and recovery guide](docs/failure_modes.md)

## What This Project Does

1. Reads customer support tickets from structured JSON data.
2. Runs a strict Planner -> Executor -> Critic workflow per ticket.
3. Applies deterministic policy checks for refunds, cancellations, damaged items, wrong-item cases, exchanges, warranty, and FAQ.
4. Produces explainable outcomes: approve, escalate, or retry.
5. Writes a full audit trail for every decision.
6. Provides a polished Gradio dashboard for live judging/demo usage.

## Current Runtime Behavior (Important)

- Ticket processing is sequential (one ticket at a time) to improve predictability and reduce LLM rate-limit pressure.
- AutoGen is role-gated. By default, only planner LLM assistance is enabled (`AUTOGEN_ROLES=planner`).
- Executor and critic run deterministic logic unless explicitly enabled through environment configuration.
- UI is dark-only (light theme removed).

## Tech Stack

- Python 3.11+
- Pydantic 2.x
- pyautogen
- openai (for OpenAI-compatible provider path)
- Gradio 5.x
- python-dotenv

## Architecture At A Glance

The agent loop is:

1. ingest ticket data,
2. plan the case-specific actions,
3. execute guarded tools,
4. critique policy and risk,
5. apply confidence and escalation rules,
6. persist the decision audit.

See the rendered diagram in [docs/architecture.png](docs/architecture.png) and the detailed reference in [docs/architecture.md](docs/architecture.md).

## Quick Start

### 1. Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure .env

Create `.env` in the project root:

```dotenv
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_FALLBACK_MODELS=llama-3.1-8b-instant
GROQ_BASE_URL=https://api.groq.com/openai/v1

ORCHESTRATION_MODE=autogen
ENABLE_AUTOGEN=true
AUTOGEN_ROLES=planner
AUTOGEN_TEMPERATURE=0.0
AUTOGEN_MAX_TOKENS=260
AUTOGEN_PAYLOAD_CHAR_LIMIT=2800

PERSIST_TOOL_MUTATIONS=false
```

Notes:

- `ORCHESTRATION_MODE` can be `autogen` or `deterministic`.
- `AUTOGEN_ROLES` accepts comma-separated roles, for example `planner,critic`.
- Keep `PERSIST_TOOL_MUTATIONS=false` during demo runs to avoid mutating source data.

### 3. Run CLI

```powershell
python main.py --reset-audit
```

Optional flags:

- `--limit N`
- `--backend autogen|deterministic`

### 4. Run Demo Wrapper

```powershell
python run_demo.py --backend deterministic --limit 5 --reset-audit
```

### 5. Run UI

```powershell
python ui_app.py
```

Open the URL printed in terminal (typically `http://127.0.0.1:7860`; it may auto-shift if occupied).

## Decision Policy Summary

- Refund requires eligibility check before issue.
- Refunds above policy amount threshold escalate.
- Warranty cases escalate for manual review.
- Wrong-item and exchange cases escalate for fulfillment/handoff decisions.
- Fraud/legal risk signals always escalate.
- Missing or ambiguous linkage (customer/order) escalates.
- Low confidence or critical partial failure escalates.
- Deterministic policy checks override weak/uncertain LLM suggestions.

## Project Structure

- `main.py`: CLI entry.
- `run_demo.py`: compact demo runner.
- `ui_app.py`: Gradio dashboard.
- `config/settings.py`: environment and runtime settings.
- `config/prompts.py`: role prompts and case taxonomy.
- `pipelines/process_tickets.py`: run pipeline (sequential execution loop).
- `app/agents/`: planner, executor, critic.
- `app/core/`: orchestrator and memory helpers.
- `app/services/`: autogen client, confidence, retry, data loader, audit logger, UI data adapter.
- `app/tools/`: customer/order/refund/knowledge/communication tool implementations and registry.
- `app/schemas/`: pydantic models.
- `data/`: customers/orders/products/tickets and knowledge base policies.
- `artifacts/`: audit output.
- `docs/`: architecture, failure modes, and full project guide.

## UI Walkthrough

- Control Panel:
	- Upload optional data files.
	- Set ticket limit.
	- Select backend (`autogen` or `deterministic`).
	- Run analysis.
- Summary Metrics:
	- dashboard cards for total/resolved/escalated/failed-safe/backend/audit status.
- Decision Policy panel:
	- quick policy explanation for judges.
- Ticket Results table:
	- decision, confidence, short reason, detailed reason.
- Selected Ticket Investigation panel:
	- Overview, Agent Trace, Audit, Escalation tabs.

## Troubleshooting

### Backend radio or UI interactions seem stale

- Ensure only one server instance is active.
- Reopen the latest printed URL.
- Hard refresh browser (Ctrl+F5).

### AutoGen slow response

- Use `Ticket Limit=1` for first test.
- Keep `AUTOGEN_ROLES=planner` for faster runs.
- Use deterministic mode for baseline speed.

### Groq model concerns

- A warning about model pricing in AutoGen does not necessarily mean model unavailability.
- Validate model availability using provider API or direct one-ticket autogen run.

### Dependency issues

```powershell
pip install -r requirements.txt
```

## Deploy To GitHub (This Folder As Repo Root)

Run these commands from inside `ShopWave Autonomous Support Resolution Agent`:

```powershell
git init
git add .
git commit -m "Prepare ShopWave for Render deployment"
git branch -M main
git remote add origin https://github.com/Aditya452255/ShopWave-Autonomous-Support-Resolution-Agent.git
git push -u origin main
```

If the remote already exists, use:

```powershell
git remote set-url origin https://github.com/Aditya452255/ShopWave-Autonomous-Support-Resolution-Agent.git
git push -u origin main
```

## Deploy To Render

This repository now includes a Render Blueprint file: `render.yaml`.

### Option A: Blueprint Deploy (recommended)

1. Push code to GitHub.
2. In Render, select **New +** -> **Blueprint**.
3. Connect this GitHub repo.
4. Render auto-detects `render.yaml` and creates the web service.
5. Add `GROQ_API_KEY` when prompted.
6. Deploy.

### Option B: Manual Web Service

Use these settings:

- Environment: `Python`
- Build Command: `pip install -r requirements.txt`
- Start Command: `python ui_app.py`

Required environment variables:

- `GROQ_API_KEY` = your key
- `ORCHESTRATION_MODE` = `autogen`
- `ENABLE_AUTOGEN` = `true`
- `AUTOGEN_ROLES` = `planner`

Optional variables:

- `GROQ_MODEL` = `llama-3.3-70b-versatile`
- `GROQ_FALLBACK_MODELS` = `llama-3.1-8b-instant`
- `GROQ_BASE_URL` = `https://api.groq.com/openai/v1`
- `PERSIST_TOOL_MUTATIONS` = `false`

## Render Readiness Notes

- The UI launcher now reads `PORT` and binds to `0.0.0.0` on Render automatically.
- Local development still works as before.
- `.env.example` is included for reference.
- `.gitignore` prevents committing local secrets and runtime noise.

## Full Documentation

- `docs/project_guide.md`: complete technical guide.
- `docs/architecture.md`: architecture and data flow reference.
- `docs/failure_modes.md`: failure and recovery runbooks.

