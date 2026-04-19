# Failure Modes and Recovery Guide

This guide documents the main runtime and demo-time failures, along with the system behavior that keeps the agent safe and explainable.

## 1. AutoGen Provider or Model Failure

### Symptoms

- Ticket output shows `autogen.success = false` for one or more enabled roles.
- Error details mention key, auth, provider, or model issues.
- The run still completes with deterministic decision logic.

### Handling

1. The orchestrator keeps deterministic policy checks active.
2. The run falls back to safe decisioning instead of failing open.
3. Audit output records the provider error for later inspection.

### Recovery

1. Verify `.env` values for `GROQ_API_KEY`, `GROQ_MODEL`, and `GROQ_BASE_URL`.
2. Reinstall dependencies with `pip install -r requirements.txt`.
3. Retry with `AUTOGEN_ROLES=planner` or switch to deterministic mode.

## 2. Refund or Cancellation Tool Guard Blocks

### Symptoms

- A refund or cancel action is requested before eligibility is confirmed.
- The execution trace shows a blocked or skipped tool step.

### Handling

1. Executor blocks the unsafe action instead of calling the mutation tool.
2. Critic records the policy reason and keeps the case explainable.
3. Final output uses a safe denial or escalation path as appropriate.

### Recovery

1. Confirm the eligibility check tool ran successfully first.
2. Inspect the plan order and step-by-step tool trace.
3. Verify the policy reason text returned by the eligibility check.

## 3. Low Confidence Decision Path

### Symptoms

- Confidence score falls below the configured threshold.
- The system marks the case as risky even if tools succeeded.

### Handling

1. The confidence service emits an escalation recommendation.
2. The orchestrator treats low confidence as a safety override.
3. The audit log captures the threshold and rationale.

### Recovery

1. Review the confidence payload in the ticket trace.
2. Check whether missing evidence or ambiguous linkage caused the drop.
3. Tune the threshold only after validating the policy impact.

## 4. UI Appears Stale or Misleading

### Symptoms

- Controls do not match the latest code behavior.
- The backend selection or result table looks out of sync.

### Handling

1. The app keeps execution isolated from stale browser state.
2. The UI writes uploads into a temp workspace instead of mutating source data.
3. Audit metadata retains the run context for debugging.

### Recovery

1. Stop older UI instances.
2. Relaunch `python ui_app.py`.
3. Hard refresh the browser and use the newest printed URL.

## 5. Unexpected Escalation Rate

### Symptoms

- More tickets escalate than expected in a demo run.

### Handling

1. Mandatory policy reasons override weak approval signals.
2. The critic and confidence service can independently force escalation.
3. The final reason payload explains why the case was not auto-resolved.

### Recovery

1. Inspect `escalation_reason_codes` and `primary_reason`.
2. Review `execution.steps` for missing evidence or failed tools.
3. Confirm that the case is not supposed to escalate under policy.

## Quick Triage Checklist

1. Confirm the backend mode used for the run.
2. Reproduce with one ticket.
3. Inspect `autogen.enabled` and `autogen.success` per stage.
4. Check `execution_status` and `tool_failures`.
5. Review reason codes, policy status, and audit output.

