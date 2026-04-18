from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config.settings import AppSettings, settings


class AuditLogger:
	def __init__(self, app_settings: AppSettings | None = None) -> None:
		self.settings = app_settings or settings
		self._path: Path = self.settings.audit_log_file
		self._ensure_file()

	@property
	def file_path(self) -> Path:
		return self._path

	def clear_records(self) -> None:
		self._write_records([])

	def read_records(self) -> list[dict[str, Any]]:
		self._ensure_file()
		raw = self._path.read_text(encoding="utf-8").strip()
		if not raw:
			return []

		try:
			parsed = json.loads(raw)
		except json.JSONDecodeError:
			return []

		if not isinstance(parsed, list):
			return []

		return [item for item in parsed if isinstance(item, dict)]

	def append_record(self, record: dict[str, Any]) -> None:
		records = self.read_records()
		payload = self._sanitize_payload(record)
		payload.setdefault("timestamp", datetime.now(tz=UTC).isoformat())
		payload.setdefault("audit_explanation", "No audit explanation provided.")
		records.append(payload)
		self._write_records(records)

	def append_many(self, records: list[dict[str, Any]]) -> None:
		existing = self.read_records()
		now = datetime.now(tz=UTC).isoformat()
		for record in records:
			payload = self._sanitize_payload(record)
			payload.setdefault("timestamp", now)
			payload.setdefault("audit_explanation", "No audit explanation provided.")
			existing.append(payload)
		self._write_records(existing)

	def _ensure_file(self) -> None:
		self.settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
		if not self._path.exists():
			self._path.write_text("[]", encoding="utf-8")
			return

		if not self._path.read_text(encoding="utf-8").strip():
			self._path.write_text("[]", encoding="utf-8")

	def _write_records(self, records: list[dict[str, Any]]) -> None:
		self._ensure_file()
		self._path.write_text(json.dumps(records, indent=2), encoding="utf-8")

	@staticmethod
	def _sanitize_payload(record: dict[str, Any]) -> dict[str, Any]:
		def _normalize(value: Any) -> Any:
			if isinstance(value, dict):
				return {str(key): _normalize(item) for key, item in value.items()}
			if isinstance(value, list):
				return [_normalize(item) for item in value]
			if isinstance(value, (str, int, float, bool)) or value is None:
				return value
			return str(value)

		return _normalize(dict(record))

