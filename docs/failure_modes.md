# Failure Modes And Recovery Guide

This document lists the practical failure patterns seen in development and runtime,
with expected behavior and immediate recovery steps.

## 1. UI Command Exits With Code 1

### Signal

- `python ui_app.py` exits unexpectedly.

### Typical Causes

1. Localhost accessibility issue in current environment.
# Failure Modes and Recovery Guide

This guide covers the most common runtime and demo-time failures, with practical recovery actions.

## 1. AutoGen Provider or Model Failure

### Symptoms

- Ticket output includes `autogen.success = false` for enabled roles.
- Error details mention key/auth/model/provider/client issues.
- System still returns decisions via deterministic fallback.

### Typical Causes

- Missing or invalid `GROQ_API_KEY`.
- Inactive `GROQ_MODEL`.
- Environment/dependency mismatch.

### Recovery

1. Verify `.env` values (`GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_BASE_URL`).
2. Reinstall dependencies: `pip install -r requirements.txt`.
3. Run one-ticket smoke test in autogen mode.
4. Switch to deterministic mode for continuity if provider issues persist.

## 2. Slow Autogen Runs

### Symptoms

- UI appears long-running during analysis.
- Throughput is much lower than deterministic mode.

### Typical Causes

- Live provider/network latency.
- Too many enabled LLM roles.
- Large payloads or token budgets.

### Recovery

1. Keep `AUTOGEN_ROLES=planner` unless needed.
2. Start with ticket limit = 1.
3. Use deterministic mode for baseline speed.
4. Keep prompt payloads constrained (already bounded by settings).

## 3. UI Appears Wrong or Stale

### Symptoms

- Controls appear out of sync with expected behavior.
- Visible theme/layout does not match latest code.
- Backend selection seems inconsistent.

### Typical Causes

- Multiple UI server instances on different ports.
- Browser connected to an older tab/server.
- Cached frontend assets.

### Recovery

1. Stop all existing UI processes.
2. Relaunch `python ui_app.py`.
3. Open only the newest terminal URL.
4. Hard refresh browser (`Ctrl+F5`).

## 4. Unexpected Escalation Rate

### Symptoms

- More tickets escalate than expected.

### Typical Causes

- Mandatory policy reason triggered.
- Missing order/customer verification evidence.
- Confidence/system risk reason present.

### Recovery

1. Inspect per-ticket `escalation_reason_codes` and `primary_reason`.
2. Check `execution.steps` for missing/failed required tools.
3. Confirm ticket has sufficient order linkage context.
4. Review `confidence` payload and threshold in settings.

## 5. Tool Guard Blocks (Refund/Cancel)

### Symptoms

- Action tool step appears skipped with policy-blocked metadata.
- Example: refund denied despite issue-refund step in plan.

### Typical Causes

- Eligibility check did not run or failed.
- Eligibility check returned not allowed under policy.

### Recovery

1. Verify `check_refund_eligibility` or `can_cancel_order` step success first.
2. Read returned policy reason text in step result.
3. Confirm plan order and tool result chain in agent trace.

## 6. Audit Log Confusion

### Symptoms

- Previous run records mixed with current experiment.
- Counts appear inconsistent with current ticket limit.

### Recovery

1. Start with `--reset-audit` for clean CLI/demo runs.
2. In UI runs, remember artifacts may be written under temp workspace context.
3. Verify `audit_path` shown in summary metadata.

## 7. Data Mutation Side Effects

### Symptoms

- Follow-up runs show changed order/refund states.

### Typical Causes

- Persistent mutation mode enabled.

### Recovery

1. Keep `PERSIST_TOOL_MUTATIONS=false` for demo consistency.
2. Restore source data snapshots when needed.

## 8. Safe Degradation Behavior

On hard runtime exceptions in orchestrator:

- final decision is forced to safe escalation,
- fallback reason payload is generated,
- failure context is still logged to audit.

This prevents unsafe approval paths when internal failures occur.

## 9. Quick Triage Checklist

1. Confirm backend mode used for the run.
2. Reproduce with one ticket.
3. Inspect `autogen.enabled` and `autogen.success` per stage.
4. Check `execution_status` and `tool_failures`.
5. Inspect reason codes and policy/system status.
6. Reset audit, rerun, compare outputs.

### Expected Handling

1. Structured error normalization in execution output.
2. Critic flags policy/risk issues.
3. Escalation is preferred over unsafe auto-resolution.

## 8. Unsafe Refund Chain Attempt

### Signal

- Refund issue action appears without confirmed eligibility.

### Expected Handling

1. Executor blocks unsafe refund action.
2. Critic records policy violation.
3. Final decision escalates.

## 9. Low Confidence Decision Path

### Signal

- Confidence score falls below threshold.

### Expected Handling

1. Confidence service emits escalation recommendation.
2. Orchestrator applies escalation override.
3. Audit record captures rationale.

## 10. Uploaded UI Files Affect Repository Data

### Signal

- Concern that uploaded files might overwrite canonical `data/` files.

### Expected Handling

1. UI copies uploads to isolated temp workspace.
2. Pipeline runs against temp workspace settings.
3. Repository data remains unchanged.

## 11. Throughput Pressure Under Large Batch

### Signal

- Large ticket set increases latency.

### Expected Handling

1. Bounded semaphore enforces max concurrent tickets.
2. Per-ticket sequence stays deterministic and ordered.
3. Summary includes resolved/escalated/retry counts for operational monitoring.

