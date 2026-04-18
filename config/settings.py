from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, PositiveInt

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _env_bool(name: str, default: bool) -> bool:
	value = os.getenv(name)
	if value is None:
		return default
	return value.strip().lower() in {"1", "true", "yes", "on"}


class AppSettings(BaseModel):
	project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1])
	data_dir_name: str = "data"
	artifacts_dir_name: str = "artifacts"
	knowledge_base_dir_name: str = "knowledge_base"
	policies_filename: str = "policies.txt"
	audit_log_filename: str = "audit_log.json"
	concurrency_limit: PositiveInt = 1
	confidence_escalation_threshold: float = 0.6
	orchestration_mode: str = Field(default_factory=lambda: os.getenv("ORCHESTRATION_MODE", "autogen"))
	enable_autogen: bool = Field(default_factory=lambda: _env_bool("ENABLE_AUTOGEN", True))
	autogen_roles: str = Field(default_factory=lambda: os.getenv("AUTOGEN_ROLES", "planner"))
	persist_tool_mutations: bool = Field(default_factory=lambda: _env_bool("PERSIST_TOOL_MUTATIONS", False))
	groq_api_key: str | None = Field(default_factory=lambda: os.getenv("GROQ_API_KEY"))
	groq_model: str = Field(default_factory=lambda: os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"))
	groq_fallback_models: str = Field(default_factory=lambda: os.getenv("GROQ_FALLBACK_MODELS", "llama-3.1-8b-instant"))
	groq_base_url: str = Field(default_factory=lambda: os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"))
	autogen_temperature: float = Field(default_factory=lambda: float(os.getenv("AUTOGEN_TEMPERATURE", "0.0")))
	autogen_max_tokens: int = Field(default_factory=lambda: int(os.getenv("AUTOGEN_MAX_TOKENS", "260")))
	autogen_payload_char_limit: int = Field(default_factory=lambda: int(os.getenv("AUTOGEN_PAYLOAD_CHAR_LIMIT", "2800")))

	@property
	def data_dir(self) -> Path:
		return self.project_root / self.data_dir_name

	@property
	def artifacts_dir(self) -> Path:
		return self.project_root / self.artifacts_dir_name

	@property
	def customers_file(self) -> Path:
		return self.data_dir / "customers.json"

	@property
	def orders_file(self) -> Path:
		return self.data_dir / "orders.json"

	@property
	def products_file(self) -> Path:
		return self.data_dir / "products.json"

	@property
	def tickets_file(self) -> Path:
		return self.data_dir / "tickets.json"

	@property
	def policies_file(self) -> Path:
		return self.data_dir / self.knowledge_base_dir_name / self.policies_filename

	@property
	def audit_log_file(self) -> Path:
		return self.artifacts_dir / self.audit_log_filename

	def data_file(self, file_name: str) -> Path:
		return self.data_dir / file_name

	@property
	def autogen_active(self) -> bool:
		return self.enable_autogen and self.orchestration_mode.strip().lower() == "autogen"

	@property
	def enabled_autogen_roles(self) -> set[str]:
		roles = {role.strip().lower() for role in self.autogen_roles.split(",") if role.strip()}
		return roles or {"planner"}


settings = AppSettings()
