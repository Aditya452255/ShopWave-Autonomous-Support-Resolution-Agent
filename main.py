from __future__ import annotations

import argparse
import json

from config.settings import AppSettings, settings
from pipelines.process_tickets import run_pipeline_sync


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		description="ShopWave Autonomous Support Resolution Agent",
	)
	parser.add_argument(
		"--limit",
		type=int,
		default=None,
		help="Optional ticket limit for quick test runs.",
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


def main() -> int:
	parser = build_parser()
	args = parser.parse_args()
	app_settings = settings if not args.backend else AppSettings(**{**settings.model_dump(), "orchestration_mode": args.backend})

	result = run_pipeline_sync(
		limit=args.limit,
		reset_audit=args.reset_audit,
		app_settings=app_settings,
	)
	print(json.dumps(result["summary"], indent=2))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())

