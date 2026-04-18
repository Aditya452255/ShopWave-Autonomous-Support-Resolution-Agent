from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from config.settings import AppSettings, settings


class UIDataAdapter:
	def __init__(self, base_settings: AppSettings | None = None) -> None:
		self.base_settings = base_settings or settings

	def prepare_settings(
		self,
		*,
		customers_path: str | None,
		orders_path: str | None,
		products_path: str | None,
		tickets_path: str | None,
		policies_path: str | None = None,
	) -> tuple[AppSettings, dict[str, Any]]:
		workspace_root = Path(tempfile.mkdtemp(prefix="shopwave_ui_"))
		(workspace_root / "data").mkdir(parents=True, exist_ok=True)
		(workspace_root / "data" / "knowledge_base").mkdir(parents=True, exist_ok=True)
		(workspace_root / "artifacts").mkdir(parents=True, exist_ok=True)

		self._copy_or_default(customers_path, self.base_settings.customers_file, workspace_root / "data" / "customers.json")
		self._copy_or_default(orders_path, self.base_settings.orders_file, workspace_root / "data" / "orders.json")
		self._copy_or_default(products_path, self.base_settings.products_file, workspace_root / "data" / "products.json")
		self._copy_or_default(tickets_path, self.base_settings.tickets_file, workspace_root / "data" / "tickets.json")
		self._copy_or_default(
			policies_path,
			self.base_settings.policies_file,
			workspace_root / "data" / "knowledge_base" / "policies.txt",
		)

		(workspace_root / "artifacts" / "audit_log.json").write_text("[]", encoding="utf-8")

		prepared = AppSettings(
			**{
				**self.base_settings.model_dump(),
				"project_root": workspace_root,
			}
		)

		metadata = {
			"workspace_root": str(workspace_root),
			"policies_text": prepared.policies_file.read_text(encoding="utf-8", errors="ignore"),
		}
		return prepared, metadata

	@staticmethod
	def _copy_or_default(uploaded_path: str | None, default_path: Path, target_path: Path) -> None:
		source = Path(uploaded_path) if uploaded_path else default_path
		if not source.exists():
			target_path.write_text("[]", encoding="utf-8")
			return
		shutil.copy2(source, target_path)

	@staticmethod
	def load_json_file(path: Path) -> list[dict[str, Any]]:
		if not path.exists():
			return []
		raw = path.read_text(encoding="utf-8-sig")
		try:
			parsed = json.loads(raw)
		except json.JSONDecodeError:
			return []
		if not isinstance(parsed, list):
			return []
		return [item for item in parsed if isinstance(item, dict)]
