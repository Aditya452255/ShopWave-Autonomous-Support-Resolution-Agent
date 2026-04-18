from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.schemas.customer import Customer
from app.schemas.order import Order
from app.schemas.ticket import Ticket
from config.settings import AppSettings, settings

ModelT = TypeVar("ModelT", bound=BaseModel)


class DataLoaderError(Exception):
	pass


class DataLoader:
	def __init__(self, app_settings: AppSettings | None = None) -> None:
		self.settings = app_settings or settings

	def load_customers(self) -> list[Customer]:
		return self._load_model_list(self.settings.customers_file, Customer)

	def load_orders(self) -> list[Order]:
		return self._load_model_list(self.settings.orders_file, Order)

	def load_tickets(self) -> list[Ticket]:
		return self._load_model_list(self.settings.tickets_file, Ticket)

	def load_customer_index_by_id(self) -> dict[str, Customer]:
		customers = self.load_customers()
		return {customer.customer_id: customer for customer in customers}

	def load_customer_index_by_email(self) -> dict[str, Customer]:
		customers = self.load_customers()
		return {customer.email.lower(): customer for customer in customers}

	def load_orders_by_customer_id(self) -> dict[str, list[Order]]:
		grouped: dict[str, list[Order]] = {}
		for order in self.load_orders():
			grouped.setdefault(order.customer_id, []).append(order)
		return grouped

	def _load_model_list(self, file_path: Path, model_type: type[ModelT]) -> list[ModelT]:
		rows = self._load_raw_list(file_path)
		models: list[ModelT] = []

		for index, row in enumerate(rows):
			try:
				models.append(model_type.model_validate(row))
			except ValidationError as exc:
				raise DataLoaderError(
					f"Validation failed for {file_path.name} at index {index}: {exc}"
				) from exc

		return models

	@staticmethod
	def _load_raw_list(file_path: Path) -> list[dict[str, Any]]:
		if not file_path.exists():
			raise DataLoaderError(f"Data file not found: {file_path}")

		try:
			raw = json.loads(file_path.read_text(encoding="utf-8-sig"))
		except json.JSONDecodeError as exc:
			raise DataLoaderError(f"Invalid JSON in {file_path}: {exc}") from exc

		if not isinstance(raw, list):
			raise DataLoaderError(f"Expected a JSON array in {file_path}")

		for index, item in enumerate(raw):
			if not isinstance(item, dict):
				raise DataLoaderError(
					f"Expected object rows in {file_path}, found {type(item).__name__} at index {index}"
				)

		return raw
