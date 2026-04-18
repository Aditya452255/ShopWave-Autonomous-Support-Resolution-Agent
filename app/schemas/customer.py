from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CustomerTier = Literal["standard", "premium", "vip"]


class Address(BaseModel):
	model_config = ConfigDict(extra="forbid")

	street: str = Field(min_length=1)
	city: str = Field(min_length=1)
	state: str = Field(min_length=2, max_length=2)
	zip: str = Field(min_length=5, max_length=10)


class Customer(BaseModel):
	model_config = ConfigDict(extra="forbid")

	customer_id: str = Field(min_length=2)
	name: str = Field(min_length=1)
	email: str = Field(min_length=3)
	phone: str = Field(min_length=7)
	tier: CustomerTier
	member_since: date
	total_orders: int = Field(ge=0)
	total_spent: float = Field(ge=0)
	address: Address
	notes: str = Field(min_length=1)
