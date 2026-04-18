from __future__ import annotations

import argparse
import json

from config.settings import AppSettings, settings
from pipelines.process_tickets import run_pipeline_sync


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(description="Run a demo ticket-processing session.")
	parser.add_argument(
		"--limit",
		type=int,
		default=None,
		help="Optional ticket limit for quick demo runs.",
	)
	parser.add_argument(
		"--reset-audit",
		action="store_true",
		help="Clear existing audit records before running.",
	)
	parser.add_argument(
		"--backend",
		choices=["deterministic", "autogen"],
		default=None,
		help="Optional orchestration backend override for this run.",
	)
	return parser


def run_demo(
	*,
	limit: int | None = None,
	reset_audit: bool = True,
	backend: str | None = None,
) -> dict[str, object]:
	app_settings = (
		settings
		if not backend
		else AppSettings(**{**settings.model_dump(), "orchestration_mode": backend})
	)
	result = run_pipeline_sync(
		limit=limit,
		reset_audit=reset_audit,
		app_settings=app_settings,
	)
	payload = {
		"summary": result.get("summary", {}),
		"backend": app_settings.orchestration_mode,
		"audit_log": str(app_settings.audit_log_file),
	}
	print(json.dumps(payload, indent=2))
	return payload


if __name__ == "__main__":
	args = build_parser().parse_args()
	run_demo(
		limit=args.limit,
		reset_audit=args.reset_audit,
		backend=args.backend,
	)

